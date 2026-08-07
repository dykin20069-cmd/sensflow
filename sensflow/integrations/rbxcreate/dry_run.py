"""Deterministic in-memory RBXCrate adapter for safe end-to-end dry runs."""

from dataclasses import dataclass
from decimal import Decimal

from sensflow.integrations.rbxcreate.errors import RbxcrateOrderNotFoundError
from sensflow.integrations.rbxcreate.models import (
    BalanceResponse,
    CancelOrderResponse,
    CreateGamepassOrderData,
    CreateGamepassOrderResponse,
    DetailedStockItem,
    OrderInfoResponse,
    ResendGamepassOrderData,
    ResendGamepassOrderResponse,
    StockResponse,
)

_DRY_RUN_BALANCE = Decimal("9999.99")
_DRY_RUN_RATE = Decimal("0.00000001")
_DRY_RUN_STOCK = 1_000_000_000


@dataclass(slots=True)
class _DryRunOrder:
    order_id: str
    username: str
    robux_amount: int
    place_id: int | None
    gamepass_id: int | None
    polls: int = 0
    cancelled: bool = False


class RbxcrateDryRunGateway:
    """Mimic the typed gateway without network traffic or account spending."""

    def __init__(self) -> None:
        self._orders: dict[str, _DryRunOrder] = {}

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
        del is_preorder, check_ownership
        order = _DryRunOrder(
            order_id=order_id,
            username=roblox_username,
            robux_amount=robux_amount,
            place_id=place_id,
            gamepass_id=gamepass_id,
        )
        self._orders[order_id] = order
        return CreateGamepassOrderResponse(
            success=True,
            data=CreateGamepassOrderData(
                order_id=order_id,
                roblox_username=roblox_username,
                roblox_user_id=0,
                robux_amount=robux_amount,
                status="Pending",
                universe_id=None,
                place_id=place_id,
                gamepass_id=gamepass_id,
            ),
        )

    async def resend_gamepass_order(
        self,
        *,
        order_id: str,
        place_id: int,
    ) -> ResendGamepassOrderResponse:
        order = self._get_order(order_id)
        order.place_id = place_id
        return ResendGamepassOrderResponse(
            success=True,
            data=ResendGamepassOrderData(success=True),
        )

    async def get_stock(self) -> StockResponse:
        return StockResponse(
            robux_available=_DRY_RUN_STOCK,
            max_robux_available=_DRY_RUN_STOCK,
        )

    async def get_detailed_stock(self) -> tuple[DetailedStockItem, ...]:
        return (
            DetailedStockItem(
                rate=_DRY_RUN_RATE,
                accounts_count=1,
                max_instant_order=_DRY_RUN_STOCK,
                total_robux_amount=_DRY_RUN_STOCK,
            ),
        )

    async def get_order_info(self, *, order_id: str) -> OrderInfoResponse:
        order = self._get_order(order_id)
        if order.cancelled:
            status = "Cancelled"
        else:
            order.polls += 1
            status = "Processing" if order.polls == 1 else "Completed"
        return OrderInfoResponse(
            order_type="dry_run",
            uuid=f"dry-run-{order.order_id}",
            price=(Decimal(order.robux_amount) * _DRY_RUN_RATE),
            vendor_id=None,
            robux_amount=order.robux_amount,
            raw_status=status,
            roblox_user_id=0,
            roblox_username=order.username,
            error=None,
        )

    async def cancel_order(self, *, order_id: str) -> CancelOrderResponse:
        self._get_order(order_id).cancelled = True
        return CancelOrderResponse(order_id=order_id)

    async def get_balance(self) -> BalanceResponse:
        return BalanceResponse(balance=_DRY_RUN_BALANCE)

    async def aclose(self) -> None:
        """Match the live gateway lifecycle without owning external resources."""

    def _get_order(self, order_id: str) -> _DryRunOrder:
        try:
            return self._orders[order_id]
        except KeyError:
            raise RbxcrateOrderNotFoundError("Dry-run order was not found") from None
