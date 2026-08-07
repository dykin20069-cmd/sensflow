"""Contract tests for the synchronous RBXCrate infrastructure gateway."""

import asyncio
import json
import logging
from collections.abc import Callable
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError

from sensflow.integrations.rbxcreate.client import REQUEST_TIMEOUT
from sensflow.integrations.rbxcreate.errors import (
    RbxcrateApiError,
    RbxcrateAuthenticationError,
    RbxcrateDailyLimitReachedError,
    RbxcrateDuplicateOrderError,
    RbxcrateError,
    RbxcrateInsufficientFundsError,
    RbxcrateInsufficientStockError,
    RbxcrateOrderNotFoundError,
    RbxcrateUnsupportedStatusError,
    RbxcrateValidationError,
)
from sensflow.integrations.rbxcreate.gateway import RbxcrateGateway
from sensflow.integrations.rbxcreate.models import StockResponse

Handler = Callable[[httpx.Request], httpx.Response]
API_KEY = "rbxcrate-super-secret"
BASE_URL = "https://rbxcrate.test"


def gateway(
    handler: Handler,
    *,
    delays: list[float] | None = None,
) -> RbxcrateGateway:
    async def record_sleep(delay: float) -> None:
        if delays is not None:
            delays.append(delay)

    return RbxcrateGateway(
        api_key=API_KEY,
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
        sleep=record_sleep,
    )


def create_response() -> dict[str, object]:
    return {
        "success": True,
        "data": {
            "orderId": "order-1",
            "robloxUsername": "Builderman",
            "robloxUserId": 42,
            "robuxAmount": 100,
            "status": "queued-by-provider",
            "universeId": {},
            "placeId": {},
            "gamepassId": {},
        },
    }


def test_create_order_with_place_id_uses_exact_contract_and_api_key_header() -> None:
    async def exercise() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.url.path == "/api/orders/gamepass"
            assert request.headers["api-key"] == API_KEY
            assert "Authorization" not in request.headers
            assert json.loads(request.content) == {
                "robloxUsername": "Builderman",
                "orderId": "order-1",
                "robuxAmount": 100,
                "gamepassId": 200,
                "placeId": 300,
                "isPreOrder": False,
                "checkOwnership": False,
            }
            return httpx.Response(200, json=create_response())

        async with gateway(handler) as client:
            response = await client.create_gamepass_order(
                roblox_username="Builderman",
                order_id="order-1",
                robux_amount=100,
                gamepass_id=200,
                place_id=300,
                is_preorder=False,
                check_ownership=False,
            )

        assert response.success is True
        assert response.data.order_id == "order-1"
        assert response.data.status == "queued-by-provider"

    asyncio.run(exercise())


def test_create_order_without_place_id_omits_the_json_field() -> None:
    async def exercise() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert "placeId" not in json.loads(request.content)
            return httpx.Response(200, json=create_response())

        async with gateway(handler) as client:
            await client.create_gamepass_order(
                roblox_username="Builderman",
                order_id="order-1",
                robux_amount=100,
                gamepass_id=200,
                place_id=None,
                is_preorder=True,
                check_ownership=True,
            )

    asyncio.run(exercise())


def test_place_only_order_omits_gamepass_id() -> None:
    async def exercise() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            assert payload["placeId"] == 300
            assert "gamepassId" not in payload
            return httpx.Response(200, json=create_response())

        async with gateway(handler) as client:
            await client.create_gamepass_order(
                roblox_username="Builderman",
                order_id="order-1",
                robux_amount=100,
                place_id=300,
                is_preorder=False,
                check_ownership=True,
            )

    asyncio.run(exercise())


def test_resend_place_id_uses_the_resend_endpoint() -> None:
    async def exercise() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/orders/gamepass/resend"
            assert json.loads(request.content) == {"orderId": "order-1", "placeId": 300}
            return httpx.Response(200, json={"success": True, "data": {"success": True}})

        async with gateway(handler) as client:
            response = await client.resend_gamepass_order(order_id="order-1", place_id=300)

        assert response.data.success is True

    asyncio.run(exercise())


