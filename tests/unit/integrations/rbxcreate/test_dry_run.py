"""Deterministic RBXCrate dry-run behavior without network access."""

import asyncio
from decimal import Decimal

import pytest

from sensflow.integrations.rbxcreate.dry_run import RbxcrateDryRunGateway
from sensflow.integrations.rbxcreate.errors import RbxcrateOrderNotFoundError


def test_dry_run_advances_pending_processing_completed() -> None:
    async def scenario() -> None:
        gateway = RbxcrateDryRunGateway()
        stock = await gateway.get_detailed_stock()
        created = await gateway.create_gamepass_order(
            roblox_username="DryRunCustomer",
            order_id="dry-order-1",
            robux_amount=1000,
            place_id=123,
            is_preorder=False,
            check_ownership=True,
        )
        processing = await gateway.get_order_info(order_id="dry-order-1")
        completed = await gateway.get_order_info(order_id="dry-order-1")

        assert stock[0].total_robux_amount >= 1000
        assert created.data.status == "Pending"
        assert created.data.gamepass_id is None
        assert processing.raw_status == "Processing"
        assert completed.raw_status == "Completed"
        assert completed.price == Decimal("0.00001000")
        assert (await gateway.get_balance()).balance == Decimal("9999.99")

    asyncio.run(scenario())


def test_dry_run_cancellation_and_unknown_order_are_safe() -> None:
    async def scenario() -> None:
        gateway = RbxcrateDryRunGateway()
        await gateway.create_gamepass_order(
            roblox_username="DryRunCustomer",
            order_id="dry-order-2",
            robux_amount=100,
            place_id=123,
            is_preorder=False,
            check_ownership=True,
        )
        await gateway.cancel_order(order_id="dry-order-2")

        assert (await gateway.get_order_info(order_id="dry-order-2")).raw_status == ("Cancelled")
        with pytest.raises(RbxcrateOrderNotFoundError):
            await gateway.get_order_info(order_id="unknown")

    asyncio.run(scenario())
