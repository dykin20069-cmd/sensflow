"""Minimal in-process polling for marketplace synchronization and PreOrders."""

import asyncio
import logging
from contextlib import suppress
from decimal import Decimal
from html import escape
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sensflow.application.marketplace_workflows import MarketplaceWorkflows
from sensflow.application.notifications import NotificationService
from sensflow.application.rbxcreate_bridge import MarketplaceStock
from sensflow.domain.enums import ClientOrderStatus, MarketplaceOrderStatus, NotificationType
from sensflow.domain.settings.service import SettingsDefaults, create_settings
from sensflow.infrastructure.database.models import SystemSettings
from sensflow.repositories import (
    ClientOrderRepository,
    MarketplaceOrderRepository,
    SystemSettingsRepository,
)

logger = logging.getLogger(__name__)

SessionFactory = async_sessionmaker[AsyncSession]
STOCK_NOTIFICATION_COOLDOWN_SECONDS = 60


class AutomationLoop:
    """Run sequential polling passes inside one owned asyncio task."""

    def __init__(
        self,
        sessions: SessionFactory,
        workflows: MarketplaceWorkflows,
        *,
        settings_defaults: SettingsDefaults | None = None,
        notifications: NotificationService | None = None,
    ) -> None:
        self._sessions = sessions
        self._workflows = workflows
        self._settings_defaults = settings_defaults
        self._notifications = notifications
        self._shutdown = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._visible_stock_rates: set[Decimal] = set()

    async def start(self) -> None:
        """Start the loop once without blocking application startup."""
        if self._task is not None and not self._task.done():
            return
        self._shutdown.clear()
        self._task = asyncio.create_task(self._run(), name="marketplace-automation")

    @property
    def is_running(self) -> bool:
        """Report whether the owned polling task is currently alive."""
        return self._task is not None and not self._task.done()

    async def stop(self) -> None:
        """Wake and await the owned loop task."""
        if self._task is None:
            return
        self._shutdown.set()
        try:
            await self._task
        finally:
            self._task = None

    async def run_synchronization_pass(self) -> int:
        """Synchronize every active attempt sequentially and isolate failures."""
        settings = await self._get_settings()
        async with self._sessions() as session:
            repository = MarketplaceOrderRepository(session)
            active_attempts = await repository.list_by_status(
                MarketplaceOrderStatus.ACTIVE,
                limit=10_000,
            )
            unfinished_completions = await repository.list_completed_for_unfinished_client_orders(
                limit=10_000
            )
            attempt_ids = tuple(
                attempt.id for attempt in (*active_attempts, *unfinished_completions)
            )
        for attempt_id in attempt_ids:
            try:
                await self._workflows.synchronize_marketplace_order(attempt_id)
            except Exception:
                logger.exception(
                    "marketplace_synchronization_failed",
                    extra={"marketplace_order_id": str(attempt_id)},
                )
                if (
                    self._notifications is not None
                    and settings.telegram_notifications_enabled
                    and NotificationType.SYNCHRONIZATION_FAILED in settings.notification_categories
                ):
                    await self._notifications.queue(
                        notification_type=NotificationType.SYNCHRONIZATION_FAILED,
                        title="Synchronization Failed",
                        message=(
                            "<b>❌ Synchronization Failed</b>\n\n"
                            f"Marketplace order: <code>{attempt_id}</code>\n"
                            "The next synchronization pass will retry automatically."
                        ),
                    )
        if self._notifications is not None:
            await self._notifications.deliver_pending()
        return len(active_attempts)

    async def run_reorder_pass(self) -> None:
        """Notify stock, maximize completed PreOrders, and safely requeue active attempts."""
        await self._run_stock_pass(process_preorders=True, process_active=True)

    async def _run_stock_pass(
        self,
        *,
        process_preorders: bool,
        process_active: bool,
    ) -> None:
        """Use one stock snapshot for whichever automation schedules are due."""
        async with self._sessions() as session:
            repository = ClientOrderRepository(session)
            orders = (
                await repository.list_by_status(
                    ClientOrderStatus.PREORDER,
                    limit=10_000,
                )
                if process_preorders
                else []
            )
            active_orders = (
                await repository.list_by_status(
                    ClientOrderStatus.PURCHASING,
                    limit=10_000,
                )
                if process_active
                else []
            )
        candidates = tuple((order.id, order.requested_robux) for order in orders)
        plan = await self._workflows.plan_automation(candidates)
        settings = await self._get_settings()
        visible_rates = {
            stock.rate
            for stock in plan.stock
            if plan.minimum_purchase_rate <= stock.rate <= plan.maximum_purchase_rate
            and stock.max_instant_order > 0
            and stock.total_robux_amount > 0
        }
        new_rates = visible_rates - self._visible_stock_rates if process_preorders else set()
        if process_preorders:
            for stock in plan.stock:
                if stock.rate in new_rates:
                    logger.info(
                        "stock_detected",
                        extra={
                            "rate": str(stock.rate),
                            "total_robux": stock.total_robux_amount,
                            "available": stock.total_robux_amount,
                            "max_instant": stock.max_instant_order,
                        },
                    )
            self._visible_stock_rates = visible_rates
        if (
            process_preorders
            and self._notifications is not None
            and settings.telegram_notifications_enabled
            and NotificationType.STOCK_AVAILABLE in settings.notification_categories
        ):
            for stock in plan.stock:
                if stock.rate not in new_rates:
                    continue
                await self._notifications.queue_once(
                    notification_type=NotificationType.STOCK_AVAILABLE,
                    title=f"Suitable stock detected · {stock.rate.normalize()}",
                    message=_stock_appeared_message(stock, len(plan.order_ids)),
                    throttle_seconds=STOCK_NOTIFICATION_COOLDOWN_SECONDS,
                )
        for order_id in plan.order_ids if process_preorders else ():
            try:
                await self._workflows.start_purchase(order_id)
            except Exception as error:
                logger.exception(
                    "automatic_reorder_failed",
                    extra={"order_id": str(order_id)},
                )
                await self._queue_marketplace_error(
                    order_id,
                    "create_order",
                    error,
                    enabled=(
                        settings.telegram_notifications_enabled
                        and NotificationType.MARKETPLACE_ERROR in settings.notification_categories
                    ),
                )
        for order in active_orders if process_active else ():
            try:
                await self._workflows.automatic_requeue(order.id, plan.stock)
            except Exception as error:
                active_attempt = None
                with suppress(Exception):
                    async with self._sessions() as session:
                        active_attempt = await MarketplaceOrderRepository(
                            session
                        ).get_active_for_client_order(order.id)
                logger.exception(
                    "auto_requeue_failed",
                    extra={
                        "order_id": str(order.id),
                        "marketplace_order_id": (
                            None if active_attempt is None else str(active_attempt.id)
                        ),
                        "external_order_id": (
                            None if active_attempt is None else active_attempt.rbxcreate_order_id
                        ),
                        "customer": order.customer.current_username,
                        "requested_robux": order.requested_robux,
                        "reason": str(error),
                    },
                )
                if (
                    self._notifications is not None
                    and settings.telegram_notifications_enabled
                    and NotificationType.AUTO_REQUEUE_FAILED in settings.notification_categories
                ):
                    await self._notifications.queue(
                        notification_type=NotificationType.AUTO_REQUEUE_FAILED,
                        title="Auto Requeue Failed",
                        message=_auto_requeue_failed_message(order, error),
                        client_order_id=order.id,
                    )
                await self._queue_marketplace_error(
                    order.id,
                    "automatic_reorder",
                    error,
                    enabled=(
                        settings.telegram_notifications_enabled
                        and NotificationType.MARKETPLACE_ERROR in settings.notification_categories
                    ),
                )
        if self._notifications is not None:
            await self._notifications.deliver_pending()

    async def _queue_marketplace_error(
        self,
        order_id: object,
        operation: str,
        error: Exception,
        *,
        enabled: bool,
    ) -> None:
        if self._notifications is None or not enabled:
            return
        await self._notifications.queue(
            notification_type=NotificationType.MARKETPLACE_ERROR,
            title="Marketplace error",
            message=_marketplace_error_message(order_id, operation, error),
            client_order_id=order_id if isinstance(order_id, UUID) else None,
        )

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        next_sync = 0.0
        next_monitoring = 0.0
        next_reorder = 0.0
        while not self._shutdown.is_set():
            try:
                settings = await self._get_settings()
                now = loop.time()
                if now >= next_sync:
                    await self.run_synchronization_pass()
                    next_sync = loop.time() + settings.synchronization_interval_seconds
                monitoring_due = now >= next_monitoring
                requeue_due = now >= next_reorder
                if monitoring_due or requeue_due:
                    if settings.automatic_reorder_enabled:
                        await self._run_stock_pass(
                            process_preorders=monitoring_due,
                            process_active=requeue_due,
                        )
                    scheduled_at = loop.time()
                    if monitoring_due:
                        next_monitoring = (
                            scheduled_at + settings.marketplace_monitoring_interval_seconds
                        )
                    if requeue_due:
                        next_reorder = scheduled_at + float(
                            settings.automatic_reorder_interval_seconds
                        )
                delay = max(
                    0.0,
                    min(next_sync, next_monitoring, next_reorder) - loop.time(),
                )
            except Exception:
                logger.exception("automation_iteration_failed")
                delay = 1.0
            with suppress(TimeoutError):
                await asyncio.wait_for(self._shutdown.wait(), timeout=delay)

    async def _get_settings(self) -> SystemSettings:
        async with self._sessions.begin() as session:
            repository = SystemSettingsRepository(session)
            settings = await repository.get_current()
            if settings is not None:
                return settings
            if self._settings_defaults is None:
                raise RuntimeError("System Settings are not initialized")
            return await repository.save(create_settings(self._settings_defaults))