def test_stock_and_detailed_stock_return_typed_values() -> None:
    async def exercise() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/orders/stock":
                return httpx.Response(
                    200,
                    json={"robuxAvailable": 1000, "maxRobuxAvailable": 5000},
                )
            assert request.url.path == "/api/orders/detailed-stock"
            return httpx.Response(
                200,
                json=[
                    {
                        "rate": 4.6,
                        "accountsCount": 12,
                        "maxInstantOrder": 15000,
                        "totalRobuxAmount": 42000,
                    }
                ],
            )

        async with gateway(handler) as client:
            stock = await client.get_stock()
            detailed = await client.get_detailed_stock()

        assert stock.robux_available == 1000
        assert stock.max_robux_available == 5000
        assert detailed[0].rate == Decimal("4.6")
        assert detailed[0].accounts_count == 12

    asyncio.run(exercise())


def test_order_info_preserves_raw_status_and_allows_null_vendor_and_error() -> None:
    async def exercise() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/orders/info"
            assert json.loads(request.content) == {"orderId": "order-1"}
            return httpx.Response(
                200,
                json={
                    "type": "gamepass",
                    "uuid": "remote-uuid",
                    "price": 12.5,
                    "vendorId": None,
                    "robuxAmount": 100,
                    "status": "arbitrary-provider-status",
                    "robloxUserId": 42,
                    "robloxUsername": "Builderman",
                    "error": None,
                },
            )

        async with gateway(handler) as client:
            response = await client.get_order_info(order_id="order-1")

        assert response.vendor_id is None
        assert response.error is None
        assert response.raw_status == "arbitrary-provider-status"
        assert response.price == Decimal("12.5")

    asyncio.run(exercise())


def test_order_info_allows_price_to_be_unavailable() -> None:
    async def exercise() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "type": "gamepass",
                    "uuid": "remote-uuid",
                    "price": None,
                    "vendorId": None,
                    "robuxAmount": 100,
                    "status": "Pending",
                    "robloxUserId": 42,
                    "robloxUsername": "Builderman",
                    "error": None,
                },
            )

        async with gateway(handler) as client:
            response = await client.get_order_info(order_id="order-1")

        assert response.price is None

    asyncio.run(exercise())


def test_order_info_parses_optional_error_details_without_status_mapping() -> None:
    async def exercise() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "type": "gamepass",
                    "uuid": "remote-uuid",
                    "price": 0,
                    "vendorId": "vendor-1",
                    "robuxAmount": 100,
                    "status": "provider-failed",
                    "robloxUserId": 42,
                    "robloxUsername": "Builderman",
                    "error": {"reason": "ownership", "message": "Already owned"},
                },
            )

        async with gateway(handler) as client:
            response = await client.get_order_info(order_id="order-1")

        assert response.raw_status == "provider-failed"
        assert response.error is not None
        assert response.error.reason == "ownership"

    asyncio.run(exercise())


def test_cancel_order_and_balance_use_their_exact_endpoints() -> None:
    async def exercise() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/orders/cancel":
                assert json.loads(request.content) == {"orderId": "order-1"}
                return httpx.Response(200, json={"orderId": "order-1"})
            assert request.url.path == "/api/shared/balance"
            return httpx.Response(200, json={"balance": 123.45})

        async with gateway(handler) as client:
            cancellation = await client.cancel_order(order_id="order-1")
            balance = await client.get_balance()

        assert cancellation.order_id == "order-1"
        assert balance.balance == Decimal("123.45")

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (400, RbxcrateValidationError),
        (401, RbxcrateAuthenticationError),
        (402, RbxcrateInsufficientStockError),
        (403, RbxcrateInsufficientFundsError),
        (404, RbxcrateOrderNotFoundError),
        (409, RbxcrateDuplicateOrderError),
        (422, RbxcrateUnsupportedStatusError),
        (429, RbxcrateDailyLimitReachedError),
    ],
)
def test_4xx_errors_are_mapped_exactly_without_retry(
    status_code: int,
    error_type: type[RbxcrateError],
) -> None:
    async def exercise() -> None:
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(
                status_code,
                json={
                    "message": "Remote message",
                    "path": "/api/orders/stock",
                    "timestamp": "2026-08-07T08:00:00Z",
                },
            )

        async with gateway(handler) as client:
            with pytest.raises(error_type) as raised:
                await client.get_stock()

        assert attempts == 1
        assert raised.value.status_code == status_code
        assert "Remote message" in str(raised.value)
        assert "/api/orders/stock" in str(raised.value)
        assert "2026-08-07T08:00:00Z" in str(raised.value)

    asyncio.run(exercise())


