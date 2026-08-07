"""High-level typed gateway for the synchronous RBXCrate endpoints."""

import asyncio
from collections.abc import Awaitable, Callable

import httpx
from pydantic import BaseModel, SecretStr, TypeAdapter, ValidationError

from sensflow.integrations.rbxcreate.client import RbxcrateClient
from sensflow.integrations.rbxcreate.errors import RbxcrateApiError
from sensflow.integrations.rbxcreate.models import (
    BalanceResponse,
    CancelOrderRequest,
    CancelOrderResponse,
    CreateGamepassOrderRequest,
    CreateGamepassOrderResponse,
    DetailedStockItem,
    OrderInfoRequest,
    OrderInfoResponse,
    ResendGamepassOrderRequest,
    ResendGamepassOrderResponse,
    StockResponse,
)

RetrySleep = Callable[[float], Awaitable[None]]


class RbxcrateGateway:
    """Perform typed RBXCrate calls without business state transitions."""

    def __init__(
        self,
        *,
        api_key: SecretStr | str,
        base_url: str = "https://rbxcrate.com",
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: RetrySleep = asyncio.sleep,
    ) -> None:
        self._client = RbxcrateClient(
            api_key=api_key,
            base_url=base_url,
            transport=transport,
            sleep=sleep,
        )

    async def create_gamepass_order(
        self,
        *,
        roblox_username: str,
        order_id: str,
        robux_amount: int,
        place_id: int | None,
        is_preorder: bool,
        check_ownership: bool,
        gamepass_id: int | None = None,
    ) -> CreateGamepassOrderResponse:
        request = CreateGamepassOrderRequest(
            roblox_username=roblox_username,
            order_id=order_id,
            robux_amount=robux_amount,
            gamepass_id=gamepass_id,
            place_id=place_id,
            is_preorder=is_preorder,
            check_ownership=check_ownership,
        )
        response = await self._client.post(
            "/api/orders/gamepass",
            request.model_dump(mode="json", by_alias=True, exclude_none=True),
        )
        return _parse_model(response, CreateGamepassOrderResponse)

    async def resend_gamepass_order(
        self,
        *,
        order_id: str,
        place_id: int,
    ) -> ResendGamepassOrderResponse:
        request = ResendGamepassOrderRequest(order_id=order_id, place_id=place_id)
        response = await self._client.post(
            "/api/orders/gamepass/resend",
            request.model_dump(mode="json", by_alias=True),
        )
        return _parse_model(response, ResendGamepassOrderResponse)

    async def get_stock(self) -> StockResponse:
        response = await self._client.get("/api/orders/stock")
        return _parse_model(response, StockResponse)

    async def get_detailed_stock(self) -> tuple[DetailedStockItem, ...]:
        response = await self._client.get("/api/orders/detailed-stock")
        try:
            return TypeAdapter(tuple[DetailedStockItem, ...]).validate_python(response.json())
        except (ValueError, ValidationError) as error:
            raise _unexpected_response(response) from error

    async def get_order_info(self, *, order_id: str) -> OrderInfoResponse:
        request = OrderInfoRequest(order_id=order_id)
        response = await self._client.post(
            "/api/orders/info",
            request.model_dump(mode="json", by_alias=True),
        )
        return _parse_model(response, OrderInfoResponse)

    async def cancel_order(self, *, order_id: str) -> CancelOrderResponse:
        request = CancelOrderRequest(order_id=order_id)
        response = await self._client.post(
            "/api/orders/cancel",
            request.model_dump(mode="json", by_alias=True),
        )
        return _parse_model(response, CancelOrderResponse)

    async def get_balance(self) -> BalanceResponse:
        response = await self._client.get("/api/shared/balance")
        return _parse_model(response, BalanceResponse)

    async def aclose(self) -> None:
        """Close the gateway's reusable HTTP connection pool."""
        await self._client.aclose()

    async def __aenter__(self) -> "RbxcrateGateway":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()


def _parse_model[ResponseModel: BaseModel](
    response: httpx.Response,
    model: type[ResponseModel],
) -> ResponseModel:
    try:
        return model.model_validate(response.json())
    except (ValueError, ValidationError) as error:
        raise _unexpected_response(response) from error


def _unexpected_response(response: httpx.Response) -> RbxcrateApiError:
    return RbxcrateApiError(
        f"RBXCrate returned an invalid response for {response.request.url.path}",
        status_code=response.status_code,
        path=response.request.url.path,
    )
