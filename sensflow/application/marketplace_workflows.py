"""Transactional RBXCrate workflows for Client and Marketplace Orders."""

import logging
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sensflow.application.dto import ActionResultDTO
from sensflow.application.errors import (
    ConflictError,
    MarketplaceCancellationUnsupportedError,
    MarketplaceIntegrationError,
    NotFoundError,
)
from sensflow.application.rbxcreate_bridge import (
    MarketplaceStock,
    MarketplaceSyncResult,
    RbxcreateBridge,
)
from sensflow.domain.enums import ClientOrderStatus, MarketplaceOrderStatus, TimelineEventType
from sensflow.domain.errors import DomainConflictError, DomainValidationError
from sensflow.domain.finance.service import (
    calculate_customer_receives,
    calculate_financial_snapshot,
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
    cancel_order,
    complete_order,
    enter_preorder,
    return_to_preorder,
    start_purchasing,
)
from sensflow.domain.order.timeline import create_timeline_event
from sensflow.domain.settings.service import SettingsDefaults, create_settings
from sensflow.infrastructure.database.base import utc_now
from sensflow.infrastructure.database.models import ClientOrder, MarketplaceOrder, SystemSettings
from sensflow.repositories import (
    ClientOrderRepository,
    CustomerRepository,
    MarketplaceOrderRepository,
    SystemSettingsRepository,
    TimelineEventRepository,
)

SessionFactory = async_sessionmaker[AsyncSession]
Clock = Callable[[], datetime]
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FinancePolicy:
    """Non-persisted calculation rules required to finalize an automated purchase."""

    roblox_tax_rate: Decimal = Decimal("0.30")
    robux_rounding: str = ROUND_DOWN
    money_rounding: str = ROUND_HALF_UP
    money_quantum: Decimal = Decimal("0.0001")


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

    async def start_purchase(self, order_id: UUID) -> ActionResultDTO:
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
                if order.current_status is ClientOrderStatus.DRAFT:
                    await timeline.save(
                        create_timeline_event(
                            order,
                            TimelineEventType.PAYMENT_CONFIRMED,
                            "Customer payment confirmed.",
                            now,
                        )
                    )

                stock = await self._bridge.get_detailed_stock()
                selected = _select_stock(
                    stock,
                    requested_robux=order.requested_robux,
                    minimum_purchase_rate=self._minimum_purchase_rate,
                    maximum_purchase_rate=order.marketplace_rate_limit,
                )
                if selected is None:
                    if order.current_status is ClientOrderStatus.DRAFT:
                        enter_preorder(order)
                    await orders.save(order)
                    await timeline.save(
                        create_timeline_event(
                            order,
                            TimelineEventType.PREORDER_CREATED,
                            "No stock satisfies the quantity, instant-order, and rate limits.",
                            now + timedelta(microseconds=1),
                        )
                    )
                    logger.info(
                        "marketplace_purchase_deferred",
                        extra={
                            "order_id": str(order.id),
                            "customer_id": str(order.customer_id),
                            "requested_robux": order.requested_robux,
                        },
                    )
                    return ActionResultDTO(
                        message="No suitable stock available; order moved to PreOrder."
                    )

                customer = await CustomerRepository(session).get(order.customer_id)
                if customer is None:
                    raise NotFoundError("Customer")
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
                    snapshot = await self._bridge.get_order_info(
                        marketplace_order.rbxcreate_order_id
                    )
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
        except (DomainValidationError, DomainConflictError) as error:
            raise ConflictError(str(error)) from error

        if active_id is not None and external_order_id is not None:
            with suppress(MarketplaceCancellationUnsupportedError):
                await self._bridge.cancel_order(external_order_id)
            return await self.synchronize_marketplace_order(active_id)
        return ActionResultDTO(message="Order cancelled.")

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
            )
            await marketplace_orders.save(marketplace_order)
            await orders.save(order)
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
    suitable = (
        item
        for item in stock
        if item.rate >= minimum_purchase_rate
        and item.rate <= maximum_purchase_rate
        and item.max_instant_order >= requested_robux
        and item.total_robux_amount >= requested_robux
    )
    return min(
        suitable,
        key=lambda item: (item.rate, -item.total_robux_amount),
        default=None,
    )