def test_500_responses_are_retried_then_succeed() -> None:
    async def exercise() -> None:
        attempts = 0
        delays: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                return httpx.Response(500, json={"message": "Temporary failure"})
            return httpx.Response(200, json={"robuxAvailable": 10, "maxRobuxAvailable": 20})

        async with gateway(handler, delays=delays) as client:
            response = await client.get_stock()

        assert response.robux_available == 10
        assert attempts == 3
        assert delays == [0.5, 1.0]

    asyncio.run(exercise())


def test_unmapped_4xx_is_an_api_error_without_retry() -> None:
    async def exercise() -> None:
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(418, json={"message": "Unexpected client error"})

        async with gateway(handler) as client:
            with pytest.raises(RbxcrateApiError) as raised:
                await client.get_stock()

        assert raised.value.status_code == 418
        assert attempts == 1

    asyncio.run(exercise())


def test_server_error_after_all_attempts_is_an_api_error() -> None:
    async def exercise() -> None:
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(503, json={"message": "Still unavailable"})

        async with gateway(handler) as client:
            with pytest.raises(RbxcrateApiError) as raised:
                await client.get_stock()

        assert raised.value.status_code == 503
        assert attempts == 3

    asyncio.run(exercise())


def test_network_timeout_is_retried_then_succeeds() -> None:
    async def exercise() -> None:
        attempts = 0
        delays: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise httpx.ReadTimeout("temporary timeout", request=request)
            return httpx.Response(200, json={"balance": 50})

        async with gateway(handler, delays=delays) as client:
            response = await client.get_balance()

        assert response.balance == Decimal("50")
        assert attempts == 2
        assert delays == [0.5]

    asyncio.run(exercise())


def test_network_timeout_after_all_attempts_raises_api_error() -> None:
    async def exercise() -> None:
        attempts = 0
        delays: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            raise httpx.ReadTimeout("permanent timeout", request=request)

        async with gateway(handler, delays=delays) as client:
            with pytest.raises(RbxcrateApiError, match="3 attempts"):
                await client.get_balance()

        assert attempts == 3
        assert delays == [0.5, 1.0]

    asyncio.run(exercise())


def test_invalid_success_payload_raises_typed_api_error() -> None:
    async def exercise() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": True})

        async with gateway(handler) as client:
            with pytest.raises(RbxcrateApiError, match="invalid response"):
                await client.get_stock()

    asyncio.run(exercise())


def test_api_key_never_appears_in_request_logs(caplog: pytest.LogCaptureFixture) -> None:
    async def exercise() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"balance": 1})

        with caplog.at_level(logging.INFO, logger="sensflow.integrations.rbxcreate.client"):
            async with gateway(handler) as client:
                await client.get_balance()

        assert "method=GET" in caplog.text
        assert "path=/api/shared/balance" in caplog.text
        assert "status_code=200" in caplog.text
        assert API_KEY not in caplog.text

    asyncio.run(exercise())


def test_configured_timeouts_match_the_production_contract() -> None:
    assert REQUEST_TIMEOUT.connect == 5.0
    assert REQUEST_TIMEOUT.read == 15.0
    assert REQUEST_TIMEOUT.write == 15.0
    assert REQUEST_TIMEOUT.pool == 30.0


def test_api_models_are_immutable() -> None:
    response = StockResponse(robux_available=10, max_robux_available=20)

    with pytest.raises(ValidationError):
        response.robux_available = 30
