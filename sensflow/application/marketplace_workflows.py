"""Transactional RBXCrate workflows for Client and Marketplace Orders."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from html import escape
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sensflow.application.dto import (
    ActionResultDTO,
    CurrentStockDTO,
    MarketplaceStockDTO,
    StockAvailabilityDTO,
)
from sensflow.application.errors import (
    ConflictError,
    MarketplaceCancellationUnsupportedError,
    MarketplaceIntegrationError,
    MarketplaceRateLimitedError,
    NotFoundError,
)
from sensflow.application.rbxcreate_bridge import (
    MarketplaceStock,
    MarketplaceSyncResult,
    RbxcreateBridge,
)
from sensflow.domain.enums import (
    ClientOrderStatus,
    MarketplaceOrderStatus,
    NotificationDeliveryStatus,
    NotificationType,
    TimelineEventType,
)
from sensflow.domain.errors import DomainConflictError, DomainValidationError
from sensflow.domain.finance.service import (
    PurchaseResult,
    calculate_customer_receives,
    calculate_financial_snapshot,
    create_purchase_result,
    record_observed_marketplace_cost,
)
from sensflow.domain.marketplace.service import (
    MarketplaceOrderResult,
    cancel_marketplace_order,
    complete_marketplace_order,
    create_marketplace_order,
    update_marketplace_progress,
)
from sensflow.domain.order.service import (
    activate_fallback,
    cancel_order,
    complete_order,
    effective_purchase_rate,
    enter_preorder,
    return_to_preorder,
    start_purchasing,
)
from sensflow.domain.order.timeline import create_timeline_event
from sensflow.domain.settings.service import SettingsDefaults, create_settings
from sensflow.infrastructure.database.base import utc_now
from sensflow.infrastructure.database.models import (
    ClientOrder,
    MarketplaceOrder,
    Notification,
    SystemSettings,
)
from sensflow.repositories import (
    ClientOrderRepository,
    CustomerRepository,
    MarketplaceOrderRepository,
    NotificationRepository,
    SystemSettingsRepository,
    TimelineEventRepository,
    UserPlaceCacheRepository,
)

SessionFactory = async_sessionmaker[AsyncSession]
Clock = Callable[[], datetime]
logger = logging.getLogger(__name__)
FRESH_PURCHASE_GUARD_SECONDS = 5
STATUS_CHECK_COOLDOWN_SECONDS = 3
STATUS_CHECK_BACKOFF_SECONDS = (5, 10, 20)


@dataclass(frozen=True, slots=True)
class FinancePolicy:
    """Non-persisted calculation rules required to finalize an automated purchase."""

    roblox_tax_rate: Decimal = Decimal("0.30")
    robux_rounding: str = ROUND_DOWN
    money_rounding: str = ROUND_HALF_UP
    money_quantum: Decimal = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class AutomationStockPlan:
    """One consistent RBXCrate stock snapshot and its maximum-clients plan."""

    order_ids: tuple[UUID, ...]
    stock: tuple[MarketplaceStock, ...]
    minimum_purchase_rate: Decimal
    maximum_purchase_rate: Decimal


@dataclass(frozen=True, slots=True)
class _StatusCheckOutcome:
    snapshot: MarketplaceSyncResult
    skipped: bool = False


class MarketplaceWorkflows:
    """Coordinate database state transitions with the RBXCrate bridge."""

    def __init__(
        self,
        sessions: SessionFactory,
        bridge: RbxcreateBridge,
        *,
        settings_defaults: SettingsDefaults | None = None,
        minimum_purchase_rate: Decimal = Decimal("0"),
        finance_policy: FinancePolicy | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._sessions = sessions
        self._bridge = bridge
        self._settings_defaults = settings_defaults
        self._minimum_purchase_rate = minimum_purchase_rate
        self._finance_policy = finance_policy or FinancePolicy()
        self._clock = clock

    async def get_current_stock(self) -> CurrentStockDTO:
        """Return the live RBXCrate stock with the currently persisted rate limit."""
        async with self._sessions.begin() as session:
            settings = await self._get_settings(session)
            stock = await self._bridge.get_detailed_stock()
        return CurrentStockDTO(
            items=tuple(
                MarketplaceStockDTO(
                    rate=item.rate,
                    accounts_count=item.accounts_count,
                    max_instant_order=item.max_instant_order,
                    total_robux_amount=item.total_robux_amount,
                )
                for item in stock
            ),
            maximum_purchase_rate=settings.maximum_purchase_rate,
            preferred_rate=settings.preferred_purchase_rate,
            updated_at=self._clock(),
        )

    async def check_stock(
        self,
        requested_robux: int,
        preferred_mode_enabled: bool | None = None,
    ) -> StockAvailabilityDTO:
        """Check one amount against one live snapshot and the persisted rate policy."""
        async with self._sessions.begin() as session:
            settings = await self._get_settings(session)
            stock = await self._bridge.get_detailed_stock()
        use_preferred = (
            settings.preferred_mode_default is not False
            if preferred_mode_enabled is None
            else preferred_mode_enabled
        )
        selected = _select_stock(
            stock,
            requested_robux=requested_robux,
            minimum_purchase_rate=self._minimum_purchase_rate,
            maximum_purchase_rate=(
                settings.preferred_purchase_rate
                if use_preferred
                else settings.maximum_purchase_rate
            ),
        )
        return StockAvailabilityDTO(
            available=selected is not None,
            maximum_purchase_rate=settings.maximum_purchase_rate,
        )

    async def plan_preorders(
        self,
        candidates: tuple[tuple[UUID, int], ...],
    ) -> tuple[tuple[UUID, ...], MarketplaceStock | None]:
        """Plan a maximum-clients pass from one consistent stock snapshot."""
        async with self._sessions.begin() as session:
            settings = await self._get_settings(session)
            stock = await self._bridge.get_detailed_stock()
        return _select_preorders_maximum_clients(
            candidates,
            stock,
            minimum_purchase_rate=self._minimum_purchase_rate,
            maximum_purchase_rate=settings.maximum_purchase_rate,
        )

    async def plan_automation(
        self,
        candidates: tuple[tuple[UUID, int, Decimal], ...],
    ) -> AutomationStockPlan:
        """Fetch stock once for notification, PreOrder, and active-requeue decisions."""
        async with self._sessions.begin() as session:
            settings = await self._get_settings(session)
            stock = await self._bridge.get_detailed_stock()
        order_ids, _ = _select_preorders_by_order_limit(
            candidates,
            stock,
            minimum_purchase_rate=self._minimum_purchase_rate,
        )
        return AutomationStockPlan(
            order_ids=order_ids,
            stock=stock,
            minimum_purchase_rate=self._minimum_purchase_rate,
            maximum_purchase_rate=settings.maximum_purchase_rate,
        )

    async def activate_expired_fallbacks(self) -> int:
        """Enable hard-limit purchasing for every expired preferred-rate PreOrder."""
        now = self._clock()
        activated = 0
        async with self._sessions.begin() as session:
            repository = ClientOrderRepository(session)
            for order in await repository.list_expired_preferred_for_update(now):
                if activate_fallback(order, now):
                    await repository.save(order)
                    activated += 1
                    logger.info(
                        "preferred_fallback_activated",
                        extra={
                            "order_id": str(order.id),
                            "preferred_rate": str(order.preferred_rate),
                            "maximum_rate": str(order.marketplace_rate_limit),
                        },
                    )
        return activated

    async def get_balance(self) -> Decimal:
        """Expose the RBXCrate balance to the owned automation coordinator."""
        return await self._bridge.get_balance()

    async def start_purchase(
        self,
        order_id: UUID,
        stock: tuple[MarketplaceStock, ...] | None = None,
    ) -> ActionResultDTO:
        """Select suitable stock and either start an attempt or retain a PreOrder."""
        try:
            async with self._sessions.begin() as session:
                orders = ClientOrderRepository(session)
                order = await orders.get_for_update(order_id)
                if order is None:
                    raise NotFoundError("Client Order")
                if order.current_status not in {
                    ClientOrderStatus.DRAFT,
                    ClientOrderStatus.PREORDER,
                }:
                    raise DomainConflictError("Purchasing can start only for a Draft or PreOrder")

                now = self._clock()
                timeline = TimelineEventRepository(session)
                customer = await CustomerRepository(session).get(order.customer_id)
                if customer is None:
                    raise NotFoundError("Customer")
                was_draft = order.current_status is ClientOrderStatus.DRAFT
                if (
                    was_draft
                    and order.preferred_expires_at is None
                    and order.preferred_timeout_minutes is not None
                ):
                    order.preferred_expires_at = now + timedelta(
                        minutes=order.preferred_timeout_minutes
                    )
                if order.current_status is ClientOrderStatus.PREORDER:
                    activate_fallback(order, now)
                if was_draft:
                    await timeline.save(
                        create_timeline_event(
                            order,
                            TimelineEventType.PAYMENT_CONFIRMED,
                            "Customer payment confirmed.",
                            now,
                        )
                    )

                current_stock = await self._bridge.get_detailed_stock() if stock is None else stock
                selected = _select_stock(
                    current_stock,
                    requested_robux=order.requested_robux,
                    minimum_purchase_rate=self._minimum_purchase_rate,
                    maximum_purchase_rate=effective_purchase_rate(order, now),
                )
                if selected is None:
                    if was_draft:
                        enter_preorder(order, now)
                    await orders.save(order)
                    if was_draft:
                        await timeline.save(
                            create_timeline_event(
                                order,
                                TimelineEventType.PREORDER_CREATED,
                                "No stock satisfies the preferred rate and quantity limits.",
                                now + timedelta(microseconds=1),
                            )
                        )
                        logger.info(
                            "preorder_created",
                            extra={
                                "order_id": str(order.id),
                                "customer": customer.current_username,
                                "requested_robux": order.requested_robux,
                                "place_id": order.current_place_id,
                            },
                        )
                    return ActionResultDTO(
                        message="No suitable stock available; order is waiting in PreOrders.",
                        order_id=order.id,
                    )

                active = await MarketplaceOrderRepository(
                    session
                ).get_active_for_client_order_for_update(order.id)
                if active is not None:
                    raise DomainConflictError(
                        "The Client Order already has an active Marketplace Order"
                    )
                start_purchasing(order)
                external = await self._bridge.create_gamepass_order(
                    roblox_username=customer.current_username,
                    order_id=str(order.id),
                    robux_amount=order.requested_robux,
                    place_id=order.current_place_id,
                )
                if external.status is not MarketplaceOrderStatus.ACTIVE:
                    raise MarketplaceIntegrationError(
                        "RBXCrate returned a terminal status while creating the order"
                    )
                marketplace_order = create_marketplace_order(
                    order,
                    MarketplaceOrderResult(
                        external_order_id=external.external_order_id,
                        purchase_rate=selected.rate,
                        requested_robux=order.requested_robux,
                    ),
                    active_order_exists=False,
                )
                marketplace_order.purchase_started_at = now
                await orders.save(order)
                await MarketplaceOrderRepository(session).save(marketplace_order)
                await timeline.save(
                    create_timeline_event(
                        order,
                        TimelineEventType.PURCHASING_STARTED,
                        "Suitable stock found; Purchasing started.",
                        now + timedelta(microseconds=1),
                    )
                )
                await timeline.save(
                    create_timeline_event(
                        order,
                        TimelineEventType.MARKETPLACE_ORDER_CREATED,
                        "Marketplace Order created through RBXCrate.",
                        now + timedelta(microseconds=2),
                    )
                )
                logger.info(
                    "marketplace_purchase_started",
                    extra={
                        "order_id": str(order.id),
                        "customer_id": str(order.customer_id),
                        "marketplace_order_id": str(marketplace_order.id),
                        "external_order_id": marketplace_order.rbxcreate_order_id,
                        "requested_robux": order.requested_robux,
                        "selected_rate": str(selected.rate),
                    },
                )
        except (DomainValidationError, DomainConflictError) as error:
            raise ConflictError(str(error)) from error
        except IntegrityError as error:
            raise ConflictError("The order changed concurrently; please refresh") from error
        return ActionResultDTO(message="Purchase started via RBXCrate.")

    async def synchronize_marketplace_order(
        self,
        marketplace_order_id: UUID,
    ) -> ActionResultDTO:
        """Apply one external status snapshot exactly once."""
        try:
            async with self._sessions.begin() as session:
                marketplace_orders = MarketplaceOrderRepository(session)
                initial = await marketplace_orders.get(marketplace_order_id)
                if initial is None:
                    raise NotFoundError("Marketplace Order")
                orders = ClientOrderRepository(session)
                order = await orders.get_for_update(initial.client_order_id)
                if order is None:
                    raise NotFoundError("Client Order")
                marketplace_order = await marketplace_orders.get_for_update(marketplace_order_id)
                if marketplace_order is None:
                    raise NotFoundError("Marketplace Order")
                if order.current_status is ClientOrderStatus.COMPLETED:
                    if marketplace_order.marketplace_status is not MarketplaceOrderStatus.COMPLETED:
                        raise DomainConflictError(
                            "Completed Client Order has an inconsistent Marketplace Order"
                        )
                    return ActionResultDTO(message="Order is already completed.")
                if marketplace_order.marketplace_status is MarketplaceOrderStatus.CANCELLED:
                    return ActionResultDTO(message="Marketplace order is already cancelled.")

                if (
                    marketplace_order.marketplace_status is MarketplaceOrderStatus.COMPLETED
                    and order.marketplace_cost is not None
                ):
                    snapshot = MarketplaceSyncResult(
                        external_order_id=marketplace_order.rbxcreate_order_id,
                        status=MarketplaceOrderStatus.COMPLETED,
                        purchased_quantity=marketplace_order.requested_robux,
                        remaining_quantity=0,
                        vendor_id=None,
                        price=order.marketplace_cost,
                        error_reason=None,
                        error_message=None,
                    )
                else:
                    status_check = await self._get_order_info_if_due(
                        session,
                        marketplace_order,
                    )
                    if status_check.skipped:
                        return ActionResultDTO(
                            message="Marketplace status check skipped; cached status retained."
                        )
                    snapshot = status_check.snapshot
                if (
                    marketplace_order.marketplace_status is MarketplaceOrderStatus.COMPLETED
                    and snapshot.status is not MarketplaceOrderStatus.COMPLETED
                ):
                    raise MarketplaceIntegrationError(
                        "RBXCrate status conflicts with the completed Marketplace Order"
                    )
                logger.info(
                    "marketplace_order_synchronized",
                    extra={
                        "order_id": str(order.id),
                        "customer_id": str(order.customer_id),
                        "marketplace_order_id": str(marketplace_order.id),
                        "external_order_id": marketplace_order.rbxcreate_order_id,
                        "requested_robux": order.requested_robux,
                        "synchronization_status": snapshot.status.value,
                    },
                )
                return await self._apply_synchronization(
                    session,
                    order,
                    marketplace_order,
                    snapshot,
                )
        except (DomainValidationError, DomainConflictError) as error:
            raise ConflictError(str(error)) from error

    async def synchronize_active_purchase(self, order_id: UUID) -> ActionResultDTO:
        """Synchronize the active external attempt associated with a Client Order."""
        async with self._sessions() as session:
            active = await MarketplaceOrderRepository(session).get_active_for_client_order(order_id)
            if active is None:
                raise ConflictError("The Client Order has no active Marketplace Order")
            marketplace_order_id = active.id
        return await self.synchronize_marketplace_order(marketplace_order_id)

    async def manual_requeue(self, order_id: UUID) -> ActionResultDTO:
        """Replace one active attempt through the shared guarded requeue transaction."""
        return await self._requeue_active(order_id, stock=None, automatic=False)

    async def automatic_requeue(
        self,
        order_id: UUID,
        stock: tuple[MarketplaceStock, ...],
    ) -> ActionResultDTO:
        """Replace one active attempt using the loop's consistent stock snapshot."""
        return await self._requeue_active(
            order_id,
            stock=stock,
            automatic=True,
        )

    async def fast_requeue(
        self,
        order_id: UUID,
        stock: tuple[MarketplaceStock, ...],
        *,
        cooldown_seconds: float,
    ) -> ActionResultDTO:
        """Start an eligible PreOrder; never replace an active purchase."""
        del cooldown_seconds
        async with self._sessions() as session:
            order = await ClientOrderRepository(session).get(order_id)
            if order is None:
                raise NotFoundError("Client Order")
            if order.current_status is ClientOrderStatus.PREORDER:
                now = self._clock()
                selected = _select_stock(
                    stock,
                    requested_robux=order.requested_robux,
                    minimum_purchase_rate=self._minimum_purchase_rate,
                    maximum_purchase_rate=effective_purchase_rate(order, now),
                )
                if selected is None:
                    return ActionResultDTO(
                        message="No suitable stock for the fast PreOrder trigger."
                    )
            elif order.current_status is ClientOrderStatus.PURCHASING:
                active = await MarketplaceOrderRepository(session).get_active_for_client_order(
                    order.id
                )
                now = self._clock()
                if active is not None and _purchase_age(active, now) < timedelta(
                    seconds=FRESH_PURCHASE_GUARD_SECONDS
                ):
                    logger.info(
                        "fast_requeue_skipped_recent_purchase",
                        extra=_recent_purchase_log_context(order.id, active, now),
                    )
                    return ActionResultDTO(message="Fresh purchase retained without requeue.")
                logger.info(
                    "fast_requeue_skipped_active_purchase",
                    extra={
                        "order_id": str(order.id),
                        "marketplace_order_id": (None if active is None else str(active.id)),
                    },
                )
                return ActionResultDTO(message="Active purchase retained without fast requeue.")
            else:
                return ActionResultDTO(message="Order is not eligible for the fast stock trigger.")
        result = await self.start_purchase(order_id, stock)
        logger.info(
            "fast_stock_trigger",
            extra={
                "order_id": str(order_id),
                "detected_rate": str(selected.rate),
                "previous_marketplace_order": None,
            },
        )
        return result

    async def _requeue_active(
        self,
        order_id: UUID,
        *,
        stock: tuple[MarketplaceStock, ...] | None,
        automatic: bool,
    ) -> ActionResultDTO:
        """Check, cancel, confirm, and replace one attempt under database row locks."""
        try:
            async with self._sessions.begin() as session:
                orders = ClientOrderRepository(session)
                order = await orders.get_for_update(order_id)
                if order is None:
                    raise NotFoundError("Client Order")
                if order.current_status is not ClientOrderStatus.PURCHASING:
                    if automatic:
                        return ActionResultDTO(
                            message="Order no longer requires automatic requeue."
                        )
                    raise DomainConflictError("Only an active purchase can be requeued")
                if automatic and order.automatic_requeue_enabled is False:
                    return ActionResultDTO(message="Automatic requeue is disabled for this order.")

                marketplace_orders = MarketplaceOrderRepository(session)
                active = await marketplace_orders.get_active_for_client_order_for_update(order.id)
                if active is None:
                    raise DomainConflictError("Purchasing order has no active Marketplace Order")
                if active.purchased_robux != 0:
                    raise DomainConflictError(
                        "An order with purchased Robux must be synchronized before requeueing"
                    )

                settings = await self._get_settings(session)
                now = self._clock()
                if _purchase_age(active, now) < timedelta(seconds=FRESH_PURCHASE_GUARD_SECONDS):
                    logger.info(
                        "fast_requeue_skipped_recent_purchase",
                        extra=_recent_purchase_log_context(order.id, active, now),
                    )
                    return ActionResultDTO(message="Fresh purchase retained without requeue.")
                delay = settings.auto_requeue_delay_seconds or Decimal("5")
                requeue_anchor = order.last_requeue_at or active.created_at
                if (
                    automatic
                    and requeue_anchor is not None
                    and now - requeue_anchor < timedelta(seconds=float(delay))
                ):
                    return ActionResultDTO(message="Automatic requeue delay has not elapsed.")

                customer = await CustomerRepository(session).get(order.customer_id)
                if customer is None:
                    raise NotFoundError("Customer")
                expected_active_id = active.id
                expected_external_id = active.rbxcreate_order_id
                status_check = await self._get_order_info_if_due(session, active)
                if status_check.skipped:
                    return ActionResultDTO(
                        message="Marketplace status check deferred; active order retained."
                    )
                if status_check.snapshot.status is not MarketplaceOrderStatus.ACTIVE:
                    return await self._apply_synchronization(
                        session,
                        order,
                        active,
                        status_check.snapshot,
                    )

                current_stock = await self._bridge.get_detailed_stock() if stock is None else stock
                selected = _select_stock(
                    current_stock,
                    requested_robux=order.requested_robux,
                    minimum_purchase_rate=self._minimum_purchase_rate,
                    maximum_purchase_rate=order.marketplace_rate_limit,
                )
                if selected is None:
                    message = (
                        "No suitable stock for automatic requeue."
                        if automatic
                        else "No suitable stock is available; the active order was retained."
                    )
                    return ActionResultDTO(message=message)

                attempt_number = (order.requeue_attempts or 0) + 2
                if automatic:
                    logger.info(
                        "auto_requeue_started",
                        extra={
                            "order_id": str(order.id),
                            "marketplace_order_id": str(active.id),
                            "external_order_id": active.rbxcreate_order_id,
                            "customer": customer.current_username,
                            "requested_robux": order.requested_robux,
                            "requeue_attempt": attempt_number,
                        },
                    )
                    if _notification_enabled(settings, NotificationType.AUTO_REQUEUE_STARTED):
                        await NotificationRepository(session).save(
                            Notification(
                                client_order_id=order.id,
                                notification_type=NotificationType.AUTO_REQUEUE_STARTED,
                                title="Auto Requeue Started",
                                message=_format_auto_requeue_started_notification(
                                    customer.current_username,
                                    order,
                                    active.rbxcreate_order_id,
                                    delay,
                                    attempt_number,
                                ),
                                delivery_status=NotificationDeliveryStatus.PENDING,
                            )
                        )

                try:
                    await self._bridge.cancel_order(active.rbxcreate_order_id)
                except MarketplaceCancellationUnsupportedError as error:
                    logger.warning(
                        "requeue_cancel_skipped_unsupported_status",
                        extra={
                            "order_id": str(order.id),
                            "marketplace_order_id": str(active.id),
                            "rbxcreate_order_id": active.rbxcreate_order_id,
                            "rbxcrate_http_status": error.status_code,
                            "rbxcrate_error_type": error.error_type,
                            "current_marketplace_status": active.marketplace_status.value,
                        },
                    )
                    return ActionResultDTO(
                        message="RBXCrate no longer allows cancellation; active order retained."
                    )
                if (
                    active.id != expected_active_id
                    or active.rbxcreate_order_id != expected_external_id
                ):
                    raise DomainConflictError("The active Marketplace Order changed concurrently")

                confirmed_status = _cached_sync_result(
                    active,
                    status=MarketplaceOrderStatus.CANCELLED,
                )
                await self._apply_synchronization(
                    session,
                    order,
                    active,
                    confirmed_status,
                )
                start_purchasing(order)
                external = await self._bridge.create_gamepass_order(
                    roblox_username=customer.current_username,
                    order_id=str(uuid4()),
                    robux_amount=order.requested_robux,
                    place_id=order.current_place_id,
                )
                if external.status is not MarketplaceOrderStatus.ACTIVE:
                    raise MarketplaceIntegrationError(
                        "RBXCrate returned a terminal status while requeueing the order"
                    )
                replacement = create_marketplace_order(
                    order,
                    MarketplaceOrderResult(
                        external_order_id=external.external_order_id,
                        purchase_rate=selected.rate,
                        requested_robux=order.requested_robux,
                    ),
                    active_order_exists=False,
                )
                requeue_time = self._clock()
                replacement.purchase_started_at = requeue_time
                order.last_requeue_at = requeue_time
                order.requeue_attempts = (order.requeue_attempts or 0) + 1
                await orders.save(order)
                await marketplace_orders.save(replacement)
                timeline = TimelineEventRepository(session)
                await timeline.save(
                    create_timeline_event(
                        order,
                        (
                            TimelineEventType.AUTOMATIC_REORDER
                            if automatic
                            else TimelineEventType.MANUAL_REORDER
                        ),
                        (
                            "Automation replaced the cancelled Marketplace Order."
                            if automatic
                            else "Operator cancelled the active attempt and requeued the order."
                        ),
                        requeue_time + timedelta(microseconds=1),
                    )
                )
                await timeline.save(
                    create_timeline_event(
                        order,
                        TimelineEventType.MARKETPLACE_ORDER_CREATED,
                        "Replacement Marketplace Order created through RBXCrate.",
                        requeue_time + timedelta(microseconds=2),
                    )
                )
                if automatic and _notification_enabled(
                    settings,
                    NotificationType.AUTO_REQUEUE_COMPLETED,
                ):
                    await NotificationRepository(session).save(
                        Notification(
                            client_order_id=order.id,
                            notification_type=NotificationType.AUTO_REQUEUE_COMPLETED,
                            title="Auto Requeue Completed",
                            message=_format_auto_requeue_completed_notification(
                                customer.current_username,
                                order,
                                active.rbxcreate_order_id,
                                replacement.rbxcreate_order_id,
                            ),
                            delivery_status=NotificationDeliveryStatus.PENDING,
                        )
                    )
                if automatic:
                    logger.info(
                        "auto_requeue_completed",
                        extra={
                            "order_id": str(order.id),
                            "marketplace_order_id": str(replacement.id),
                            "external_order_id": replacement.rbxcreate_order_id,
                            "customer": customer.current_username,
                            "requested_robux": order.requested_robux,
                            "previous_marketplace_order_id": str(active.id),
                            "new_marketplace_order_id": str(replacement.id),
                            "requeue_attempt": attempt_number,
                        },
                    )
        except (DomainValidationError, DomainConflictError) as error:
            raise ConflictError(str(error)) from error
        except IntegrityError as error:
            raise ConflictError("The order changed concurrently; please refresh") from error
        return ActionResultDTO(
            message=(
                "Marketplace Order automatically requeued."
                if automatic
                else "Active Marketplace Order was requeued."
            )
        )

    async def cancel_active_purchase(self, order_id: UUID) -> ActionResultDTO:
        """Cancel an active external attempt, or the Client Order when none exists."""
        try:
            async with self._sessions.begin() as session:
                orders = ClientOrderRepository(session)
                order = await orders.get_for_update(order_id)
                if order is None:
                    raise NotFoundError("Client Order")
                active = await MarketplaceOrderRepository(
                    session
                ).get_active_for_client_order_for_update(order_id)
                if active is not None:
                    now = self._clock()
                    if _purchase_age(active, now) < timedelta(seconds=FRESH_PURCHASE_GUARD_SECONDS):
                        logger.info(
                            "fast_requeue_skipped_recent_purchase",
                            extra=_recent_purchase_log_context(order.id, active, now),
                        )
                        return ActionResultDTO(message="Fresh purchase cannot be cancelled yet.")
                    active_id = active.id
                    external_order_id = active.rbxcreate_order_id
                elif order.current_status is ClientOrderStatus.CANCELLED:
                    return ActionResultDTO(message="Order is already cancelled.")
                else:
                    active_id = None
                    external_order_id = None
                    now = self._clock()
                    cancel_order(order, now)
                    await orders.save(order)
                    await TimelineEventRepository(session).save(
                        create_timeline_event(
                            order,
                            TimelineEventType.ORDER_CANCELLED,
                            "Client Order cancelled by the operator.",
                            now,
                        )
                    )
                    await self._save_order_cancelled_notification(session, order)
        except (DomainValidationError, DomainConflictError) as error:
            raise ConflictError(str(error)) from error

        if active_id is not None and external_order_id is not None:
            try:
                await self._bridge.cancel_order(external_order_id)
            except MarketplaceCancellationUnsupportedError as error:
                logger.warning(
                    "cancel_skipped_unsupported_status",
                    extra={
                        "order_id": str(order_id),
                        "marketplace_order_id": str(active_id),
                        "rbxcreate_order_id": external_order_id,
                        "rbxcrate_http_status": error.status_code,
                        "rbxcrate_error_type": error.error_type,
                    },
                )
                return ActionResultDTO(
                    message="RBXCrate no longer allows cancellation; active order retained."
                )
            async with self._sessions.begin() as session:
                orders = ClientOrderRepository(session)
                order = await orders.get_for_update(order_id)
                if order is None:
                    raise NotFoundError("Client Order")
                marketplace_orders = MarketplaceOrderRepository(session)
                active = await marketplace_orders.get_for_update(active_id)
                if (
                    active is None
                    or active.rbxcreate_order_id != external_order_id
                    or active.marketplace_status is not MarketplaceOrderStatus.ACTIVE
                ):
                    return ActionResultDTO(
                        message="Marketplace order changed while cancellation was in progress."
                    )
                await self._apply_synchronization(
                    session,
                    order,
                    active,
                    _cached_sync_result(
                        active,
                        status=MarketplaceOrderStatus.CANCELLED,
                    ),
                )
                if order.current_status is not ClientOrderStatus.PREORDER:
                    raise ConflictError(
                        "RBXCrate has not confirmed cancellation; the Client Order remains active"
                    )
                now = self._clock()
                cancel_order(order, now)
                await orders.save(order)
                await TimelineEventRepository(session).save(
                    create_timeline_event(
                        order,
                        TimelineEventType.ORDER_CANCELLED,
                        "Client Order cancelled after RBXCrate confirmed cancellation.",
                        now,
                    )
                )
                await self._save_order_cancelled_notification(session, order)
            return ActionResultDTO(message="Order cancelled.")
        return ActionResultDTO(message="Order cancelled.")

    async def _get_order_info_if_due(
        self,
        session: AsyncSession,
        marketplace_order: MarketplaceOrder,
    ) -> _StatusCheckOutcome:
        """Poll one external status only after its persisted guards have elapsed."""
        now = self._clock()
        cached = _cached_sync_result(marketplace_order)
        purchase_age = _purchase_age(marketplace_order, now)
        if purchase_age < timedelta(seconds=FRESH_PURCHASE_GUARD_SECONDS):
            logger.info(
                "marketplace_status_check_skipped_recent_purchase",
                extra={
                    **_recent_purchase_log_context(
                        marketplace_order.client_order_id,
                        marketplace_order,
                        now,
                    ),
                    "status_check_cooldown_remaining_ms": max(
                        0,
                        int(
                            (
                                timedelta(seconds=FRESH_PURCHASE_GUARD_SECONDS) - purchase_age
                            ).total_seconds()
                            * 1000
                        ),
                    ),
                },
            )
            return _StatusCheckOutcome(cached, skipped=True)
        if (
            marketplace_order.status_check_backoff_until is not None
            and now < marketplace_order.status_check_backoff_until
        ):
            logger.warning(
                "marketplace_status_check_skipped_backoff",
                extra={
                    "order_id": str(marketplace_order.client_order_id),
                    "marketplace_order_id": str(marketplace_order.id),
                    "rbxcreate_order_id": marketplace_order.rbxcreate_order_id,
                    "backoff_remaining_ms": int(
                        (marketplace_order.status_check_backoff_until - now).total_seconds() * 1000
                    ),
                },
            )
            return _StatusCheckOutcome(cached, skipped=True)
        if (
            marketplace_order.last_status_check_at is not None
            and now - marketplace_order.last_status_check_at
            < timedelta(seconds=STATUS_CHECK_COOLDOWN_SECONDS)
        ):
            return _StatusCheckOutcome(cached, skipped=True)
        try:
            snapshot = await self._bridge.get_order_info(marketplace_order.rbxcreate_order_id)
        except MarketplaceRateLimitedError as error:
            consecutive = (marketplace_order.status_check_rate_limit_count or 0) + 1
            backoff_seconds = STATUS_CHECK_BACKOFF_SECONDS[min(consecutive - 1, 2)]
            marketplace_order.last_status_check_at = now
            marketplace_order.status_check_rate_limit_count = consecutive
            marketplace_order.status_check_backoff_until = now + timedelta(seconds=backoff_seconds)
            await MarketplaceOrderRepository(session).save(marketplace_order)
            logger.warning(
                "rbxcrate_status_rate_limited",
                extra={
                    "order_id": str(marketplace_order.client_order_id),
                    "marketplace_order_id": str(marketplace_order.id),
                    "rbxcreate_order_id": marketplace_order.rbxcreate_order_id,
                    "rbxcrate_http_status": error.status_code,
                    "rbxcrate_error_type": error.error_type,
                    "backoff_seconds": backoff_seconds,
                    "consecutive_rate_limits": consecutive,
                },
            )
            return _StatusCheckOutcome(cached, skipped=True)
        marketplace_order.last_status_check_at = now
        marketplace_order.status_check_rate_limit_count = 0
        marketplace_order.status_check_backoff_until = None
        await MarketplaceOrderRepository(session).save(marketplace_order)
        return _StatusCheckOutcome(snapshot)

    async def _save_order_cancelled_notification(
        self,
        session: AsyncSession,
        order: ClientOrder,
    ) -> None:
        settings = await self._get_settings(session)
        customer = await CustomerRepository(session).get(order.customer_id)
        if customer is None:
            raise NotFoundError("Customer")
        logger.info(
            "order_cancelled",
            extra={
                "order_id": str(order.id),
                "customer": customer.current_username,
                "requested_robux": order.requested_robux,
            },
        )
        if not _notification_enabled(settings, NotificationType.ORDER_CANCELLED):
            return
        await NotificationRepository(session).save(
            Notification(
                client_order_id=order.id,
                notification_type=NotificationType.ORDER_CANCELLED,
                title="Order Cancelled",
                message=(
                    "<b>❌ Order Cancelled</b>\n\n"
                    f"Customer: {escape(customer.current_username)}\n"
                    f"Order: {order.requested_robux} R$\n"
                    f"Order ID: <code>{order.id}</code>"
                ),
                delivery_status=NotificationDeliveryStatus.PENDING,
            )
        )

    async def _apply_synchronization(
        self,
        session: AsyncSession,
        order: ClientOrder,
        marketplace_order: MarketplaceOrder,
        snapshot: MarketplaceSyncResult,
    ) -> ActionResultDTO:
        marketplace_orders = MarketplaceOrderRepository(session)
        orders = ClientOrderRepository(session)
        timeline = TimelineEventRepository(session)
        now = self._clock()

        if snapshot.status is MarketplaceOrderStatus.ACTIVE:
            if snapshot.purchased_quantity is not None and snapshot.remaining_quantity is not None:
                update_marketplace_progress(
                    marketplace_order,
                    purchased_robux=snapshot.purchased_quantity,
                    remaining_robux=snapshot.remaining_quantity,
                )
            if snapshot.price is not None:
                record_observed_marketplace_cost(order, snapshot.price)
                await orders.save(order)
            await marketplace_orders.save(marketplace_order)
            return ActionResultDTO(message="Marketplace order synchronized.")

        if snapshot.status is MarketplaceOrderStatus.COMPLETED:
            marketplace_cost = order.marketplace_cost if snapshot.price is None else snapshot.price
            if marketplace_cost is None:
                raise MarketplaceIntegrationError(
                    "RBXCrate completion is missing the marketplace price"
                )
            settings = await self._get_settings(session)
            customer_receives = calculate_customer_receives(
                order.requested_robux,
                tax_rate=self._finance_policy.roblox_tax_rate,
                rounding=self._finance_policy.robux_rounding,
            )
            financials = calculate_financial_snapshot(
                marketplace_cost=marketplace_cost,
                commission_rate=settings.marketplace_commission,
                usd_exchange_rate=settings.usd_exchange_rate,
                money_quantum=self._finance_policy.money_quantum,
                rounding=self._finance_policy.money_rounding,
            )
            purchase_result = create_purchase_result(
                requested_rate=marketplace_order.purchase_rate,
                purchased_robux=marketplace_order.requested_robux,
                financials=financials,
            )
            marketplace_completed_now = (
                marketplace_order.marketplace_status is MarketplaceOrderStatus.ACTIVE
            )
            if marketplace_completed_now:
                complete_marketplace_order(
                    marketplace_order,
                    purchased_robux=marketplace_order.requested_robux,
                    now=now,
                )
            elif marketplace_order.marketplace_status is not MarketplaceOrderStatus.COMPLETED:
                raise DomainConflictError("Marketplace Order cannot be completed")
            complete_order(
                order,
                customer_receives=customer_receives,
                marketplace_cost=financials.marketplace_cost,
                marketplace_commission=financials.marketplace_commission,
                final_cost_usd=financials.final_cost_usd,
                final_cost_local_currency=financials.final_cost_local_currency,
                usd_exchange_rate=financials.usd_exchange_rate,
                now=now,
                executed_rate=purchase_result.executed_rate,
            )
            await marketplace_orders.save(marketplace_order)
            await orders.save(order)
            customer = await CustomerRepository(session).get(order.customer_id)
            if customer is None:
                raise NotFoundError("Customer")
            remembered = await UserPlaceCacheRepository(session).get_by_username_for_update(
                customer.current_username
            )
            if remembered is not None and remembered.place_id == order.current_place_id:
                remembered.last_used_at = now
                await UserPlaceCacheRepository(session).save(remembered)
            if marketplace_completed_now:
                logger.info(
                    "purchase_completed",
                    extra={
                        "order_id": str(order.id),
                        "marketplace_order_id": str(marketplace_order.id),
                        "external_order_id": marketplace_order.rbxcreate_order_id,
                        "customer": customer.current_username,
                        "requested_robux": order.requested_robux,
                    },
                )
                if _notification_enabled(settings, NotificationType.PURCHASE_COMPLETED):
                    await NotificationRepository(session).save(
                        Notification(
                            client_order_id=order.id,
                            notification_type=NotificationType.PURCHASE_COMPLETED,
                            title="Purchase Completed",
                            message=_format_purchase_completed_notification(
                                order,
                                marketplace_order,
                                customer.current_username,
                                settings.marketplace_commission,
                                purchase_result,
                            ),
                            delivery_status=NotificationDeliveryStatus.PENDING,
                        )
                    )
            if marketplace_completed_now:
                await timeline.save(
                    create_timeline_event(
                        order,
                        TimelineEventType.MARKETPLACE_ORDER_COMPLETED,
                        "RBXCrate confirmed successful execution.",
                        now,
                    )
                )
            await timeline.save(
                create_timeline_event(
                    order,
                    TimelineEventType.ORDER_COMPLETED,
                    "Client Order completed with historical financial values.",
                    now + timedelta(microseconds=1),
                )
            )
            return ActionResultDTO(message="Order completed successfully.")

        cancel_marketplace_order(
            marketplace_order,
            purchased_robux=(
                marketplace_order.purchased_robux
                if snapshot.purchased_quantity is None
                else snapshot.purchased_quantity
            ),
            remaining_robux=(
                marketplace_order.remaining_robux
                if snapshot.remaining_quantity is None
                else snapshot.remaining_quantity
            ),
            now=now,
        )
        return_to_preorder(order)
        await marketplace_orders.save(marketplace_order)
        await orders.save(order)
        await timeline.save(
            create_timeline_event(
                order,
                TimelineEventType.MARKETPLACE_ORDER_CANCELLED,
                "RBXCrate ended the attempt; Client Order returned to PreOrder.",
                now,
            )
        )
        return ActionResultDTO(message="Active purchase cancelled; order returned to PreOrder.")

    async def _get_settings(self, session: AsyncSession) -> SystemSettings:
        repository = SystemSettingsRepository(session)
        settings = await repository.get_current()
        if settings is not None:
            return settings
        if self._settings_defaults is None:
            raise MarketplaceIntegrationError("System Settings are not initialized")
        return await repository.save(create_settings(self._settings_defaults))


