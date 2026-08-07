"""Focused startup recovery tests with repository fakes."""

import asyncio
from contextlib import AbstractAsyncContextManager
from decimal import Decimal
from typing import Any
from uuid import uuid4

import sensflow.application.recovery as recovery_module
from sensflow.application.recovery import RecoveryService
from sensflow.domain.enums import ClientOrderStatus, MarketplaceOrderStatus
from sensflow.infrastructure.database.models import ClientOrder, MarketplaceOrder


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


def _purchasing_order() -> ClientOrder:
    order = ClientOrder(
        customer_id=uuid4(),
        requested_robux=1000,
        current_status=ClientOrderStatus.PURCHASING,
        current_place_id=77,
        marketplace_rate_limit=Decimal("2"),
    )
    order.id = uuid4()
    return order


def _wire(
    monkeypatch: Any,
    orders: list[ClientOrder],
    active_by_order: dict[object, MarketplaceOrder],
) -> list[object]:
    events: list[object] = []

    class Orders:
        async def list_by_status(self, *args: object, **kwargs: object) -> list[ClientOrder]:
            return orders

        async def get_for_update(self, order_id: object) -> ClientOrder | None:
            return next((order for order in orders if order.id == order_id), None)

        async def get(self, order_id: object) -> ClientOrder | None:
            return next((order for order in orders if order.id == order_id), None)

        async def save(self, order: ClientOrder) -> ClientOrder:
            return order

    class Marketplace:
        async def get_active_for_client_order(self, order_id: object) -> MarketplaceOrder | None:
            return active_by_order.get(order_id)

        async def get_active_for_client_order_for_update(
            self, order_id: object
        ) -> MarketplaceOrder | None:
            return active_by_order.get(order_id)

        async def list_for_client_order(
            self, order_id: object, **kwargs: object
        ) -> list[MarketplaceOrder]:
            active = active_by_order.get(order_id)
            return [] if active is None else [active]

    class Timeline:
        async def save(self, event: object) -> object:
            events.append(event)
            return event

    monkeypatch.setattr(recovery_module, "ClientOrderRepository", lambda session: Orders())
    monkeypatch.setattr(
        recovery_module, "MarketplaceOrderRepository", lambda session: Marketplace()
    )
    monkeypatch.setattr(recovery_module, "TimelineEventRepository", lambda session: Timeline())
    return events


def test_recovery_restores_orphaned_purchasing_order(monkeypatch: Any) -> None:
    async def scenario() -> None:
        order = _purchasing_order()
        events = _wire(monkeypatch, [order], {})

        class Workflows:
            async def synchronize_marketplace_order(self, order_id: object) -> None:
                raise AssertionError("orphan must not synchronize")

        recovery = RecoveryService(Sessions(), Workflows())  # type: ignore[arg-type]
        await recovery.recover_incomplete_orders()

        assert order.current_status is ClientOrderStatus.PREORDER
        assert len(events) == 1

    asyncio.run(scenario())


def test_recovery_synchronizes_active_marketplace_attempt(monkeypatch: Any) -> None:
    async def scenario() -> None:
        order = _purchasing_order()
        attempt = MarketplaceOrder(
            client_order_id=order.id,
            rbxcreate_order_id="external",
            marketplace_status=MarketplaceOrderStatus.ACTIVE,
            purchase_rate=Decimal("1"),
            requested_robux=1000,
            purchased_robux=0,
            remaining_robux=1000,
        )
        attempt.id = uuid4()
        events = _wire(monkeypatch, [order], {order.id: attempt})
        synchronized: list[object] = []

        class Workflows:
            async def synchronize_marketplace_order(self, order_id: object) -> None:
                synchronized.append(order_id)

        recovery = RecoveryService(Sessions(), Workflows())  # type: ignore[arg-type]
        await recovery.recover_incomplete_orders()

        assert synchronized == [attempt.id]
        assert order.current_status is ClientOrderStatus.PURCHASING
        assert events == []

    asyncio.run(scenario())
