"""Focused tests for the owned asyncio automation task."""

import asyncio
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import sensflow.application.automation_loop as loop_module
from sensflow.application.automation_loop import (
    FAST_REQUEUE_COOLDOWN_SECONDS,
    AutomationLoop,
    _stock_appeared_message,
)
from sensflow.application.marketplace_workflows import AutomationStockPlan
from sensflow.application.rbxcreate_bridge import MarketplaceStock
from sensflow.domain.enums import ClientOrderStatus, NotificationType
from sensflow.infrastructure.database.models import SystemSettings

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)


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
            preferred_purchase_rate=Decimal("1.5"),
            preferred_timeout_minutes=35,
            low_balance_threshold=Decimal("10"),
            critical_balance_threshold=Decimal("5"),
            stock_notifications_enabled=True,
            automatic_reorder_enabled=False,
            automatic_reorder_interval_seconds=3600,
            auto_requeue_delay_seconds=Decimal("5"),
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
            async def activate_expired_fallbacks(self) -> int:
                return 0

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
        Decimal("4.5"),
    )

    assert "Stock appeared" in message
    assert "Rate: 4.3$" in message
    assert "Available: 9,071 R$" in message
    assert "Instant: 338 R$" in message
    assert "current limit ≤ 4.5$" in message


def test_reorder_pass_uses_one_stock_plan_for_preorders_and_active_orders(
    monkeypatch: Any,
) -> None:
    async def scenario() -> None:
        preorder_id = uuid4()
        active_id = uuid4()
        stock = MarketplaceStock(Decimal("4.3"), 25, 338, 9071)
        settings = SystemSettings(
            maximum_purchase_rate=Decimal("4.5"),
            preferred_purchase_rate=Decimal("4.3"),
            preferred_timeout_minutes=35,
            low_balance_threshold=Decimal("10"),
            critical_balance_threshold=Decimal("5"),
            stock_notifications_enabled=True,
            automatic_reorder_enabled=True,
            automatic_reorder_interval_seconds=Decimal("0.3"),
            auto_requeue_delay_seconds=Decimal("5"),
            marketplace_monitoring_interval_seconds=30,
            synchronization_interval_seconds=30,
            marketplace_commission=Decimal("0.05"),
            usd_exchange_rate=Decimal("90"),
            telegram_notifications_enabled=True,
            notification_categories=[NotificationType.STOCK_AVAILABLE],
            application_timezone="UTC",
        )

        class ClientRepository:
            async def list_by_status(self, status: object, **kwargs: object) -> list[object]:
                if status is ClientOrderStatus.PREORDER:
                    return [
                        SimpleNamespace(
                            id=preorder_id,
                            requested_robux=100,
                            preferred_rate=Decimal("4.3"),
                            fallback_active=False,
                            preferred_expires_at=None,
                            marketplace_rate_limit=Decimal("4.5"),
                        )
                    ]
                return [SimpleNamespace(id=active_id, requested_robux=100)]

        class SettingsRepository:
            async def get_current(self) -> SystemSettings:
                return settings

        monkeypatch.setattr(
            loop_module, "ClientOrderRepository", lambda session: ClientRepository()
        )
        monkeypatch.setattr(
            loop_module, "SystemSettingsRepository", lambda session: SettingsRepository()
        )
        workflows = MagicMock()
        workflows.plan_automation = AsyncMock(
            return_value=AutomationStockPlan(
                order_ids=(preorder_id,),
                stock=(stock,),
                minimum_purchase_rate=Decimal("0"),
                maximum_purchase_rate=Decimal("4.5"),
            )
        )
        workflows.start_purchase = AsyncMock()
        workflows.fast_requeue = AsyncMock()
        workflows.automatic_requeue = AsyncMock()
        notifications = MagicMock()
        notifications.queue = AsyncMock()
        notifications.deliver_pending = AsyncMock(return_value=1)

        automation = AutomationLoop(
            Sessions(),  # type: ignore[arg-type]
            workflows,
            notifications=notifications,
        )
        await automation.run_reorder_pass()

        workflows.plan_automation.assert_awaited_once()
        workflows.start_purchase.assert_awaited_once_with(preorder_id)
        workflows.fast_requeue.assert_awaited_once_with(
            active_id,
            (stock,),
            cooldown_seconds=FAST_REQUEUE_COOLDOWN_SECONDS,
        )
        workflows.automatic_requeue.assert_awaited_once_with(active_id, (stock,))
        notifications.queue.assert_awaited_once()
        notifications.deliver_pending.assert_awaited_once()

        await automation._run_stock_pass(
            process_preorders=False,
            process_active=True,
        )

        assert workflows.plan_automation.await_args.args[0] == ()
        assert workflows.start_purchase.await_count == 1
        assert workflows.fast_requeue.await_count == 1
        assert workflows.automatic_requeue.await_count == 2

        await automation._run_stock_pass(
            process_preorders=False,
            process_active=False,
            process_fast_triggers=True,
        )

        assert workflows.fast_requeue.await_count == 2
        assert workflows.automatic_requeue.await_count == 2

    asyncio.run(scenario())


