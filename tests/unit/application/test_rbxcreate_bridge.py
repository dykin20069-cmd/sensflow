"""Application boundary tests for typed RBXCrate translation."""

import asyncio
from decimal import Decimal

import pytest

from sensflow.application.errors import UnknownMarketplaceStatusError
from sensflow.application.rbxcreate_bridge import RbxcreateBridge, map_marketplace_status
from sensflow.domain.enums import MarketplaceOrderStatus
from sensflow.integrations.rbxcreate.models import (
    DetailedStockItem,
    OrderInfoResponse,
)


class FakeGateway:
    def __init__(self, status: str = "Completed") -> None:
        self.status = status

    async def get_detailed_stock(self) -> tuple[DetailedStockItem, ...]:
        return (
            DetailedStockItem.model_validate(
                {
                    "rate": "1.25",
                    "accountsCount": 2,
                    "maxInstantOrder": 5000,
                    "totalRobuxAmount": 7000,
                }
            ),
        )

    async def get_order_info(self, *, order_id: str) -> OrderInfoResponse:
        return OrderInfoResponse.model_validate(
            {
                "type": "gamepass",
                "uuid": "remote-uuid",
                "price": "12.50",
                "vendorId": "vendor",
                "robuxAmount": 1000,
                "status": self.status,
                "robloxUserId": 42,
                "robloxUsername": "builder",
                "error": None,
            }
        )


@pytest.mark.parametrize(
    ("raw_status", "expected"),
    [
        ("Pending", MarketplaceOrderStatus.ACTIVE),
        ("Queued", MarketplaceOrderStatus.ACTIVE),
        ("Processing", MarketplaceOrderStatus.ACTIVE),
        ("Completed", MarketplaceOrderStatus.COMPLETED),
        ("Cancelled", MarketplaceOrderStatus.CANCELLED),
        ("Error", MarketplaceOrderStatus.CANCELLED),
    ],
)
def test_maps_approved_statuses(raw_status: str, expected: MarketplaceOrderStatus) -> None:
    assert map_marketplace_status(raw_status) is expected


def test_rejects_unknown_status() -> None:
    with pytest.raises(UnknownMarketplaceStatusError):
        map_marketplace_status("Paused")


def test_translates_stock_and_completed_order() -> None:
    async def scenario() -> None:
        bridge = RbxcreateBridge(FakeGateway())  # type: ignore[arg-type]
        stock = await bridge.get_detailed_stock()
        result = await bridge.get_order_info("external-1")

        assert stock[0].rate == Decimal("1.25")
        assert stock[0].total_robux_amount == 7000
        assert result.external_order_id == "external-1"
        assert result.status is MarketplaceOrderStatus.COMPLETED
        assert result.purchased_quantity == 1000
        assert result.remaining_quantity == 0
        assert result.price == Decimal("12.50")

    asyncio.run(scenario())
