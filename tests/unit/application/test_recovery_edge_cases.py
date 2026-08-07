"""Startup recovery coverage for every interrupted Purchasing shape."""

import asyncio
from contextlib import AbstractAsyncContextManager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

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


def _order() -> ClientOrder:
    order = ClientOrder(
        customer_id=uuid4(),
        requested_robux=1000,
        current_status=ClientOrderStatus.PURCHASING,
        current_place_id=77,
        marketplace_rate_limit=Decimal("2"),
    )
    order.id = uuid4()
    return order


def _attempt(order: ClientOrder, status: MarketplaceOrderStatus) -> MarketplaceOrder:
    attempt = MarketplaceOrder(
        client_order_id=order.id,
        rbxcreate_order_id=f"external-{status.value}",
        marketplace_status=status,
        purchase_rate=Decimal("1.5"),
        requested_robux=1000,
        purchased_robux=1000 if status is MarketplaceOrderStatus.COMPLETED else 0,
        remaining_robux=0 if status is MarketplaceOrderStatus.COMPLETED else 1000,
    )
    attempt.id = uuid4()
    return attempt


def _run_recovery(
    order: ClientOrder,
    attempts: list[MarketplaceOrder],
    workflows: MagicMock,
) -> list[object]:
    async def scenario() -> list[object]:
        timeline_events: list[object] = []
        active = next(
            (
                attempt
                for attempt in attempts
                if attempt.marketplace_status is MarketplaceOrderStatus.ACTIVE
            ),
            None,
        )
        orders = MagicMock()
        orders.list_by_status = AsyncMock(return_value=[order])
        orders.get_for_update = AsyncMock(return_value=order)
        orders.get = AsyncMock(return_value=order)
        orders.save = AsyncMock(side_effect=lambda entity: entity)
        marketplace = MagicMock()
        marketplace.get_active_for_client_order = AsyncMock(return_value=active)
        marketplace.get_active_for_client_order_for_update = AsyncMock(return_value=active)
        marketplace.list_for_client_order = AsyncMock(return_value=attempts)
        timeline = MagicMock()

        async def save_event(event: object) -> object:
            timeline_events.append(event)
            return event

        timeline.save = AsyncMock(side_effect=save_event)
        with (
            patch(
                "sensflow.application.recovery.ClientOrderRepository",
                return_value=orders,
            ),
            patch(
                "sensflow.application.recovery.MarketplaceOrderRepository",
                return_value=marketplace,
            ),
            patch(
                "sensflow.application.recovery.TimelineEventRepository",
                return_value=timeline,
            ),
        ):
            await RecoveryService(Sessions(), workflows).recover_incomplete_orders()  # type: ignore[arg-type]
        return timeline_events

    return asyncio.run(scenario())


def test_orphaned_purchasing_order_returns_to_preorder() -> None:
    order = _order()
    workflows = MagicMock()
    workflows.synchronize_marketplace_order = AsyncMock()

    events = _run_recovery(order, [], workflows)

    assert order.current_status is ClientOrderStatus.PREORDER
    assert len(events) == 1
    workflows.synchronize_marketplace_order.assert_not_awaited()


def test_completed_attempt_is_selected_for_client_finalization() -> None:
    order = _order()
    completed = _attempt(order, MarketplaceOrderStatus.COMPLETED)
    workflows = MagicMock()

    async def finalize(attempt_id: object) -> None:
        assert attempt_id == completed.id
        order.current_status = ClientOrderStatus.COMPLETED

    workflows.synchronize_marketplace_order = AsyncMock(side_effect=finalize)

    events = _run_recovery(order, [completed], workflows)

    assert order.current_status is ClientOrderStatus.COMPLETED
    assert events == []
    workflows.synchronize_marketplace_order.assert_awaited_once_with(completed.id)


def test_active_attempt_is_synchronized() -> None:
    order = _order()
    active = _attempt(order, MarketplaceOrderStatus.ACTIVE)
    workflows = MagicMock()
    workflows.synchronize_marketplace_order = AsyncMock()

    events = _run_recovery(order, [active], workflows)

    assert order.current_status is ClientOrderStatus.PURCHASING
    assert events == []
    workflows.synchronize_marketplace_order.assert_awaited_once_with(active.id)
