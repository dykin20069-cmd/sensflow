"""Minimal in-process polling for marketplace synchronization and PreOrders."""

import asyncio
import logging
from contextlib import suppress
from decimal import Decimal
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
        if self._notifications is not None:
            await self._notifications.deliver_pending()
        return len(active_attempts)

    async def run_reorder_pass(self) -> None:
        """Notify stock, maximize completed PreOrders, and safely requeue active attempts."""
        async with self._sessions() as session:
            repository = ClientOrderRepository(session)
            orders = await repository.list_by_status(
                ClientOrderStatus.PREORDER,
                limit=10_000,
            )
            active_orders = await repository.list_by_status(
                ClientOrderStatus.PURCHASING,
                limit=10_000,
            )
        candidates = tuple((order.id, order.requested_robux) for order in orders)
        plan = await self._workflows.plan_automation(candidates)
        settings = await self._get_settings()
        visible_rates = {
            stock.rate for stock in plan.stock if stock.rate <= plan.maximum_purchase_rate
        }
        new_rates = visible_rates - self._visible_stock_rates
        for stock in plan.stock:
            if stock.rate in new_rates:
                logger.info(
                    "stock_detected",
                    extra={
                        "rate": str(stock.rate),
                        "total_robux": stock.total_robux_amount,
                        "max_instant": stock.max_instant_order,
                    },
                )
        self._visible_stock_rates = visible_rates
        if (
            self._notifications is not None
            and settings.telegram_notifications_enabled
            and NotificationType.AUTOMATIC_REORDER in settings.notification_categories
        ):
            for stock in plan.stock:
                if stock.rate not in new_rates:
                    continue
                await self._notifications.queue_once(
                    notification_type=NotificationType.AUTOMATIC_REORDER,
                    title=f"New stock appeared · {stock.rate.normalize()}",
                    message=_stock_appeared_message(stock),
                    throttle_seconds=300,
                )
        for order_id in plan.order_ids:
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
        for order in active_orders:
            try:
                await self._workflows.automatic_requeue(order.id, plan.stock)
            except Exception as error:
                logger.exception(
                    "automatic_reorder_failed",
                    extra={"order_id": str(order.id)},
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
        next_reorder = 0.0
        while not self._shutdown.is_set():
            try:
                settings = await self._get_settings()
                now = loop.time()
                if now >= next_sync:
                    await self.run_synchronization_pass()
                    next_sync = loop.time() + settings.synchronization_interval_seconds
                if now >= next_reorder:
                    if settings.automatic_reorder_enabled:
                        await self.run_reorder_pass()
                    next_reorder = loop.time() + float(settings.automatic_reorder_interval_seconds)
                delay = max(0.0, min(next_sync, next_reorder) - loop.time())
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


def _stock_appeared_message(stock: MarketplaceStock) -> str:
    preferred = "\n🎯 Preferred stock detected (≤ 4.3$)" if stock.rate <= Decimal("4.3") else ""
    return (
        "<b>🟢 New stock appeared</b>\n\n"
        f"Rate: {stock.rate.normalize()}$\n"
        f"Available: {stock.total_robux_amount:,} R$\n"
        f"Max instant: {stock.max_instant_order:,} R$"
        f"{preferred}"
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