def _select_stock(
    stock: tuple[MarketplaceStock, ...],
    *,
    requested_robux: int,
    minimum_purchase_rate: Decimal,
    maximum_purchase_rate: Decimal,
) -> MarketplaceStock | None:
    eligible = [
        item
        for item in stock
        if item.rate >= minimum_purchase_rate
        and item.rate <= maximum_purchase_rate
        and item.max_instant_order >= requested_robux
        and item.total_robux_amount >= requested_robux
    ]
    ordered = sorted(
        eligible,
        key=lambda item: (item.rate, -item.total_robux_amount),
    )
    return ordered[0] if ordered else None


def _purchase_age(marketplace_order: MarketplaceOrder, now: datetime) -> timedelta:
    started_at = marketplace_order.purchase_started_at or marketplace_order.created_at
    if started_at is None:
        return timedelta.max
    return max(timedelta(), now - started_at)


def _recent_purchase_log_context(
    order_id: UUID,
    marketplace_order: MarketplaceOrder,
    now: datetime,
) -> dict[str, str | int]:
    return {
        "order_id": str(order_id),
        "marketplace_order_id": str(marketplace_order.id),
        "age_ms": int(_purchase_age(marketplace_order, now).total_seconds() * 1000),
    }


def _cached_sync_result(
    marketplace_order: MarketplaceOrder,
    *,
    status: MarketplaceOrderStatus | None = None,
) -> MarketplaceSyncResult:
    cached_status = status or marketplace_order.marketplace_status
    return MarketplaceSyncResult(
        external_order_id=marketplace_order.rbxcreate_order_id,
        status=cached_status,
        purchased_quantity=marketplace_order.purchased_robux,
        remaining_quantity=marketplace_order.remaining_robux,
        vendor_id=None,
        price=None,
        error_reason=None,
        error_message=None,
    )


