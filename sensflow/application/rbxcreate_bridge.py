"""Translate the typed RBXCrate adapter into application-level results."""

from dataclasses import dataclass
from decimal import Decimal

from sensflow.application.errors import (
    MarketplaceCancellationUnsupportedError,
    MarketplaceIntegrationError,
    UnknownMarketplaceStatusError,
)
from sensflow.domain.enums import MarketplaceOrderStatus
from sensflow.integrations.rbxcreate.dry_run import RbxcrateDryRunGateway
from sensflow.integrations.rbxcreate.errors import (
    RbxcrateError,
    RbxcrateUnsupportedStatusError,
)
from sensflow.integrations.rbxcreate.gateway import RbxcrateGateway
from sensflow.integrations.rbxcreate.models import OrderInfoResponse


@dataclass(frozen=True, slots=True)
class MarketplaceStock:
    """Stock values needed by the purchase selection rule."""

    rate: Decimal
    accounts_count: int
    max_instant_order: int
    total_robux_amount: int


@dataclass(frozen=True, slots=True)
class MarketplaceCreateResult:
    """Application result of creating one external order."""

    external_order_id: str
    status: MarketplaceOrderStatus


@dataclass(frozen=True, slots=True)
class MarketplaceSyncResult:
    """Application-safe snapshot returned by marketplace synchronization."""

    external_order_id: str
    status: MarketplaceOrderStatus
    purchased_quantity: int | None
    remaining_quantity: int | None
    vendor_id: str | None
    price: Decimal | None
    error_reason: str | None
    error_message: str | None


_STATUS_MAP = {
    "pending": MarketplaceOrderStatus.ACTIVE,
    "queued": MarketplaceOrderStatus.ACTIVE,
    "processing": MarketplaceOrderStatus.ACTIVE,
    "completed": MarketplaceOrderStatus.COMPLETED,
    "cancelled": MarketplaceOrderStatus.CANCELLED,
    "error": MarketplaceOrderStatus.CANCELLED,
}


class RbxcreateBridge:
    """Keep RBXCrate models and exceptions out of business orchestration."""

    def __init__(self, gateway: RbxcrateGateway | RbxcrateDryRunGateway) -> None:
        self._gateway = gateway

    async def get_detailed_stock(self) -> tuple[MarketplaceStock, ...]:
        try:
            items = await self._gateway.get_detailed_stock()
        except RbxcrateError as error:
            raise MarketplaceIntegrationError("RBXCrate stock is unavailable") from error
        return tuple(
            MarketplaceStock(
                rate=item.rate,
                accounts_count=item.accounts_count,
                max_instant_order=item.max_instant_order,
                total_robux_amount=item.total_robux_amount,
            )
            for item in items
        )

    async def create_gamepass_order(
        self,
        *,
        roblox_username: str,
        order_id: str,
        robux_amount: int,
        place_id: int,
        gamepass_id: int | None = None,
    ) -> MarketplaceCreateResult:
        try:
            response = await self._gateway.create_gamepass_order(
                roblox_username=roblox_username,
                order_id=order_id,
                robux_amount=robux_amount,
                gamepass_id=gamepass_id,
                place_id=place_id,
                is_preorder=False,
                check_ownership=True,
            )
        except RbxcrateError as error:
            raise MarketplaceIntegrationError("RBXCrate could not create the order") from error
        if not response.success:
            raise MarketplaceIntegrationError("RBXCrate did not accept the order")
        return MarketplaceCreateResult(
            external_order_id=response.data.order_id,
            status=map_marketplace_status(response.data.status),
        )

    async def get_order_info(self, external_order_id: str) -> MarketplaceSyncResult:
        try:
            response = await self._gateway.get_order_info(order_id=external_order_id)
        except RbxcrateError as error:
            raise MarketplaceIntegrationError("RBXCrate order status is unavailable") from error
        return _sync_result(response, external_order_id)

    async def cancel_order(self, external_order_id: str) -> None:
        try:
            await self._gateway.cancel_order(order_id=external_order_id)
        except RbxcrateUnsupportedStatusError as error:
            raise MarketplaceCancellationUnsupportedError(
                "RBXCrate requires the latest order status"
            ) from error
        except RbxcrateError as error:
            raise MarketplaceIntegrationError("RBXCrate could not cancel the order") from error

    async def get_balance(self) -> Decimal:
        """Return the account balance without exposing an infrastructure model."""
        try:
            response = await self._gateway.get_balance()
        except RbxcrateError as error:
            raise MarketplaceIntegrationError("RBXCrate balance is unavailable") from error
        return response.balance


def map_marketplace_status(raw_status: str) -> MarketplaceOrderStatus:
    """Map exactly the V1 statuses approved by the integration contract."""
    normalized = raw_status.strip().casefold()
    try:
        return _STATUS_MAP[normalized]
    except KeyError:
        raise UnknownMarketplaceStatusError(raw_status) from None


def _sync_result(response: OrderInfoResponse, external_order_id: str) -> MarketplaceSyncResult:
    status = map_marketplace_status(response.raw_status)
    # The typed endpoint provides only one quantity. It is definitive only after
    # completion; active/cancelled progress remains the persisted snapshot.
    purchased = response.robux_amount if status is MarketplaceOrderStatus.COMPLETED else None
    remaining = 0 if status is MarketplaceOrderStatus.COMPLETED else None
    return MarketplaceSyncResult(
        external_order_id=external_order_id,
        status=status,
        purchased_quantity=purchased,
        remaining_quantity=remaining,
        vendor_id=response.vendor_id,
        price=response.price,
        error_reason=None if response.error is None else response.error.reason,
        error_message=None if response.error is None else response.error.message,
    )
