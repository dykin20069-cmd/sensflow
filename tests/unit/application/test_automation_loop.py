"""Focused tests for the owned asyncio automation task."""

import asyncio
from contextlib import AbstractAsyncContextManager
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import sensflow.application.automation_loop as loop_module
from sensflow.application.automation_loop import AutomationLoop, _stock_appeared_message
from sensflow.application.rbxcreate_bridge import MarketplaceStock
from sensflow.infrastructure.database.models import SystemSettings


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


def test_loop_synchronizes_respects_disabled_reorder_and_stops(
    monkeypatch: Any,
) -> None:
    async def scenario() -> None:
        marketplace_id = uuid4()
        preorder_id = uuid4()
        settings = SystemSettings(
            maximum_purchase_rate=Decimal("2"),
            automatic_reorder_enabled=False,
            automatic_reorder_interval_seconds=3600,
            marketplace_monitoring_interval_seconds=3600,
            synchronization_interval_seconds=3600,
            marketplace_commission=Decimal("0.1"),
            usd_exchange_rate=Decimal("90"),
            telegram_notifications_enabled=True,
            notification_categories=[],
            application_timezone="UTC",
        )

        class MarketplaceRepository:
            async def list_by_status(self, *args: object, **kwargs: object) -> list[object]:
                return [SimpleNamespace(id=marketplace_id)]

            async def list_completed_for_unfinished_client_orders(
                self, **kwargs: object
            ) -> list[object]:
                return []

        class ClientRepository:
            async def list_by_status(self, *args: object, **kwargs: object) -> list[object]:
                return [SimpleNamespace(id=preorder_id)]

        class SettingsRepository:
            async def get_current(self) -> SystemSettings:
                return settings

        monkeypatch.setattr(
            loop_module, "MarketplaceOrderRepository", lambda session: MarketplaceRepository()
        )
        monkeypatch.setattr(
            loop_module, "ClientOrderRepository", lambda session: ClientRepository()
        )
        monkeypatch.setattr(
            loop_module, "SystemSettingsRepository", lambda session: SettingsRepository()
        )

        synchronized = asyncio.Event()
        reorder_calls: list[object] = []

        class Workflows:
            async def synchronize_marketplace_order(self, order_id: object) -> None:
                assert order_id == marketplace_id
                synchronized.set()

            async def start_purchase(self, order_id: object) -> None:
                reorder_calls.append(order_id)

        automation = AutomationLoop(Sessions(), Workflows())  # type: ignore[arg-type]
        await automation.start()
        assert automation.is_running is True
        await asyncio.wait_for(synchronized.wait(), timeout=1)
        await automation.stop()

        assert reorder_calls == []
        assert automation.is_running is False
        assert automation._task is None

    asyncio.run(scenario())


def test_stock_notification_describes_selected_tier_and_client_count() -> None:
    message = _stock_appeared_message(
        MarketplaceStock(
            rate=Decimal("4.3"),
            accounts_count=25,
            max_instant_order=338,
            total_robux_amount=9071,
        ),
        3,
    )

    assert "Stock appeared" in message
    assert "Rate: 4.3$" in message
    assert "Available: 9071 R$" in message
    assert "Largest instant order: 338 R$" in message
    assert "Requeueing 3 PreOrders" in message