def _select_preorders_maximum_clients(
    candidates: tuple[tuple[UUID, int], ...],
    stock: tuple[MarketplaceStock, ...],
    *,
    minimum_purchase_rate: Decimal,
    maximum_purchase_rate: Decimal,
) -> tuple[tuple[UUID, ...], MarketplaceStock | None]:
    """Greedily fit the smallest complete orders into eligible stock tiers."""
    remaining = [item.total_robux_amount for item in stock]
    selected_ids: list[UUID] = []
    notification_stock: MarketplaceStock | None = None
    for order_id, requested_robux in sorted(candidates, key=lambda item: (item[1], item[0])):
        eligible_indexes = [
            index
            for index, item in enumerate(stock)
            if item.rate >= minimum_purchase_rate
            and item.rate <= maximum_purchase_rate
            and item.max_instant_order >= requested_robux
            and remaining[index] >= requested_robux
        ]
        if not eligible_indexes:
            continue
        selected_index = min(
            eligible_indexes,
            key=lambda index: (stock[index].rate, -remaining[index]),
        )
        remaining[selected_index] -= requested_robux
        selected_ids.append(order_id)
        if notification_stock is None:
            notification_stock = stock[selected_index]
    return tuple(selected_ids), notification_stock


def _select_preorders_by_order_limit(
    candidates: tuple[tuple[UUID, int, Decimal], ...],
    stock: tuple[MarketplaceStock, ...],
    *,
    minimum_purchase_rate: Decimal,
) -> tuple[tuple[UUID, ...], MarketplaceStock | None]:
    """Fit smallest orders while respecting each order's current preferred/fallback limit."""
    remaining = [item.total_robux_amount for item in stock]
    selected_ids: list[UUID] = []
    notification_stock: MarketplaceStock | None = None
    for order_id, requested_robux, order_limit in sorted(
        candidates,
        key=lambda item: (item[1], item[0]),
    ):
        eligible_indexes = [
            index
            for index, item in enumerate(stock)
            if minimum_purchase_rate <= item.rate <= order_limit
            and item.max_instant_order >= requested_robux
            and remaining[index] >= requested_robux
        ]
        if not eligible_indexes:
            continue
        selected_index = min(
            eligible_indexes,
            key=lambda index: (stock[index].rate, -remaining[index]),
        )
        remaining[selected_index] -= requested_robux
        selected_ids.append(order_id)
        if notification_stock is None:
            notification_stock = stock[selected_index]
    return tuple(selected_ids), notification_stock


