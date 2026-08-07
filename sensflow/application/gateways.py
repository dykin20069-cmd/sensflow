"""External capability contracts needed by business orchestration."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sensflow.application.errors import FeatureUnavailableError
from sensflow.domain.customer.service import RobloxIdentity
from sensflow.domain.marketplace.service import MarketplaceOrderResult


@dataclass(frozen=True, slots=True)
class MarketplaceCancellationResult:
    """Confirmed quantities returned after cancelling an external attempt."""

    purchased_robux: int
    remaining_robux: int


class RobloxGateway(Protocol):
    """Roblox identity capabilities implemented in the later API milestone."""

    async def resolve_username(self, username: str) -> RobloxIdentity: ...

    async def refresh_identity(self, roblox_user_id: int) -> RobloxIdentity: ...

    async def discover_place_id(self, roblox_user_id: int) -> int | None: ...


class MarketplaceGateway(Protocol):
    """RBXCreate capabilities implemented in the later API milestone."""

    async def has_suitable_stock(self, requested_robux: int, maximum_rate: Decimal) -> bool: ...

    async def create_order(
        self,
        *,
        client_order_id: UUID,
        place_id: int,
        requested_robux: int,
        maximum_rate: Decimal,
    ) -> MarketplaceOrderResult: ...

    async def cancel_order(self, external_order_id: str) -> MarketplaceCancellationResult: ...


class UnavailableRobloxGateway:
    """Safe production boundary until Roblox integration is implemented."""

    async def resolve_username(self, username: str) -> RobloxIdentity:
        raise FeatureUnavailableError("Roblox identity lookup")

    async def refresh_identity(self, roblox_user_id: int) -> RobloxIdentity:
        raise FeatureUnavailableError("Roblox identity refresh")

    async def discover_place_id(self, roblox_user_id: int) -> int | None:
        raise FeatureUnavailableError("Roblox Place ID discovery")


class UnavailableMarketplaceGateway:
    """Safe production boundary until RBXCreate integration is implemented."""

    async def has_suitable_stock(self, requested_robux: int, maximum_rate: Decimal) -> bool:
        raise FeatureUnavailableError("Marketplace stock lookup")

    async def create_order(
        self,
        *,
        client_order_id: UUID,
        place_id: int,
        requested_robux: int,
        maximum_rate: Decimal,
    ) -> MarketplaceOrderResult:
        raise FeatureUnavailableError("Marketplace Order creation")

    async def cancel_order(self, external_order_id: str) -> MarketplaceCancellationResult:
        raise FeatureUnavailableError("Marketplace Order cancellation")
