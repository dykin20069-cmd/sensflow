"""Stateless Client Order lifecycle rules."""

from datetime import datetime, timedelta
from decimal import Decimal

from sensflow.domain.enums import ClientOrderStatus
from sensflow.domain.errors import DomainConflictError, DomainValidationError
from sensflow.domain.order.state_machine import validate_transition
from sensflow.infrastructure.database.models import ClientOrder, Customer


def create_draft(
    customer: Customer,
    requested_robux: int,
    place_id: int,
    marketplace_rate_limit: Decimal,
    preferred_rate: Decimal | None = None,
    preferred_timeout_minutes: int | None = None,
) -> ClientOrder:
    """Create a structurally valid unpaid Client Order snapshot."""
    _validate_requested_robux(requested_robux)
    _validate_place_id(place_id)
    _validate_positive_decimal(marketplace_rate_limit, "Marketplace rate limit")
    selected_preferred_rate = preferred_rate or marketplace_rate_limit
    _validate_positive_decimal(selected_preferred_rate, "Preferred rate")
    if selected_preferred_rate > marketplace_rate_limit:
        raise DomainValidationError("Preferred rate must not exceed Marketplace rate limit")
    selected_timeout = 35 if preferred_timeout_minutes is None else preferred_timeout_minutes
    if selected_timeout <= 0:
        raise DomainValidationError("Preferred timeout must be greater than zero")
    return ClientOrder(
        customer_id=customer.id,
        requested_robux=requested_robux,
        current_status=ClientOrderStatus.DRAFT,
        current_place_id=place_id,
        marketplace_rate_limit=marketplace_rate_limit,
        preferred_rate=selected_preferred_rate,
        preferred_timeout_minutes=selected_timeout,
        fallback_active=False,
    )


def edit_draft(
    order: ClientOrder,
    *,
    requested_robux: int | None = None,
    place_id: int | None = None,
) -> None:
    """Edit only mutable Draft fields."""
    if order.current_status is not ClientOrderStatus.DRAFT:
        raise DomainConflictError("Only Draft orders can be edited")
    if requested_robux is None and place_id is None:
        raise DomainValidationError("At least one Draft field must be changed")
    if requested_robux is not None:
        _validate_requested_robux(requested_robux)
        order.requested_robux = requested_robux
    if place_id is not None:
        _validate_place_id(place_id)
        order.current_place_id = place_id


def enter_preorder(order: ClientOrder, now: datetime | None = None) -> None:
    """Move a paid Draft into the waiting state."""
    _transition(order, ClientOrderStatus.PREORDER)
    if (
        now is not None
        and order.preferred_expires_at is None
        and order.preferred_timeout_minutes is not None
    ):
        order.preferred_expires_at = now + timedelta(minutes=order.preferred_timeout_minutes)


def activate_fallback(order: ClientOrder, now: datetime) -> bool:
    """Enable the immutable maximum-rate fallback after preferred waiting expires."""
    if order.current_status is not ClientOrderStatus.PREORDER:
        raise DomainConflictError("Fallback can be activated only for a PreOrder")
    if order.fallback_active is True:
        return False
    if order.preferred_expires_at is None or now < order.preferred_expires_at:
        return False
    order.fallback_active = True
    return True


def effective_purchase_rate(order: ClientOrder, now: datetime) -> Decimal:
    """Return the preferred trigger until timeout, then the hard maximum rate."""
    if (
        order.preferred_rate is not None
        and order.fallback_active is not True
        and (order.preferred_expires_at is None or now < order.preferred_expires_at)
    ):
        return min(order.preferred_rate, order.marketplace_rate_limit)
    return order.marketplace_rate_limit


def start_purchasing(order: ClientOrder) -> None:
    """Move a paid Draft or selected PreOrder into execution."""
    _transition(order, ClientOrderStatus.PURCHASING)


def return_to_preorder(order: ClientOrder) -> None:
    """Return an interrupted purchase to the paid waiting state."""
    _transition(order, ClientOrderStatus.PREORDER)


def cancel_order(order: ClientOrder, now: datetime) -> None:
    """Cancel a non-terminal order while retaining its complete record."""
    _transition(order, ClientOrderStatus.CANCELLED)
    order.cancelled_at = now


def complete_order(
    order: ClientOrder,
    *,
    customer_receives: int,
    marketplace_cost: Decimal,
    marketplace_commission: Decimal,
    final_cost_usd: Decimal,
    final_cost_local_currency: Decimal,
    usd_exchange_rate: Decimal,
    now: datetime,
    executed_rate: Decimal | None = None,
) -> None:
    """Finalize all historical values together and make the order terminal."""
    if customer_receives < 0:
        raise DomainValidationError("Customer Receives must not be negative")
    for value, name in (
        (marketplace_cost, "Marketplace cost"),
        (marketplace_commission, "Marketplace commission"),
        (final_cost_usd, "Final cost USD"),
        (final_cost_local_currency, "Final cost local currency"),
    ):
        if value < 0:
            raise DomainValidationError(f"{name} must not be negative")
    _validate_positive_decimal(usd_exchange_rate, "USD exchange rate")
    if executed_rate is not None:
        _validate_positive_decimal(executed_rate, "Executed rate")
    _transition(order, ClientOrderStatus.COMPLETED)
    order.customer_receives = customer_receives
    order.marketplace_cost = marketplace_cost
    order.marketplace_commission = marketplace_commission
    order.final_cost_usd = final_cost_usd
    order.final_cost_local_currency = final_cost_local_currency
    order.usd_exchange_rate = usd_exchange_rate
    order.executed_rate = executed_rate
    order.completed_at = now


def _transition(order: ClientOrder, target: ClientOrderStatus) -> None:
    validate_transition(order.current_status, target)
    order.current_status = target


def _validate_requested_robux(value: int) -> None:
    if value <= 0:
        raise DomainValidationError("Requested Robux must be greater than zero")


def _validate_place_id(value: int) -> None:
    if value <= 0:
        raise DomainValidationError("Place ID must be greater than zero")


def _validate_positive_decimal(value: Decimal, name: str) -> None:
    if not value.is_finite() or value <= 0:
        raise DomainValidationError(f"{name} must be a finite value greater than zero")