def _format_purchase_completed_notification(
    order: ClientOrder,
    marketplace_order: MarketplaceOrder,
    username: str,
    commission_rate: Decimal,
    purchase_result: PurchaseResult,
) -> str:
    """Format the completed order's immutable historical financial snapshot."""
    commission_percent = commission_rate * Decimal("100")
    executed_rate = purchase_result.executed_rate
    preferred_rate = order.preferred_rate or marketplace_order.purchase_rate
    warning = "\n⚠️ Executed above preferred rate" if executed_rate > preferred_rate else ""
    return (
        "<b>✅ Purchase completed</b>\n\n"
        f"👤 Username: {escape(username)}\n"
        f"🛒 Purchased: {marketplace_order.purchased_robux} R$\n"
        f"🎁 Client receives: {order.customer_receives} R$\n"
        f"🎯 Preferred trigger: {preferred_rate.normalize()}$\n"
        f"💰 Executed rate: {executed_rate.normalize()}$\n"
        f"💰 Marketplace price: ${(order.marketplace_cost or Decimal('0')):.2f}\n"
        f"🧾 +{commission_percent.normalize()}% commission: "
        f"${(order.marketplace_commission or Decimal('0')):.2f}\n"
        f"💳 Total paid: ${(order.final_cost_usd or Decimal('0')):.2f}\n"
        f"🇷🇺 Total RUB: {(order.final_cost_local_currency or Decimal('0')):.2f} ₽\n\n"
        f"Order: #{order.id.hex[:8].upper()}"
        f"{warning}"
    )


