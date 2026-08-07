"""Deterministic safeguards for detailed RBXCrate stock selection."""

from decimal import Decimal

from sensflow.application.marketplace_workflows import _select_stock
from sensflow.application.rbxcreate_bridge import MarketplaceStock


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


def test_real_detailed_stock_selects_for_100_robux_order() -> None:
    stock = _stock("4.3")

    assert _select(stock) is stock


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
