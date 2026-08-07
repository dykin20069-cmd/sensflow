"""Focused orchestration tests using repositories and an RBXCrate bridge fake."""

import asyncio
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import sensflow.application.marketplace_workflows as workflow_module
from sensflow.application.marketplace_workflows import MarketplaceWorkflows
from sensflow.application.rbxcreate_bridge import (
    MarketplaceCreateResult,
    MarketplaceStock,
    MarketplaceSyncResult,
)
from sensflow.domain.enums import ClientOrderStatus, MarketplaceOrderStatus
from sensflow.infrastructure.database.models import (
    ClientOrder,
    Customer,
    MarketplaceOrder,
    SystemSettings,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class SessionContext(AbstractAsyncContextManager[object]):
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *args: object) -> None:
        return None


class Sessions:
    def __call__(self) -> SessionContext:
        return SessionContext()

    def begin(self) -> SessionContext:
        return SessionContext()


class Bridge:
    def __init__(
        self,
        stock: tuple[MarketplaceStock, ...] = (),
        sync: MarketplaceSyncResult | None = None,
    ) -> None:
        self.stock = stock
        self.sync = sync
        self.create_calls: list[dict[str, object]] = []
        self.sync_calls = 0

    async def get_detailed_stock(self) -> tuple[MarketplaceStock, ...]:
        return self.stock

    async def create_gamepass_order(self, **values: object) -> MarketplaceCreateResult:
        self.create_calls.append(values)
        return MarketplaceCreateResult(
            external_order_id=str(values["order_id"]),
            status=MarketplaceOrderStatus.ACTIVE,
        )

    async def get_order_info(self, external_order_id: str) -> MarketplaceSyncResult:
        self.sync_calls += 1
        assert self.sync is not None
        return self.sync


def _customer() -> Customer:
    customer = Customer(
        roblox_user_id=9,
        current_username="builder",
        current_place_id=77,
    )
    customer.id = uuid4()
    return customer


def _order(customer: Customer, status: ClientOrderStatus) -> ClientOrder:
    order = ClientOrder(
        customer_id=customer.id,
        requested_robux=1000,
        current_status=status,
        current_place_id=77,
        marketplace_rate_limit=Decimal("2.50"),
    )
    order.id = uuid4()
    return order


def _attempt(order: ClientOrder) -> MarketplaceOrder:
    attempt = MarketplaceOrder(
        client_order_id=order.id,
        rbxcreate_order_id=str(order.id),
        marketplace_status=MarketplaceOrderStatus.ACTIVE,
        purchase_rate=Decimal("2.00"),
        requested_robux=1000,
        purchased_robux=0,
        remaining_robux=1000,
    )
    attempt.id = uuid4()
    return attempt


def _wire(
    monkeypatch: Any,
    *,
    customer: Customer,
    order: ClientOrder,
    attempt: MarketplaceOrder | None = None,
    maximum_purchase_rate: Decimal = Decimal("2.50"),
) -> SimpleNamespace:
    saved_marketplace: list[MarketplaceOrder] = []
    timeline: list[object] = []

    class Orders:
        async def get_for_update(self, order_id: object) -> ClientOrder | None:
            return order if order_id == order.id else None

        async def save(self, entity: ClientOrder) -> ClientOrder:
            return entity

    class Customers:
        async def get(self, customer_id: object) -> Customer | None:
            return customer if customer_id == customer.id else None

    class Marketplace:
        async def get(self, marketplace_id: object) -> MarketplaceOrder | None:
            return attempt if attempt is not None and marketplace_id == attempt.id else None

        async def get_for_update(self, marketplace_id: object) -> MarketplaceOrder | None:
            return await self.get(marketplace_id)

        async def get_active_for_client_order_for_update(
            self, client_order_id: object
        ) -> MarketplaceOrder | None:
            if (
                attempt is not None
                and attempt.client_order_id == client_order_id
                and attempt.marketplace_status is MarketplaceOrderStatus.ACTIVE
            ):
                return attempt
            return None

        async def save(self, entity: MarketplaceOrder) -> MarketplaceOrder:
            saved_marketplace.append(entity)
            return entity

    class Timeline:
        async def save(self, event: object) -> object:
            timeline.append(event)
            return event

    settings = SystemSettings(
        maximum_purchase_rate=maximum_purchase_rate,
        automatic_reorder_enabled=True,
        automatic_reorder_interval_seconds=60,
        marketplace_monitoring_interval_seconds=60,
        synchronization_interval_seconds=60,
        marketplace_commission=Decimal("0.10"),
        usd_exchange_rate=Decimal("90"),
        telegram_notifications_enabled=True,
        notification_categories=[],
        application_timezone="UTC",
    )

    class SettingsRepository:
        async def get_current(self) -> SystemSettings:
            return settings

    monkeypatch.setattr(workflow_module, "ClientOrderRepository", lambda session: Orders())
    monkeypatch.setattr(workflow_module, "CustomerRepository", lambda session: Customers())
    monkeypatch.setattr(
        workflow_module, "MarketplaceOrderRepository", lambda session: Marketplace()
    )
    monkeypatch.setattr(workflow_module, "TimelineEventRepository", lambda session: Timeline())
    monkeypatch.setattr(
        workflow_module, "SystemSettingsRepository", lambda session: SettingsRepository()
    )
    return SimpleNamespace(saved_marketplace=saved_marketplace, timeline=timeline)