def _notification_enabled(settings: SystemSettings, category: NotificationType) -> bool:
    return settings.telegram_notifications_enabled and category in settings.notification_categories


def _format_auto_requeue_started_notification(
    username: str,
    order: ClientOrder,
    old_external_order_id: str,
    delay_seconds: Decimal,
    attempt_number: int,
) -> str:
    return (
        "<b>🔄 Auto Requeue Started</b>\n\n"
        f"Customer: {escape(username)}\n"
        f"Order: {order.requested_robux} R$\n"
        "Old marketplace order:\n"
        f"<code>{escape(old_external_order_id)}</code>\n"
        f"Reason: order remained ACTIVE for {delay_seconds.normalize()}s\n"
        f"Attempt: #{attempt_number}"
    )


def _format_auto_requeue_completed_notification(
    username: str,
    order: ClientOrder,
    old_external_order_id: str,
    new_external_order_id: str,
) -> str:
    return (
        "<b>✅ Auto Requeue Completed</b>\n\n"
        f"Customer: {escape(username)}\n"
        f"Order: {order.requested_robux} R$\n"
        f"Old order: <code>{escape(old_external_order_id)}</code>\n"
        f"New order: <code>{escape(new_external_order_id)}</code>\n"
        "Queue priority refreshed successfully."
    )
