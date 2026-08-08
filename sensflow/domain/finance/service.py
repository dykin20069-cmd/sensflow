"""Deterministic Decimal-based financial calculations."""

from dataclasses import dataclass
from decimal import Decimal, DecimalException

from sensflow.domain.enums import ClientOrderStatus
from sensflow.domain.errors import DomainConflictError, DomainValidationError
from sensflow.infrastructure.database.models import ClientOrder


@dataclass(frozen=True, slots=True)
class FinancialSnapshot:
    """Final values persisted on a Completed Client Order."""

    marketplace_cost: Decimal
    marketplace_commission: Decimal
    final_cost_usd: Decimal
    final_cost_local_currency: Decimal
    usd_exchange_rate: Decimal


@dataclass(frozen=True, slots=True)
class PurchaseResult:
    """Actual immutable purchase values used by persistence and notifications."""

    requested_rate: Decimal
    executed_rate: Decimal
    marketplace_price_usd: Decimal
    commission_usd: Decimal
    total_paid_usd: Decimal


def create_purchase_result(
    *,
    requested_rate: Decimal,
    purchased_robux: int,
    financials: FinancialSnapshot,
) -> PurchaseResult:
    """Derive the effective paid rate from the final historical USD total."""
    _validate_decimal(requested_rate, "Requested rate", allow_zero=False)
    if purchased_robux <= 0:
        raise DomainValidationError("Purchased Robux must be greater than zero")
    executed_rate = (
        financials.final_cost_usd * Decimal("1000") / Decimal(purchased_robux)
    ).quantize(Decimal("0.00000001"))
    _validate_decimal(executed_rate, "Executed rate", allow_zero=False)
    return PurchaseResult(
        requested_rate=requested_rate,
        executed_rate=executed_rate,
        marketplace_price_usd=financials.marketplace_cost,
        commission_usd=financials.marketplace_commission,
        total_paid_usd=financials.final_cost_usd,
    )


def record_observed_marketplace_cost(order: ClientOrder, cost: Decimal) -> None:
    """Store a provisional price only while a purchase attempt is active."""
    if order.current_status is not ClientOrderStatus.PURCHASING:
        raise DomainConflictError(
            "Marketplace cost can be observed only while an order is Purchasing"
        )
    _validate_decimal(cost, "Marketplace cost", allow_zero=True)
    order.marketplace_cost = cost


def calculate_customer_receives(
    requested_robux: int,
    *,
    tax_rate: Decimal,
    rounding: str,
) -> int:
    """Apply an explicit Roblox tax and rounding policy to integer Robux."""
    if requested_robux <= 0:
        raise DomainValidationError("Requested Robux must be greater than zero")
    if not tax_rate.is_finite() or not Decimal("0") <= tax_rate < Decimal("1"):
        raise DomainValidationError("Roblox tax rate must be at least zero and below one")
    try:
        receives = (Decimal(requested_robux) * (Decimal("1") - tax_rate)).to_integral_value(
            rounding=rounding
        )
    except (DecimalException, TypeError, ValueError) as error:
        raise DomainValidationError("Robux rounding policy is invalid") from error
    return int(receives)


def calculate_financial_snapshot(
    *,
    marketplace_cost: Decimal,
    commission_rate: Decimal,
    usd_exchange_rate: Decimal,
    money_quantum: Decimal,
    rounding: str,
) -> FinancialSnapshot:
    """Calculate commission and final costs from the actual marketplace cost."""
    _validate_decimal(marketplace_cost, "Marketplace cost", allow_zero=True)
    _validate_decimal(commission_rate, "Marketplace commission", allow_zero=True)
    _validate_decimal(usd_exchange_rate, "USD exchange rate", allow_zero=False)
    if not money_quantum.is_finite() or money_quantum <= 0:
        raise DomainValidationError("Money quantum must be greater than zero")
    try:
        stored_cost = marketplace_cost.quantize(money_quantum, rounding=rounding)
        commission = (marketplace_cost * commission_rate).quantize(
            money_quantum,
            rounding=rounding,
        )
        final_usd = (stored_cost + commission).quantize(money_quantum, rounding=rounding)
        final_local = (final_usd * usd_exchange_rate).quantize(
            money_quantum,
            rounding=rounding,
        )
    except (DecimalException, TypeError, ValueError) as error:
        raise DomainValidationError("Money rounding policy is invalid") from error
    return FinancialSnapshot(
        marketplace_cost=stored_cost,
        marketplace_commission=commission,
        final_cost_usd=final_usd,
        final_cost_local_currency=final_local,
        usd_exchange_rate=usd_exchange_rate,
    )


def _validate_decimal(value: Decimal, name: str, *, allow_zero: bool) -> None:
    minimum_is_valid = value >= 0 if allow_zero else value > 0
    if not value.is_finite() or not minimum_is_valid:
        qualifier = "non-negative" if allow_zero else "greater than zero"
        raise DomainValidationError(f"{name} must be finite and {qualifier}")
