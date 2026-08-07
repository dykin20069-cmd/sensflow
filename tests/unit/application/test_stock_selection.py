"""Deterministic safeguards for detailed RBXCrate stock selection."""

import asyncio
from decimal import Decimal
from uuid import uuid4

from sensflow.application.marketplace_workflows import (
    _select_preorders_maximum_clients,
    _select_stock,
)
from sensflow.application.rbxcreate_bridge import MarketplaceStock, RbxcreateBridge
from sensflow.integrations.rbxcreate.models import DetailedStockItem


class DetailedStockGateway:
    async def get_detailed_stock(self) -> tuple[DetailedStockItem, ...]:
        return (
            DetailedStockItem(
                rate=Decimal("4.2"),
                accounts_count=3,
                max_instant_order=427,
                total_robux_amount=1325,
            ),
            DetailedStockItem(
                rate=Decimal("4.3"),
                accounts_count=25,
                max_instant_order=338,
                total_robux_amount=9071,
            ),
            DetailedStockItem(
                rate=Decimal("4.5"),
                accounts_count=1,
                max_instant_order=257,
                total_robux_amount=367,
            ),
        )


def _stock(
    rate: str,
    *,
    total_robux_amount: int = 9071,
    max_instant_order: int = 338,
    accounts_count: int = 25,
) -> MarketplaceStock:
    return MarketplaceStock(
        rate=Decimal(rate),
        accounts_count=accounts_count,
        max_instant_order=max_instant_order,
        total_robux_amount=total_robux_amount,
    )


def _select(
    *stock: MarketplaceStock,
    requested_robux: int = 100,
    minimum_purchase_rate: str = "4.0",
    maximum_purchase_rate: str = "5.0",
) -> MarketplaceStock | None:
    return _select_stock(
        stock,
        requested_robux=requested_robux,
        minimum_purchase_rate=Decimal(minimum_purchase_rate),
        maximum_purchase_rate=Decimal(maximum_purchase_rate),
    )


def test_real_detailed_stock_selects_cheapest_entry_for_100_robux_order() -> None:
    bridge = RbxcreateBridge(DetailedStockGateway())  # type: ignore[arg-type]
    stock = asyncio.run(bridge.get_detailed_stock())

    selected = _select(*stock, minimum_purchase_rate="0", maximum_purchase_rate="4.5")

    assert selected is not None
    assert selected.rate == Decimal("4.2")
    assert selected.max_instant_order == 427
    assert selected.total_robux_amount == 1325


def test_stock_with_insufficient_max_instant_order_is_rejected() -> None:
    assert _select(_stock("4.3", max_instant_order=99)) is None


def test_stock_with_insufficient_total_robux_amount_is_rejected() -> None:
    assert _select(_stock("4.3", total_robux_amount=99)) is None


def test_rate_above_maximum_purchase_rate_is_rejected() -> None:
    assert _select(_stock("5.01")) is None


def test_rate_below_minimum_purchase_rate_is_rejected() -> None:
    assert _select(_stock("3.99")) is None


def test_lowest_valid_rate_is_selected() -> None:
    selected = _select(_stock("4.7"), _stock("4.3"), _stock("4.5"))

    assert selected is not None
    assert selected.rate == Decimal("4.3")


def test_equal_rate_uses_largest_available_stock() -> None:
    selected = _select(
        _stock("4.3", total_robux_amount=2000),
        _stock("4.3", total_robux_amount=9000),
        _stock("4.3", total_robux_amount=5000),
    )

    assert selected is not None
    assert selected.total_robux_amount == 9000


def test_maximum_clients_strategy_fits_smallest_complete_preorders_first() -> None:
    order_ids = tuple(uuid4() for _ in range(4))
    stock = (_stock("4.2", total_robux_amount=1000, max_instant_order=1000),)

    selected, selected_stock = _select_preorders_maximum_clients(
        tuple(zip(order_ids, (229, 231, 514, 950), strict=True)),
        stock,
        minimum_purchase_rate=Decimal("0"),
        maximum_purchase_rate=Decimal("4.5"),
    )

    assert selected == order_ids[:3]
    assert selected_stock is stock[0]