def _stock_appeared_message(stock: MarketplaceStock, matching_preorders: int = 0) -> str:
    preferred = "\n🎯 Preferred stock detected (≤ 4.3$)" if stock.rate <= Decimal("4.3") else ""
    return (
        "<b>🟢 Suitable stock detected</b>\n\n"
        f"Rate: {stock.rate.normalize()}$\n"
        f"Accounts: {stock.accounts_count:,}\n"
        f"Available: {stock.total_robux_amount:,} R$\n"
        f"Max instant: {stock.max_instant_order:,} R$\n"
        f"{matching_preorders} matching PreOrders will be processed automatically."
        f"{preferred}"
    )


def _auto_requeue_failed_message(order: object, error: Exception) -> str:
    customer = getattr(getattr(order, "customer", None), "current_username", "Unknown")
    requested_robux = getattr(order, "requested_robux", "—")
    return (
        "<b>❌ Auto Requeue Failed</b>\n\n"
        f"Customer: {escape(str(customer))}\n"
        f"Order: {requested_robux} R$\n"
        f"Reason:\n{escape(type(error).__name__)}: {escape(str(error))}"
    )


def _marketplace_error_message(order_id: object, operation: str, error: Exception) -> str:
    identifier = getattr(order_id, "hex", str(order_id))
    short_id = str(identifier)[:8].upper()
    return (
        "<b>❌ Marketplace error</b>\n\n"
        f"Order: #{short_id}\n\n"
        f"Operation: {operation}\n\n"
        f"Error: {type(error).__name__}: {error}\n\n"
        "Retry scheduled automatically."
    )
