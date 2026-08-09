"""MarketplaceOrder domain policy tests."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from sensflow.domain.enums import ClientOrderStatus, MarketplaceOrderStatus
from sensflow.domain.errors import DomainConflictError, DomainValidationError
from sensflow.domain.marketplace.service import (
    MarketplaceOrderResult,
    cancel_marketplace_order,
    complete_marketplace_order,
    create_marketplace_order,
    force_close_marketplace_order,
    update_marketplace_progress,
)
from sensflow.infrastructure.database.models import ClientOrder, MarketplaceOrder

NOW = datetime(2026, 8, 7, 8, 0, tzinfo=UTC)


def client_order(status: ClientOrderStatus = ClientOrderStatus.PURCHASING) -> ClientOrder:
    return ClientOrder(
        id=uuid4(),
        customer_id=uuid4(),
        requested_robux=100,
        current_status=status,
        current_place_id=100,
        marketplace_rate_limit=Decimal("1.25"),
    )


def active_attempt() -> MarketplaceOrder:
    return MarketplaceOrder(
        id=uuid4(),
        client_order_id=uuid4(),
        rbxcreate_order_id="rbx-1",
        marketplace_status=MarketplaceOrderStatus.ACTIVE,
        purchase_rate=Decimal("1.00"),
        requested_robux=100,
        purchased_robux=0,
        remaining_robux=100,
    )


def test_active_attempt_requires_purchasing_and_no_existing_active_attempt() -> None:
    result = MarketplaceOrderResult("rbx-1", Decimal("1.00"), 100)
    attempt = create_marketplace_order(client_order(), result, active_order_exists=False)

    assert attempt.marketplace_status is MarketplaceOrderStatus.ACTIVE
    assert attempt.remaining_robux == 100

    with pytest.raises(DomainConflictError):
        create_marketplace_order(client_order(), result, active_order_exists=True)
    with pytest.raises(DomainConflictError):
        create_marketplace_order(
            client_order(ClientOrderStatus.DRAFT), result, active_order_exists=False
        )


def test_marketplace_quantities_are_consistent_and_monotonic() -> None:
    attempt = active_attempt()
    update_marketplace_progress(attempt, purchased_robux=40, remaining_robux=60)

    assert attempt.purchased_robux == 40
    with pytest.raises(DomainConflictError):
        update_marketplace_progress(attempt, purchased_robux=20, remaining_robux=80)
    with pytest.raises(DomainValidationError):
        update_marketplace_progress(attempt, purchased_robux=50, remaining_robux=60)


def test_marketplace_completion_and_cancellation_are_terminal() -> None:
    completed = active_attempt()
    complete_marketplace_order(completed, purchased_robux=100, now=NOW)
    assert completed.marketplace_status is MarketplaceOrderStatus.COMPLETED
    assert completed.remaining_robux == 0

    cancelled = active_attempt()
    cancel_marketplace_order(
        cancelled,
        purchased_robux=25,
        remaining_robux=75,
        now=NOW,
    )
    assert cancelled.marketplace_status is MarketplaceOrderStatus.CANCELLED
    assert cancelled.cancelled_at == NOW


def test_force_close_clears_synchronization_retry_state() -> None:
    attempt = active_attempt()
    attempt.last_status_check_at = NOW
    attempt.status_check_backoff_until = NOW
    attempt.status_check_rate_limit_count = 3

    force_close_marketplace_order(attempt, now=NOW)

    assert attempt.marketplace_status is MarketplaceOrderStatus.FORCE_CLOSED
    assert attempt.cancelled_at == NOW
    assert attempt.last_status_check_at is None
    assert attempt.status_check_backoff_until is None
    assert attempt.status_check_rate_limit_count == 0
