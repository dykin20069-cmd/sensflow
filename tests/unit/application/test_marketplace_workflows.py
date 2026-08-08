"""Focused orchestration tests using repositories and an RBXCrate bridge fake."""

import asyncio
import logging
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

import sensflow.application.marketplace_workflows as workflow_module
from sensflow.application.errors import ConflictError
from sensflow.application.marketplace_workflows import (
    MarketplaceWorkflows,
    _format_purchase_completed_notification,
)
from sensflow.application.rbxcreate_bridge import (
    MarketplaceCreateResult,
    MarketplaceStock,
    MarketplaceSyncResult,
)
from sensflow.domain.enums import ClientOrderStatus, MarketplaceOrderStatus
from sensflow.domain.finance.service import PurchaseResult
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
        sync_results: tuple[MarketplaceSyncResult, ...] = (),
    ) -> None:
        self.stock = stock
        self.sync = sync
        self.sync_results = list(sync_results)
        self.create_calls: list[dict[str, object]] = []
        self.cancel_calls: list[str] = []
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
        if self.sync_results:
            return self.sync_results.pop(0)
        assert self.sync is not None
        return self.sync

    async def cancel_order(self, external_order_id: str) -> None:
        self.cancel_calls.append(external_order_id)


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
        fallback_active=False,
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


