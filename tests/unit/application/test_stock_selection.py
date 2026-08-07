"""Deterministic safeguards for detailed RBXCrate stock selection."""

from decimal import Decimal
from uuid import uuid4

from sensflow.application.marketplace_workflows import _select_stock
from sensflow.application.rbxcreate_bridge import MarketplaceStock
from sensflow.domain.enums import ClientOrderStatus
from sensflow.infrastructure.database.models import ClientOrder


def _order() -> ClientOrder:
    order = ClientOrder(
        customer_id=uuid4(),
        requested_robux=1000,
        current_status=ClientOrderStatus.PREORDER,
        current_place_id=77,
        marketplace_rate_limit=Decimal("2.50"),
    )
    order.id = uuid4()
    return order


def _stock(
    rate: str,
    *,
    total: int = 5000,
    maximum: int = 5000,
    accounts: int = 1,
) -> MarketplaceStock:
    return MarketplaceStock(
        rate=Decimal(rate),
        accounts_count=accounts,
        max_instant_order=maximum,
        total_robux_amount=total,
    )


def test_no_stock_returns_no_selection() -> None:
    assert _select_stock((), _order()) is None


def test_insufficient_total_or_instant_stock_is_ignored() -> None:
    stock = (
        _stock("1.00", total=999),
        _stock("1.10", maximum=999),
        _stock("1.20", accounts=0),
    )

    assert _select_stock(stock, _order()) is None


def test_rate_above_order_limit_is_ignored() -> None:
    assert _select_stock((_stock("2.51"),), _order()) is None


def test_lowest_valid_rate_is_selected() -> None:
    selected = _select_stock(
        (_stock("2.25"), _stock("1.75"), _stock("2.00")),
        _order(),
    )

    assert selected is not None
    assert selected.rate == Decimal("1.75")


def test_equal_rate_uses_largest_available_stock() -> None:
    selected = _select_stock(
        (
            _stock("1.75", total=2000),
            _stock("1.75", total=9000),
            _stock("1.75", total=5000),
        ),
        _order(),
    )

    assert selected is not None
    assert selected.total_robux_amount == 9000
