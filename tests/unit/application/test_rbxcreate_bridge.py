"""Application boundary tests for typed RBXCrate translation."""

import asyncio
import logging
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from sensflow.application.errors import (
    MarketplaceGamepassNotFoundError,
    MarketplaceIntegrationError,
    MarketplaceRateLimitedError,
    UnknownMarketplaceStatusError,
)
from sensflow.application.rbxcreate_bridge import (
    GAMEPASS_NOT_FOUND_MESSAGE,
    RbxcreateBridge,
    map_marketplace_status,
)
from sensflow.domain.enums import MarketplaceOrderStatus
from sensflow.integrations.rbxcreate.errors import (
    RbxcrateApiError,
    RbxcrateDailyLimitReachedError,
    RbxcrateOrderNotFoundError,
)
from sensflow.integrations.rbxcreate.models import (
    CreateGamepassOrderResponse,
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


def create_response() -> CreateGamepassOrderResponse:
    return CreateGamepassOrderResponse.model_validate(
        {
            "success": True,
            "data": {
                "orderId": "external-1",
                "robloxUsername": "Builderman",
                "robloxUserId": 42,
                "robuxAmount": 100,
                "status": "Pending",
                "universeId": {},
                "placeId": 300,
                "gamepassId": {},
            },
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


def test_translates_status_polling_429_without_losing_http_metadata() -> None:
    async def scenario() -> None:
        gateway = FakeGateway()

        async def rate_limited(*, order_id: str) -> OrderInfoResponse:
            raise RbxcrateDailyLimitReachedError(
                f"So fast for {order_id}",
                status_code=429,
                path="/api/orders/info",
            )

        gateway.get_order_info = rate_limited  # type: ignore[method-assign]
        bridge = RbxcreateBridge(gateway)  # type: ignore[arg-type]

        with pytest.raises(MarketplaceRateLimitedError) as raised:
            await bridge.get_order_info("external-1")

        assert raised.value.status_code == 429
        assert raised.value.error_type == "RbxcrateDailyLimitReachedError"

    asyncio.run(scenario())


def test_place_only_404_is_logged_and_translated_to_a_specific_gamepass_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        gateway = FakeGateway()

        create_order = AsyncMock(
            side_effect=RbxcrateOrderNotFoundError(
                "No gamepass for place 300",
                status_code=404,
                path="/api/orders/gamepass",
                response_text='{"message":"Gamepass not found"}',
            )
        )
        gateway.create_gamepass_order = create_order  # type: ignore[attr-defined]
        bridge = RbxcreateBridge(gateway)  # type: ignore[arg-type]

        with (
            caplog.at_level(logging.INFO),
            pytest.raises(MarketplaceGamepassNotFoundError) as raised,
        ):
            await bridge.create_gamepass_order(
                roblox_username="Builderman",
                order_id="order-1",
                robux_amount=100,
                place_id=300,
            )

        assert str(raised.value) == GAMEPASS_NOT_FOUND_MESSAGE
        assert raised.value.status_code == 404
        assert raised.value.response_text == '{"message":"Gamepass not found"}'
        assert "rbxcrate_quick_order_request" in caplog.text
        assert "username=Builderman amount=100 place_id=300 gamepass_id=None" in caplog.text
        assert "rbxcrate_quick_order_failed" in caplog.text
        assert 'body={"message":"Gamepass not found"}' in caplog.text
        assert create_order.await_count == 1

    asyncio.run(scenario())


def test_404_with_explicit_gamepass_id_keeps_generic_integration_handling() -> None:
    async def scenario() -> None:
        gateway = FakeGateway()

        create_order = AsyncMock(
            side_effect=RbxcrateOrderNotFoundError(
                "Missing gamepass 200",
                status_code=404,
                response_text='{"message":"Not found"}',
            )
        )
        gateway.create_gamepass_order = create_order  # type: ignore[attr-defined]
        bridge = RbxcreateBridge(gateway)  # type: ignore[arg-type]

        with pytest.raises(MarketplaceIntegrationError) as raised:
            await bridge.create_gamepass_order(
                roblox_username="Builderman",
                order_id="order-1",
                robux_amount=100,
                place_id=300,
                gamepass_id=200,
            )

        assert not isinstance(raised.value, MarketplaceGamepassNotFoundError)
        assert create_order.await_count == 1

    asyncio.run(scenario())


def test_instant_gamepass_order_success_does_not_call_preorder() -> None:
    async def scenario() -> None:
        gateway = FakeGateway()
        create_order = AsyncMock(return_value=create_response())
        gateway.create_gamepass_order = create_order  # type: ignore[attr-defined]
        bridge = RbxcreateBridge(gateway)  # type: ignore[arg-type]

        result = await bridge.create_gamepass_order(
            roblox_username="Builderman",
            order_id="order-1",
            robux_amount=100,
            place_id=300,
        )

        assert create_order.await_count == 1
        assert create_order.await_args.kwargs["is_preorder"] is False
        assert result.external_order_id == "external-1"
        assert result.status is MarketplaceOrderStatus.ACTIVE
        assert result.is_preorder is False

    asyncio.run(scenario())


def test_instant_out_of_stock_retries_once_as_preorder(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        gateway = FakeGateway()
        create_order = AsyncMock(
            side_effect=(
                RbxcrateApiError(
                    "out of stock",
                    status_code=402,
                    response_text='{"code":"OUT_OF_STOCK"}',
                ),
                create_response(),
            )
        )
        gateway.create_gamepass_order = create_order  # type: ignore[attr-defined]
        bridge = RbxcreateBridge(gateway)  # type: ignore[arg-type]

        with caplog.at_level(logging.INFO):
            result = await bridge.create_gamepass_order(
                roblox_username="Builderman",
                order_id="order-1",
                robux_amount=100,
                place_id=300,
            )

        assert create_order.await_count == 2
        assert create_order.await_args_list[0].kwargs["is_preorder"] is False
        assert create_order.await_args_list[1].kwargs["is_preorder"] is True
        assert create_order.await_args_list[1].kwargs["order_id"] == "order-1"
        assert result.is_preorder is True
        assert "rbxcrate_instant_out_of_stock_fallback_to_preorder" in caplog.text
        assert "rbxcrate_preorder_created" in caplog.text
        assert "rbxcrate_quick_order_failed" not in caplog.text

    asyncio.run(scenario())


def test_preorder_fallback_failure_is_logged_once_and_translated(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        gateway = FakeGateway()
        create_order = AsyncMock(
            side_effect=(
                RbxcrateApiError(
                    "out of stock",
                    status_code=402,
                    response_text='{"code":"OUT_OF_STOCK"}',
                ),
                RbxcrateApiError(
                    "preorder failed",
                    status_code=503,
                    response_text='{"message":"Unavailable"}',
                ),
            )
        )
        gateway.create_gamepass_order = create_order  # type: ignore[attr-defined]
        bridge = RbxcreateBridge(gateway)  # type: ignore[arg-type]

        with (
            caplog.at_level(logging.INFO),
            pytest.raises(MarketplaceIntegrationError) as raised,
        ):
            await bridge.create_gamepass_order(
                roblox_username="Builderman",
                order_id="order-1",
                robux_amount=100,
                place_id=300,
            )

        assert raised.value.status_code == 503
        assert create_order.await_count == 2
        assert caplog.text.count("rbxcrate_quick_order_failed") == 1
        assert "rbxcrate_instant_out_of_stock_fallback_to_preorder" in caplog.text
        assert "rbxcrate_preorder_created" not in caplog.text

    asyncio.run(scenario())