def test_start_purchase_chooses_lowest_valid_rate_and_skips_overpriced(monkeypatch: Any) -> None:
    async def scenario() -> None:
        customer = _customer()
        order = _order(customer, ClientOrderStatus.DRAFT)
        state = _wire(monkeypatch, customer=customer, order=order)
        bridge = Bridge(
            stock=(
                MarketplaceStock(Decimal("1.00"), 1, 500, 5000),
                MarketplaceStock(Decimal("3.00"), 3, 5000, 5000),
                MarketplaceStock(Decimal("2.00"), 2, 5000, 5000),
                MarketplaceStock(Decimal("2.25"), 2, 5000, 5000),
            )
        )
        workflows = MarketplaceWorkflows(Sessions(), bridge, clock=lambda: NOW)  # type: ignore[arg-type]

        result = await workflows.start_purchase(order.id)

        assert result.message == "Purchase started via RBXCrate."
        assert order.current_status is ClientOrderStatus.PURCHASING
        assert state.saved_marketplace[-1].purchase_rate == Decimal("2.00")
        assert bridge.create_calls[0]["order_id"] == str(order.id)
        assert "gamepass_id" not in bridge.create_calls[0]

    asyncio.run(scenario())


def test_start_purchase_uses_current_rate_limit_for_existing_draft(monkeypatch: Any) -> None:
    async def scenario() -> None:
        customer = _customer()
        order = _order(customer, ClientOrderStatus.DRAFT)
        order.requested_robux = 100
        order.marketplace_rate_limit = Decimal("1.00")
        state = _wire(
            monkeypatch,
            customer=customer,
            order=order,
            maximum_purchase_rate=Decimal("4.5"),
        )
        bridge = Bridge(
            stock=(
                MarketplaceStock(Decimal("4.2"), 3, 427, 1325),
                MarketplaceStock(Decimal("4.3"), 25, 338, 9071),
                MarketplaceStock(Decimal("4.5"), 1, 257, 367),
            )
        )
        workflows = MarketplaceWorkflows(
            Sessions(),
            bridge,
            minimum_purchase_rate=Decimal("0"),
            clock=lambda: NOW,
        )  # type: ignore[arg-type]

        result = await workflows.start_purchase(order.id)

        assert result.message == "Purchase started via RBXCrate."
        assert order.marketplace_rate_limit == Decimal("4.5")
        assert state.saved_marketplace[-1].purchase_rate == Decimal("4.2")

    asyncio.run(scenario())


def test_start_purchase_moves_order_to_preorder_when_stock_is_insufficient(
    monkeypatch: Any,
) -> None:
    async def scenario() -> None:
        customer = _customer()
        order = _order(customer, ClientOrderStatus.DRAFT)
        _wire(monkeypatch, customer=customer, order=order)
        bridge = Bridge(stock=(MarketplaceStock(Decimal("1.00"), 1, 500, 500),))
        workflows = MarketplaceWorkflows(Sessions(), bridge, clock=lambda: NOW)  # type: ignore[arg-type]

        result = await workflows.start_purchase(order.id)

        assert "PreOrder" in result.message
        assert order.current_status is ClientOrderStatus.PREORDER
        assert bridge.create_calls == []

    asyncio.run(scenario())


def test_synchronization_completes_exactly_once(monkeypatch: Any) -> None:
    async def scenario() -> None:
        customer = _customer()
        order = _order(customer, ClientOrderStatus.PURCHASING)
        attempt = _attempt(order)
        _wire(monkeypatch, customer=customer, order=order, attempt=attempt)
        bridge = Bridge(
            sync=MarketplaceSyncResult(
                external_order_id=attempt.rbxcreate_order_id,
                status=MarketplaceOrderStatus.COMPLETED,
                purchased_quantity=1000,
                remaining_quantity=0,
                vendor_id=None,
                price=Decimal("10.00"),
                error_reason=None,
                error_message=None,
            )
        )
        workflows = MarketplaceWorkflows(Sessions(), bridge, clock=lambda: NOW)  # type: ignore[arg-type]

        first = await workflows.synchronize_marketplace_order(attempt.id)
        second = await workflows.synchronize_marketplace_order(attempt.id)

        assert first.message == "Order completed successfully."
        assert second.message == "Order is already completed."
        assert bridge.sync_calls == 1
        assert order.current_status is ClientOrderStatus.COMPLETED
        assert attempt.marketplace_status is MarketplaceOrderStatus.COMPLETED
        assert order.marketplace_cost == Decimal("10.0000")

    asyncio.run(scenario())


def test_synchronization_returns_to_preorder_on_external_error(monkeypatch: Any) -> None:
    async def scenario() -> None:
        customer = _customer()
        order = _order(customer, ClientOrderStatus.PURCHASING)
        attempt = _attempt(order)
        _wire(monkeypatch, customer=customer, order=order, attempt=attempt)
        bridge = Bridge(
            sync=MarketplaceSyncResult(
                external_order_id=attempt.rbxcreate_order_id,
                status=MarketplaceOrderStatus.CANCELLED,
                purchased_quantity=None,
                remaining_quantity=None,
                vendor_id=None,
                price=None,
                error_reason="remote_error",
                error_message="not exposed",
            )
        )
        workflows = MarketplaceWorkflows(Sessions(), bridge, clock=lambda: NOW)  # type: ignore[arg-type]

        await workflows.synchronize_marketplace_order(attempt.id)

        assert order.current_status is ClientOrderStatus.PREORDER
        assert attempt.marketplace_status is MarketplaceOrderStatus.CANCELLED

    asyncio.run(scenario())