def test_balance_monitor_queues_low_and_critical_alerts_with_hourly_throttle(
    monkeypatch: Any,
) -> None:
    async def scenario() -> None:
        settings = SystemSettings(
            maximum_purchase_rate=Decimal("4.5"),
            preferred_purchase_rate=Decimal("4.3"),
            preferred_timeout_minutes=35,
            low_balance_threshold=Decimal("10"),
            critical_balance_threshold=Decimal("5"),
            stock_notifications_enabled=True,
            automatic_reorder_enabled=True,
            automatic_reorder_interval_seconds=Decimal("0.3"),
            auto_requeue_delay_seconds=Decimal("5"),
            marketplace_monitoring_interval_seconds=5,
            synchronization_interval_seconds=30,
            marketplace_commission=Decimal("0.05"),
            usd_exchange_rate=Decimal("90"),
            telegram_notifications_enabled=True,
            notification_categories=[
                NotificationType.LOW_BALANCE,
                NotificationType.CRITICAL_BALANCE,
            ],
            application_timezone="UTC",
        )

        class SettingsRepository:
            async def get_current(self) -> SystemSettings:
                return settings

        monkeypatch.setattr(
            loop_module, "SystemSettingsRepository", lambda session: SettingsRepository()
        )
        workflows = MagicMock()
        workflows.get_balance = AsyncMock(side_effect=(Decimal("9.42"), Decimal("4.81")))
        notifications = MagicMock()
        notifications.queue_once = AsyncMock(return_value=True)
        notifications.deliver_pending = AsyncMock(return_value=1)
        automation = AutomationLoop(
            Sessions(),  # type: ignore[arg-type]
            workflows,
            notifications=notifications,
        )

        await automation.run_balance_monitor_pass()
        await automation.run_balance_monitor_pass()

        calls = notifications.queue_once.await_args_list
        assert calls[0].kwargs["notification_type"] is NotificationType.LOW_BALANCE
        assert calls[0].kwargs["throttle_seconds"] == 3600
        assert "$9.42" in calls[0].kwargs["message"]
        assert calls[1].kwargs["notification_type"] is NotificationType.CRITICAL_BALANCE
        assert "$4.81" in calls[1].kwargs["message"]

    asyncio.run(scenario())


def test_stock_notification_repeats_only_after_twenty_percent_growth(
    monkeypatch: Any,
) -> None:
    async def scenario() -> None:
        settings = SystemSettings(
            maximum_purchase_rate=Decimal("4.5"),
            preferred_purchase_rate=Decimal("4.3"),
            preferred_timeout_minutes=35,
            low_balance_threshold=Decimal("10"),
            critical_balance_threshold=Decimal("5"),
            stock_notifications_enabled=True,
            automatic_reorder_enabled=True,
            automatic_reorder_interval_seconds=Decimal("0.3"),
            auto_requeue_delay_seconds=Decimal("5"),
            marketplace_monitoring_interval_seconds=5,
            synchronization_interval_seconds=30,
            marketplace_commission=Decimal("0.05"),
            usd_exchange_rate=Decimal("90"),
            telegram_notifications_enabled=True,
            notification_categories=[NotificationType.STOCK_AVAILABLE],
            application_timezone="UTC",
        )

        class ClientRepository:
            async def list_by_status(self, *args: object, **kwargs: object) -> list[object]:
                return []

        class SettingsRepository:
            async def get_current(self) -> SystemSettings:
                return settings

        monkeypatch.setattr(
            loop_module, "ClientOrderRepository", lambda session: ClientRepository()
        )
        monkeypatch.setattr(
            loop_module, "SystemSettingsRepository", lambda session: SettingsRepository()
        )
        plans = tuple(
            AutomationStockPlan(
                order_ids=(),
                stock=(MarketplaceStock(Decimal("4.3"), 2, 500, amount),),
                minimum_purchase_rate=Decimal("0"),
                maximum_purchase_rate=Decimal("4.5"),
            )
            for amount in (1_000, 1_100, 1_200)
        )
        workflows = MagicMock()
        workflows.plan_automation = AsyncMock(side_effect=plans)
        notifications = MagicMock()
        notifications.queue = AsyncMock()
        notifications.deliver_pending = AsyncMock(return_value=1)
        current_time = [NOW]
        automation = AutomationLoop(
            Sessions(),  # type: ignore[arg-type]
            workflows,
            notifications=notifications,
            clock=lambda: current_time[0],
        )

        await automation._run_stock_pass(
            process_preorders=False,
            process_active=False,
        )
        current_time[0] += timedelta(minutes=5)
        await automation._run_stock_pass(
            process_preorders=False,
            process_active=False,
        )
        await automation._run_stock_pass(
            process_preorders=False,
            process_active=False,
        )

        assert notifications.queue.await_count == 2
        assert "Available: 1,200 R$" in notifications.queue.await_args.kwargs["message"]

    asyncio.run(scenario())
