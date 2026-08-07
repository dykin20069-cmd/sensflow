"""Immutable request and response models for the RBXCrate HTTP API."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RbxcrateModel(BaseModel):
    """Shared immutable configuration for RBXCrate payloads."""

    model_config = ConfigDict(
        frozen=True,
        populate_by_name=True,
        allow_inf_nan=False,
    )


class CreateGamepassOrderRequest(RbxcrateModel):
    roblox_username: str = Field(alias="robloxUsername", min_length=1)
    order_id: str = Field(alias="orderId", min_length=1)
    robux_amount: int = Field(alias="robuxAmount", gt=0)
    gamepass_id: int | None = Field(default=None, alias="gamepassId", gt=0)
    place_id: int | None = Field(default=None, alias="placeId", gt=0)
    is_preorder: bool = Field(alias="isPreOrder")
    check_ownership: bool = Field(alias="checkOwnership")


class CreateGamepassOrderData(RbxcrateModel):
    order_id: str = Field(alias="orderId")
    roblox_username: str = Field(alias="robloxUsername")
    roblox_user_id: int = Field(alias="robloxUserId", ge=0)
    robux_amount: int = Field(alias="robuxAmount", ge=0)
    status: str
    universe_id: int | dict[str, object] | None = Field(alias="universeId")
    place_id: int | dict[str, object] | None = Field(alias="placeId")
    gamepass_id: int | dict[str, object] | None = Field(alias="gamepassId")


class CreateGamepassOrderResponse(RbxcrateModel):
    success: bool
    data: CreateGamepassOrderData


class ResendGamepassOrderRequest(RbxcrateModel):
    order_id: str = Field(alias="orderId", min_length=1)
    place_id: int = Field(alias="placeId", gt=0)


class ResendGamepassOrderData(RbxcrateModel):
    success: bool


class ResendGamepassOrderResponse(RbxcrateModel):
    success: bool
    data: ResendGamepassOrderData


class StockResponse(RbxcrateModel):
    robux_available: int = Field(alias="robuxAvailable", ge=0)
    max_robux_available: int = Field(alias="maxRobuxAvailable", ge=0)


class DetailedStockItem(RbxcrateModel):
    rate: Decimal = Field(gt=0)
    accounts_count: int = Field(alias="accountsCount", ge=0)
    max_instant_order: int = Field(alias="maxInstantOrder", ge=0)
    total_robux_amount: int = Field(alias="totalRobuxAmount", ge=0)


class OrderInfoRequest(RbxcrateModel):
    order_id: str = Field(alias="orderId", min_length=1)


class OrderError(RbxcrateModel):
    reason: str
    message: str


class OrderInfoResponse(RbxcrateModel):
    order_type: str = Field(alias="type")
    uuid: str
    price: Decimal | None = Field(ge=0)
    vendor_id: str | None = Field(alias="vendorId")
    robux_amount: int = Field(alias="robuxAmount", ge=0)
    raw_status: str = Field(alias="status")
    roblox_user_id: int = Field(alias="robloxUserId", ge=0)
    roblox_username: str = Field(alias="robloxUsername")
    error: OrderError | None


class CancelOrderRequest(RbxcrateModel):
    order_id: str = Field(alias="orderId", min_length=1)


class CancelOrderResponse(RbxcrateModel):
    order_id: str = Field(alias="orderId")


class BalanceResponse(RbxcrateModel):
    balance: Decimal = Field(ge=0)
