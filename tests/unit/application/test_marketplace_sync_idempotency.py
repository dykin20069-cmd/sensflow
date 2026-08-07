"""Integration-style synchronization tests with in-memory ORM entities."""

import asyncio
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sensflow.application.callbacks import MarketplaceCallbackService
from sensflow.application.marketplace_workflows import MarketplaceWorkflows
from sensflow.application.rbxcreate_bridge import MarketplaceSyncResult
from sensflow.domain.enums import ClientOrderStatus, MarketplaceOrderStatus
from sensflow.infrastructure.database.models import (
    ClientOrder,
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


def _entities(
    marketplace_status: MarketplaceOrderStatus = MarketplaceOrderStatus.ACTIVE,
) -> tuple[ClientOrder, MarketplaceOrder]:
    order = ClientOrder(
        customer_id=uuid4(),
        requested_robux=1000,
        current_status=ClientOrderStatus.PURCHASING,
        current_place_id=77,
        marketplace_rate_limit=Decimal("2"),
    )
    order.id = uuid4()
    attempt = MarketplaceOrder(
        client_order_id=order.id,
        rbxcreate_order_id=str(order.id),
        marketplace_status=marketplace_status,
        purchase_rate=Decimal("1.50"),
        requested_robux=1000,
        purchased_robux=100 if marketplace_status is MarketplaceOrderStatus.ACTIVE else 1000,
        remaining_robux=900 if marketplace_status is MarketplaceOrderStatus.ACTIVE else 0,
        completed_at=NOW if marketplace_status is MarketplaceOrderStatus.COMPLETED else None,
    )
    attempt.id = uuid4()
    return order, attempt


def _settings() -> SystemSettings:
    return SystemSettings(
        maximum_purchase_rate=Decimal("2"),
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


def _repositories(
    order: ClientOrder,
    attempt: MarketplaceOrder,
) -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
    orders = MagicMock()
    orders.get_for_update = AsyncMock(return_value=order)
    orders.save = AsyncMock(side_effect=lambda entity: entity)
    marketplace = MagicMock()
    marketplace.get = AsyncMock(return_value=attempt)
    marketplace.get_for_update = AsyncMock(return_value=attempt)
    marketplace.save = AsyncMock(side_effect=lambda entity: entity)
    timeline = MagicMock()
    timeline.save = AsyncMock(side_effect=lambda entity: entity)
    settings = MagicMock()
    settings.get_current = AsyncMock(return_value=_settings())
    return orders, marketplace, timeline, settings


def _patch_repositories(
    orders: MagicMock,
    marketplace: MagicMock,
    timeline: MagicMock,
    settings: MagicMock,
) -> Any:
    return (
        patch(
            "sensflow.application.marketplace_workflows.ClientOrderRepository",
            return_value=orders,
        ),
        patch(
            "sensflow.application.marketplace_workflows.MarketplaceOrderRepository",
            return_value=marketplace,
        ),
        patch(
            "sensflow.application.marketplace_workflows.TimelineEventRepository",
            return_value=timeline,
        ),
        patch(
            "sensflow.application.marketplace_workflows.SystemSettingsRepository",
            return_value=settings,
        ),
        patch(
            "sensflow.application.marketplace_workflows.CustomerRepository",
            return_value=SimpleNamespace(
                get=AsyncMock(return_value=SimpleNamespace(current_username="builder"))
            ),
        ),
        patch(
            "sensflow.application.marketplace_workflows.UserPlaceCacheRepository",
            return_value=SimpleNamespace(get_by_username_for_update=AsyncMock(return_value=None)),
        ),
    )


def test_repeated_completion_finalizes_exactly_once() -> None:
    async def scenario() -> None:
        order, attempt = _entities()
        repositories = _repositories(order, attempt)
        bridge = MagicMock()
        bridge.get_order_info = AsyncMock(
            return_value=MarketplaceSyncResult(
                attempt.rbxcreate_order_id,
                MarketplaceOrderStatus.COMPLETED,
                None,
                None,
                None,
                Decimal("12.50"),
                None,
                None,
            )
        )
        workflows = MarketplaceWorkflows(Sessions(), bridge, clock=lambda: NOW)  # type: ignore[arg-type]
        patches = _patch_repositories(*repositories)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            first = await workflows.synchronize_marketplace_order(attempt.id)
            second = await workflows.synchronize_marketplace_order(attempt.id)

        assert first.message == "Order completed successfully."
        assert second.message == "Order is already completed."
        assert bridge.get_order_info.await_count == 1
        assert attempt.purchased_robux == attempt.requested_robux
        assert order.current_status is ClientOrderStatus.COMPLETED

    asyncio.run(scenario())


def test_repeated_cancellation_is_idempotent() -> None:
    async def scenario() -> None:
        order, attempt = _entities()
        repositories = _repositories(order, attempt)
        bridge = MagicMock()
        bridge.get_order_info = AsyncMock(
            return_value=MarketplaceSyncResult(
                attempt.rbxcreate_order_id,
                MarketplaceOrderStatus.CANCELLED,
                None,
                None,
                None,
                None,
                "provider_error",
                "not shown",
            )
        )
        workflows = MarketplaceWorkflows(Sessions(), bridge, clock=lambda: NOW)  # type: ignore[arg-type]
        patches = _patch_repositories(*repositories)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            await workflows.synchronize_marketplace_order(attempt.id)
            repeated = await workflows.synchronize_marketplace_order(attempt.id)

        assert repeated.message == "Marketplace order is already cancelled."
        assert bridge.get_order_info.await_count == 1
        assert order.current_status is ClientOrderStatus.PREORDER

    asyncio.run(scenario())


def test_active_sync_preserves_progress_and_records_observed_price() -> None:
    async def scenario() -> None:
        order, attempt = _entities()
        repositories = _repositories(order, attempt)
        bridge = MagicMock()
        bridge.get_order_info = AsyncMock(
            return_value=MarketplaceSyncResult(
                attempt.rbxcreate_order_id,
                MarketplaceOrderStatus.ACTIVE,
                None,
                None,
                None,
                Decimal("8.75"),
                None,
                None,
            )
        )
        workflows = MarketplaceWorkflows(Sessions(), bridge, clock=lambda: NOW)  # type: ignore[arg-type]
        patches = _patch_repositories(*repositories)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            await workflows.synchronize_marketplace_order(attempt.id)

        assert attempt.purchased_robux == 100
        assert attempt.remaining_robux == 900
        assert order.marketplace_cost == Decimal("8.75")

    asyncio.run(scenario())


def test_locally_completed_attempt_finalizes_unfinished_client_order() -> None:
    async def scenario() -> None:
        order, attempt = _entities(MarketplaceOrderStatus.COMPLETED)
        order.marketplace_cost = Decimal("12.50")
        repositories = _repositories(order, attempt)
        bridge = MagicMock()
        bridge.get_order_info = AsyncMock()
        workflows = MarketplaceWorkflows(Sessions(), bridge, clock=lambda: NOW)  # type: ignore[arg-type]
        patches = _patch_repositories(*repositories)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            result = await workflows.synchronize_marketplace_order(attempt.id)

        assert result.message == "Order completed successfully."
        bridge.get_order_info.assert_not_awaited()
        assert order.current_status is ClientOrderStatus.COMPLETED

    asyncio.run(scenario())


def test_callback_boundary_synchronizes_known_external_order() -> None:
    async def scenario() -> None:
        _, attempt = _entities()
        repository = MagicMock()
        repository.get_by_external_id = AsyncMock(return_value=attempt)
        workflows = MagicMock()
        workflows.synchronize_marketplace_order = AsyncMock()
        with patch(
            "sensflow.application.callbacks.MarketplaceOrderRepository",
            return_value=repository,
        ):
            found = await MarketplaceCallbackService(
                Sessions(),
                workflows,  # type: ignore[arg-type]
            ).handle_order_update(attempt.rbxcreate_order_id)

        assert found is True
        workflows.synchronize_marketplace_order.assert_awaited_once_with(attempt.id)

    asyncio.run(scenario())


def test_callback_boundary_ignores_unknown_external_order() -> None:
    async def scenario() -> None:
        repository = MagicMock()
        repository.get_by_external_id = AsyncMock(return_value=None)
        workflows = MagicMock()
        workflows.synchronize_marketplace_order = AsyncMock()
        with patch(
            "sensflow.application.callbacks.MarketplaceOrderRepository",
            return_value=repository,
        ):
            found = await MarketplaceCallbackService(
                Sessions(),
                workflows,  # type: ignore[arg-type]
            ).handle_order_update("unknown")

        assert found is False
        workflows.synchronize_marketplace_order.assert_not_awaited()

    asyncio.run(scenario())
