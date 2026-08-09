"""Stateless MarketplaceOrder lifecycle and quantity rules."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sensflow.domain.enums import ClientOrderStatus, MarketplaceOrderStatus
from sensflow.domain.errors import DomainConflictError, DomainValidationError
from sensflow.infrastructure.database.models import ClientOrder, MarketplaceOrder


@dataclass(frozen=True, slots=True)
class MarketplaceOrderResult:
    """Validated data returned after a future RBXCreate create call."""

    external_order_id: str
    purchase_rate: Decimal
    requested_robux: int


def create_marketplace_order(
    client_order: ClientOrder,
    result: MarketplaceOrderResult,
    *,
    active_order_exists: bool,
) -> MarketplaceOrder:
    """Create one active attempt for a Purchasing Client Order."""
    if client_order.current_status is not ClientOrderStatus.PURCHASING:
        raise DomainConflictError("Marketplace Orders require a Purchasing Client Order")
    if active_order_exists:
        raise DomainConflictError("The Client Order already has an active Marketplace Order")
    external_id = result.external_order_id.strip()
    if not external_id:
        raise DomainValidationError("Marketplace Order ID must not be empty")
    if len(external_id) > 128:
        raise DomainValidationError("Marketplace Order ID must not exceed 128 characters")
    if not result.purchase_rate.is_finite() or result.purchase_rate <= 0:
        raise DomainValidationError("Marketplace purchase rate must be greater than zero")
    if result.purchase_rate > client_order.marketplace_rate_limit:
        raise DomainConflictError("Marketplace purchase rate exceeds the Client Order limit")
    if result.requested_robux != client_order.requested_robux:
        raise DomainConflictError("Marketplace quantity does not match the Client Order")
    return MarketplaceOrder(
        client_order_id=client_order.id,
        rbxcreate_order_id=external_id,
        marketplace_status=MarketplaceOrderStatus.ACTIVE,
        purchase_rate=result.purchase_rate,
        requested_robux=result.requested_robux,
        purchased_robux=0,
        remaining_robux=result.requested_robux,
    )


def update_marketplace_progress(
    order: MarketplaceOrder,
    *,
    purchased_robux: int,
    remaining_robux: int,
) -> None:
    """Apply monotonic, internally consistent quantities to an active attempt."""
    if order.marketplace_status is not MarketplaceOrderStatus.ACTIVE:
        raise DomainConflictError("Only an active Marketplace Order can be updated")
    if purchased_robux < order.purchased_robux:
        raise DomainConflictError("Purchased Robux cannot decrease")
    if purchased_robux < 0 or remaining_robux < 0:
        raise DomainValidationError("Marketplace quantities must not be negative")
    if purchased_robux + remaining_robux != order.requested_robux:
        raise DomainValidationError("Marketplace quantities must equal Requested Robux")
    order.purchased_robux = purchased_robux
    order.remaining_robux = remaining_robux


def complete_marketplace_order(
    order: MarketplaceOrder,
    *,
    purchased_robux: int,
    now: datetime,
) -> None:
    """Finalize an active attempt after marketplace success confirmation."""
    update_marketplace_progress(order, purchased_robux=purchased_robux, remaining_robux=0)
    if purchased_robux != order.requested_robux:
        raise DomainConflictError("A completed Marketplace Order must be fully purchased")
    order.marketplace_status = MarketplaceOrderStatus.COMPLETED
    order.completed_at = now


def cancel_marketplace_order(
    order: MarketplaceOrder,
    *,
    purchased_robux: int,
    remaining_robux: int,
    now: datetime,
) -> None:
    """Finalize an active attempt after marketplace cancellation confirmation."""
    update_marketplace_progress(
        order,
        purchased_robux=purchased_robux,
        remaining_robux=remaining_robux,
    )
    order.marketplace_status = MarketplaceOrderStatus.CANCELLED
    order.cancelled_at = now


def force_close_marketplace_order(order: MarketplaceOrder, *, now: datetime) -> None:
    """Close one active attempt locally without contacting the marketplace."""
    if order.marketplace_status is not MarketplaceOrderStatus.ACTIVE:
        raise DomainConflictError("Only an active Marketplace Order can be force closed")
    order.marketplace_status = MarketplaceOrderStatus.FORCE_CLOSED
    order.completed_at = None
    order.cancelled_at = now
    order.last_status_check_at = None
    order.status_check_backoff_until = None
    order.status_check_rate_limit_count = 0
