"""Operational diagnostics tests without live infrastructure."""

import asyncio
from contextlib import AbstractAsyncContextManager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from sensflow.application.commands import SystemActionCommand
from sensflow.application.errors import AuthorizationError, MarketplaceIntegrationError
from sensflow.application.recovery import RecoveryResult
from sensflow.application.services import SystemApplicationService
from sensflow.presentation.telegram.rendering import render_system_status


class SessionContext(AbstractAsyncContextManager[object]):
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *args: object) -> None:
        return None


class Sessions:
    def __call__(self) -> SessionContext:
        return SessionContext()


def _repositories() -> tuple[MagicMock, MagicMock]:
    marketplace = MagicMock()
    marketplace.count_by_status = AsyncMock(return_value=3)
    orders = MagicMock()
    orders.count_by_status = AsyncMock(return_value=7)
    return marketplace, orders


def test_status_reports_rbxcrate_balance_counts_and_running_loop() -> None:
    async def scenario() -> None:
        marketplace, orders = _repositories()
        bridge = MagicMock()
        bridge.get_balance = AsyncMock(return_value=Decimal("12.446"))
        automation = MagicMock(is_running=True)
        service = SystemApplicationService(
            MagicMock(),
            sessions=Sessions(),  # type: ignore[arg-type]
            rbxcrate=bridge,
            automation=automation,
        )
        with (
            patch(
                "sensflow.application.services.verify_database_connection",
                new=AsyncMock(),
            ),
            patch(
                "sensflow.application.services.MarketplaceOrderRepository",
                return_value=marketplace,
            ),
            patch(
                "sensflow.application.services.ClientOrderRepository",
                return_value=orders,
            ),
        ):
            status = await service.get_status()

        screen = render_system_status(status)
        assert status.marketplace_available is True
        assert status.rbxcrate_balance == Decimal("12.45")
        assert status.active_marketplace_orders == 3
        assert status.pending_preorders == 7
        assert status.automation_available is True
        assert "RBXCrate Balance: $12.45" in screen.text
        assert "Automation Loop: Running" in screen.text
        assert screen.reply_markup is not None
        labels = [button.text for row in screen.reply_markup.inline_keyboard for button in row]
        assert "Run Recovery Now" in labels
        assert "Run Sync Pass Now" in labels

    asyncio.run(scenario())


def test_status_reports_rbxcrate_unavailable_without_leaking_details() -> None:
    async def scenario() -> None:
        marketplace, orders = _repositories()
        bridge = MagicMock()
        bridge.get_balance = AsyncMock(
            side_effect=MarketplaceIntegrationError("secret upstream details")
        )
        service = SystemApplicationService(
            MagicMock(),
            sessions=Sessions(),  # type: ignore[arg-type]
            rbxcrate=bridge,
        )
        with (
            patch(
                "sensflow.application.services.verify_database_connection",
                new=AsyncMock(),
            ),
            patch(
                "sensflow.application.services.MarketplaceOrderRepository",
                return_value=marketplace,
            ),
            patch(
                "sensflow.application.services.ClientOrderRepository",
                return_value=orders,
            ),
        ):
            status = await service.get_status()

        screen = render_system_status(status)
        assert status.marketplace_available is False
        assert status.rbxcrate_balance is None
        assert "RBXCrate API: Unavailable" in screen.text
        assert "secret upstream details" not in screen.text

    asyncio.run(scenario())


def test_status_reports_stopped_automation_loop() -> None:
    async def scenario() -> None:
        marketplace, orders = _repositories()
        automation = MagicMock(is_running=False)
        service = SystemApplicationService(
            MagicMock(),
            sessions=Sessions(),  # type: ignore[arg-type]
            automation=automation,
        )
        with (
            patch(
                "sensflow.application.services.verify_database_connection",
                new=AsyncMock(),
            ),
            patch(
                "sensflow.application.services.MarketplaceOrderRepository",
                return_value=marketplace,
            ),
            patch(
                "sensflow.application.services.ClientOrderRepository",
                return_value=orders,
            ),
        ):
            status = await service.get_status()

        assert status.automation_available is False
        assert "Automation Loop: Stopped" in render_system_status(status).text

    asyncio.run(scenario())


def test_operator_can_run_recovery_and_sync_pass() -> None:
    async def scenario() -> None:
        recovery = MagicMock()
        recovery.recover_incomplete_orders = AsyncMock(
            return_value=RecoveryResult(checked=4, repaired=2)
        )
        automation = MagicMock(is_running=True)
        automation.run_synchronization_pass = AsyncMock(return_value=3)
        service = SystemApplicationService(
            MagicMock(),
            recovery=recovery,
            automation=automation,
            operator_id=42,
        )
        command = SystemActionCommand(operator_id=42)

        recovery_result = await service.run_recovery_now(command)
        sync_result = await service.run_sync_pass_now(command)

        assert recovery_result.message == "Recovery checked 4 orders and repaired 2."
        assert sync_result.message == ("Synchronization processed 3 active Marketplace Orders.")

        try:
            await service.run_sync_pass_now(SystemActionCommand(operator_id=7))
        except AuthorizationError:
            pass
        else:
            raise AssertionError("unauthorized operational action was accepted")

    asyncio.run(scenario())