def _active_then_cancelled(attempt: MarketplaceOrder) -> tuple[MarketplaceSyncResult, ...]:
    return (
        MarketplaceSyncResult(
            attempt.rbxcreate_order_id,
            MarketplaceOrderStatus.ACTIVE,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
        MarketplaceSyncResult(
            attempt.rbxcreate_order_id,
            MarketplaceOrderStatus.CANCELLED,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
    )


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

    class PlaceCache:
        async def get_by_username_for_update(self, username: str) -> None:
            return None

    settings = SystemSettings(
        maximum_purchase_rate=maximum_purchase_rate,
        preferred_purchase_rate=min(maximum_purchase_rate, Decimal("4.3")),
        preferred_timeout_minutes=35,
        low_balance_threshold=Decimal("10"),
        critical_balance_threshold=Decimal("5"),
        stock_notifications_enabled=True,
        automatic_reorder_enabled=True,
        automatic_reorder_interval_seconds=60,
        auto_requeue_delay_seconds=Decimal("5"),
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
        workflow_module,
        "UserPlaceCacheRepository",
        lambda session: PlaceCache(),
    )
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


def test_start_purchase_preserves_the_order_rate_policy_snapshot(monkeypatch: Any) -> None:
    async def scenario() -> None:
        customer = _customer()
        order = _order(customer, ClientOrderStatus.DRAFT)
        order.requested_robux = 100
        order.marketplace_rate_limit = Decimal("4.4")
        order.preferred_rate = Decimal("4.3")
        order.preferred_timeout_minutes = 35
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
        assert order.marketplace_rate_limit == Decimal("4.4")
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


def test_preferred_rate_defers_then_uses_maximum_after_timeout(monkeypatch: Any) -> None:
    async def scenario() -> None:
        customer = _customer()
        order = _order(customer, ClientOrderStatus.DRAFT)
        order.requested_robux = 100
        order.marketplace_rate_limit = Decimal("4.5")
        order.preferred_rate = Decimal("4.1")
        order.preferred_timeout_minutes = 35
        state = _wire(
            monkeypatch,
            customer=customer,
            order=order,
            maximum_purchase_rate=Decimal("4.5"),
        )
        bridge = Bridge(stock=(MarketplaceStock(Decimal("4.2"), 3, 427, 1325),))
        current_time = [NOW]
        workflows = MarketplaceWorkflows(
            Sessions(),
            bridge,
            clock=lambda: current_time[0],
        )  # type: ignore[arg-type]

        waiting = await workflows.start_purchase(order.id)

        assert order.current_status is ClientOrderStatus.PREORDER
        assert order.preferred_expires_at == NOW + timedelta(minutes=35)
        assert order.fallback_active is False
        assert "PreOrder" in waiting.message
        assert bridge.create_calls == []

        current_time[0] = NOW + timedelta(minutes=35)
        started = await workflows.start_purchase(order.id)

        assert started.message == "Purchase started via RBXCrate."
        assert order.fallback_active is True
        assert order.current_status is ClientOrderStatus.PURCHASING
        assert state.saved_marketplace[-1].purchase_rate == Decimal("4.2")

    asyncio.run(scenario())


def test_quick_mode_starts_immediately_above_the_preferred_rate(monkeypatch: Any) -> None:
    async def scenario() -> None:
        customer = _customer()
        order = _order(customer, ClientOrderStatus.DRAFT)
        order.requested_robux = 857
        order.marketplace_rate_limit = Decimal("4.5")
        order.preferred_rate = None
        order.preferred_timeout_minutes = None
        order.fallback_active = True
        state = _wire(
            monkeypatch,
            customer=customer,
            order=order,
            maximum_purchase_rate=Decimal("4.5"),
        )
        bridge = Bridge(stock=(MarketplaceStock(Decimal("4.5"), 3, 1_000, 2_000),))
        workflows = MarketplaceWorkflows(Sessions(), bridge, clock=lambda: NOW)  # type: ignore[arg-type]

        result = await workflows.start_purchase(order.id)

        assert result.message == "Purchase started via RBXCrate."
        assert order.current_status is ClientOrderStatus.PURCHASING
        assert state.saved_marketplace[-1].purchase_rate == Decimal("4.5")

    asyncio.run(scenario())


def test_manual_requeue_cancels_and_replaces_active_attempt_atomically(
    monkeypatch: Any,
) -> None:
    async def scenario() -> None:
        customer = _customer()
        order = _order(customer, ClientOrderStatus.PURCHASING)
        attempt = _attempt(order)
        attempt.created_at = NOW - timedelta(seconds=5)
        state = _wire(monkeypatch, customer=customer, order=order, attempt=attempt)
        bridge = Bridge(
            stock=(MarketplaceStock(Decimal("2.00"), 2, 5000, 5000),),
            sync_results=(
                MarketplaceSyncResult(
                    attempt.rbxcreate_order_id,
                    MarketplaceOrderStatus.ACTIVE,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
                MarketplaceSyncResult(
                    attempt.rbxcreate_order_id,
                    MarketplaceOrderStatus.CANCELLED,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            ),
        )
        workflows = MarketplaceWorkflows(Sessions(), bridge, clock=lambda: NOW)  # type: ignore[arg-type]

        result = await workflows.manual_requeue(order.id)

        replacement = state.saved_marketplace[-1]
        assert result.message == "Active Marketplace Order was requeued."
        assert bridge.cancel_calls == [attempt.rbxcreate_order_id]
        assert attempt.marketplace_status is MarketplaceOrderStatus.CANCELLED
        assert replacement is not attempt
        assert replacement.marketplace_status is MarketplaceOrderStatus.ACTIVE
        assert order.current_status is ClientOrderStatus.PURCHASING

    asyncio.run(scenario())


def test_automatic_requeue_checks_status_then_replaces_once(monkeypatch: Any) -> None:
    async def scenario() -> None:
        customer = _customer()
        order = _order(customer, ClientOrderStatus.PURCHASING)
        attempt = _attempt(order)
        attempt.created_at = NOW - timedelta(seconds=5)
        state = _wire(monkeypatch, customer=customer, order=order, attempt=attempt)
        bridge = Bridge(
            sync_results=(
                MarketplaceSyncResult(
                    attempt.rbxcreate_order_id,
                    MarketplaceOrderStatus.ACTIVE,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
                MarketplaceSyncResult(
                    attempt.rbxcreate_order_id,
                    MarketplaceOrderStatus.CANCELLED,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            )
        )
        workflows = MarketplaceWorkflows(Sessions(), bridge, clock=lambda: NOW)  # type: ignore[arg-type]

        result = await workflows.automatic_requeue(
            order.id,
            (MarketplaceStock(Decimal("2.00"), 2, 5000, 5000),),
        )

        assert result.message == "Marketplace Order automatically requeued."
        assert bridge.sync_calls == 2
        assert bridge.cancel_calls == [attempt.rbxcreate_order_id]
        assert len(bridge.create_calls) == 1
        assert attempt.marketplace_status is MarketplaceOrderStatus.CANCELLED
        assert state.saved_marketplace[-1].marketplace_status is MarketplaceOrderStatus.ACTIVE

    asyncio.run(scenario())


def test_automatic_requeue_waits_for_configured_five_second_delay(monkeypatch: Any) -> None:
    async def scenario() -> None:
        customer = _customer()
        order = _order(customer, ClientOrderStatus.PURCHASING)
        attempt = _attempt(order)
        attempt.created_at = NOW - timedelta(seconds=4)
        _wire(monkeypatch, customer=customer, order=order, attempt=attempt)
        bridge = Bridge(
            stock=(MarketplaceStock(Decimal("2.00"), 2, 5000, 5000),),
        )
        workflows = MarketplaceWorkflows(Sessions(), bridge, clock=lambda: NOW)  # type: ignore[arg-type]

        result = await workflows.automatic_requeue(order.id, bridge.stock)

        assert result.message == "Automatic requeue delay has not elapsed."
        assert bridge.sync_calls == 0
        assert bridge.cancel_calls == []
        assert bridge.create_calls == []

    asyncio.run(scenario())


def test_fast_trigger_requeues_preferred_order_at_or_below_preferred_rate(
    monkeypatch: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        customer = _customer()
        order = _order(customer, ClientOrderStatus.PURCHASING)
        order.marketplace_rate_limit = Decimal("4.5")
        order.preferred_rate = Decimal("4.3")
        order.preferred_timeout_minutes = 35
        order.fallback_active = False
        attempt = _attempt(order)
        attempt.created_at = NOW
        state = _wire(
            monkeypatch,
            customer=customer,
            order=order,
            attempt=attempt,
            maximum_purchase_rate=Decimal("4.5"),
        )
        stock = (MarketplaceStock(Decimal("4.2"), 2, 5_000, 5_000),)
        bridge = Bridge(stock=stock, sync_results=_active_then_cancelled(attempt))
        workflows = MarketplaceWorkflows(Sessions(), bridge, clock=lambda: NOW)  # type: ignore[arg-type]

        with caplog.at_level(logging.INFO):
            result = await workflows.fast_requeue(
                order.id,
                stock,
                cooldown_seconds=1,
            )

        assert result.message == "Marketplace Order requeued by fast stock trigger."
        assert bridge.cancel_calls == [attempt.rbxcreate_order_id]
        assert len(bridge.create_calls) == 1
        assert state.saved_marketplace[-1].purchase_rate == Decimal("4.2")
        record = next(item for item in caplog.records if item.message == "fast_stock_trigger")
        assert record.order_id == str(order.id)
        assert record.detected_rate == "4.2"
        assert record.previous_marketplace_order == attempt.rbxcreate_order_id

    asyncio.run(scenario())


def test_fast_trigger_requeues_quick_order_at_its_maximum_rate(monkeypatch: Any) -> None:
    async def scenario() -> None:
        customer = _customer()
        order = _order(customer, ClientOrderStatus.PURCHASING)
        order.marketplace_rate_limit = Decimal("4.5")
        order.preferred_rate = None
        order.preferred_timeout_minutes = None
        order.fallback_active = True
        attempt = _attempt(order)
        attempt.created_at = NOW
        state = _wire(
            monkeypatch,
            customer=customer,
            order=order,
            attempt=attempt,
            maximum_purchase_rate=Decimal("4.5"),
        )
        stock = (MarketplaceStock(Decimal("4.5"), 2, 5_000, 5_000),)
        bridge = Bridge(stock=stock, sync_results=_active_then_cancelled(attempt))
        workflows = MarketplaceWorkflows(Sessions(), bridge, clock=lambda: NOW)  # type: ignore[arg-type]

        await workflows.fast_requeue(order.id, stock, cooldown_seconds=1)

        assert bridge.cancel_calls == [attempt.rbxcreate_order_id]
        assert len(bridge.create_calls) == 1
        assert state.saved_marketplace[-1].purchase_rate == Decimal("4.5")

    asyncio.run(scenario())


def test_fast_trigger_retains_active_order_without_eligible_stock(monkeypatch: Any) -> None:
    async def scenario() -> None:
        customer = _customer()
        order = _order(customer, ClientOrderStatus.PURCHASING)
        order.marketplace_rate_limit = Decimal("4.5")
        order.preferred_rate = Decimal("4.1")
        order.fallback_active = False
        attempt = _attempt(order)
        _wire(
            monkeypatch,
            customer=customer,
            order=order,
            attempt=attempt,
            maximum_purchase_rate=Decimal("4.5"),
        )
        stock = (MarketplaceStock(Decimal("4.2"), 2, 5_000, 5_000),)
        bridge = Bridge(
            stock=stock,
            sync_results=(_active_then_cancelled(attempt)[0],),
        )
        workflows = MarketplaceWorkflows(Sessions(), bridge, clock=lambda: NOW)  # type: ignore[arg-type]

        result = await workflows.fast_requeue(order.id, stock, cooldown_seconds=1)

        assert result.message == "No suitable stock for fast requeue."
        assert bridge.cancel_calls == []
        assert bridge.create_calls == []
        assert bridge.sync_calls == 0
        assert attempt.marketplace_status is MarketplaceOrderStatus.ACTIVE

    asyncio.run(scenario())


def test_fast_trigger_cooldown_blocks_a_second_requeue_within_one_second(
    monkeypatch: Any,
) -> None:
    async def scenario() -> None:
        customer = _customer()
        order = _order(customer, ClientOrderStatus.PURCHASING)
        order.marketplace_rate_limit = Decimal("4.5")
        order.preferred_rate = None
        order.fallback_active = True
        order.last_requeue_at = NOW - timedelta(milliseconds=500)
        attempt = _attempt(order)
        _wire(
            monkeypatch,
            customer=customer,
            order=order,
            attempt=attempt,
            maximum_purchase_rate=Decimal("4.5"),
        )
        stock = (MarketplaceStock(Decimal("4.2"), 2, 5_000, 5_000),)
        bridge = Bridge(stock=stock)
        workflows = MarketplaceWorkflows(Sessions(), bridge, clock=lambda: NOW)  # type: ignore[arg-type]

        result = await workflows.fast_requeue(order.id, stock, cooldown_seconds=1)

        assert result.message == "Fast requeue cooldown has not elapsed."
        assert bridge.sync_calls == 0
        assert bridge.cancel_calls == []
        assert bridge.create_calls == []

    asyncio.run(scenario())


def test_manual_requeue_retry_never_creates_a_second_remote_order(monkeypatch: Any) -> None:
    async def scenario() -> None:
        customer = _customer()
        order = _order(customer, ClientOrderStatus.PURCHASING)
        attempt = _attempt(order)
        _wire(monkeypatch, customer=customer, order=order, attempt=attempt)
        bridge = Bridge(
            stock=(MarketplaceStock(Decimal("2.00"), 2, 5000, 5000),),
            sync_results=(
                MarketplaceSyncResult(
                    attempt.rbxcreate_order_id,
                    MarketplaceOrderStatus.ACTIVE,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
                MarketplaceSyncResult(
                    attempt.rbxcreate_order_id,
                    MarketplaceOrderStatus.CANCELLED,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            ),
        )
        workflows = MarketplaceWorkflows(Sessions(), bridge, clock=lambda: NOW)  # type: ignore[arg-type]

        await workflows.manual_requeue(order.id)
        with pytest.raises(ConflictError, match="no active Marketplace Order"):
            await workflows.manual_requeue(order.id)

        assert len(bridge.create_calls) == 1

    asyncio.run(scenario())


def test_automatic_requeue_never_replaces_completed_attempt(monkeypatch: Any) -> None:
    async def scenario() -> None:
        customer = _customer()
        order = _order(customer, ClientOrderStatus.PURCHASING)
        attempt = _attempt(order)
        _wire(monkeypatch, customer=customer, order=order, attempt=attempt)
        bridge = Bridge(
            sync=MarketplaceSyncResult(
                attempt.rbxcreate_order_id,
                MarketplaceOrderStatus.COMPLETED,
                1000,
                0,
                None,
                Decimal("2.00"),
                None,
                None,
            )
        )
        workflows = MarketplaceWorkflows(Sessions(), bridge, clock=lambda: NOW)  # type: ignore[arg-type]

        result = await workflows.automatic_requeue(
            order.id,
            (MarketplaceStock(Decimal("2.00"), 2, 5000, 5000),),
        )

        assert result.message == "Order completed successfully."
        assert bridge.cancel_calls == []
        assert bridge.create_calls == []
        assert order.current_status is ClientOrderStatus.COMPLETED

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
        assert order.executed_rate == Decimal("11.00000000")

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


def test_purchase_completed_notification_uses_persisted_financial_snapshot() -> None:
    customer = _customer()
    order = _order(customer, ClientOrderStatus.COMPLETED)
    order.requested_robux = 100
    order.customer_receives = 70
    order.marketplace_cost = Decimal("0.3900")
    order.marketplace_commission = Decimal("0.0200")
    order.final_cost_usd = Decimal("0.4100")
    order.final_cost_local_currency = Decimal("36.9000")
    order.preferred_rate = Decimal("3.9")
    attempt = _attempt(order)
    attempt.marketplace_status = MarketplaceOrderStatus.COMPLETED
    attempt.purchase_rate = Decimal("3.9")
    attempt.requested_robux = 100
    attempt.purchased_robux = 100
    attempt.remaining_robux = 0

    message = _format_purchase_completed_notification(
        order,
        attempt,
        "viki_show2010435",
        Decimal("0.05"),
        PurchaseResult(
            requested_rate=Decimal("3.9"),
            executed_rate=Decimal("4.1"),
            marketplace_price_usd=Decimal("0.39"),
            commission_usd=Decimal("0.02"),
            total_paid_usd=Decimal("0.41"),
        ),
    )

    assert "Purchased: 100 R$" in message
    assert "Client receives: 70 R$" in message
    assert "Preferred trigger: 3.9$" in message
    assert "Executed rate: 4.1$" in message
    assert "Executed above preferred rate" in message
    assert "Marketplace price: $0.39" in message
    assert "commission: $0.02" in message
    assert "Total paid: $0.41" in message
    assert "Total RUB: 36.90 ₽" in message
