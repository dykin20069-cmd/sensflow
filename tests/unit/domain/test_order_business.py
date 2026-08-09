"""ClientOrder state, Draft, completion, and timeline tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from sensflow.domain.enums import ClientOrderStatus, TimelineEventType
from sensflow.domain.errors import DomainConflictError
from sensflow.domain.order.service import (
    activate_fallback,
    cancel_order,
    complete_order,
    create_draft,
    edit_draft,
    effective_purchase_rate,
    enter_preorder,
    force_close_order,
)
from sensflow.domain.order.state_machine import ALLOWED_TRANSITIONS, validate_transition
from sensflow.domain.order.timeline import create_timeline_event
from sensflow.infrastructure.database.models import ClientOrder, Customer

NOW = datetime(2026, 8, 7, 8, 0, tzinfo=UTC)


def customer() -> Customer:
    return Customer(
        id=uuid4(),
        roblox_user_id=42,
        current_username="Builderman",
        current_place_id=100,
        archived=False,
        last_activity=NOW,
    )


def order(status: ClientOrderStatus = ClientOrderStatus.DRAFT) -> ClientOrder:
    return ClientOrder(
        id=uuid4(),
        customer_id=uuid4(),
        requested_robux=100,
        current_status=status,
        current_place_id=100,
        marketplace_rate_limit=Decimal("1.25"),
    )


def test_state_machine_covers_every_status_pair() -> None:
    for current in ClientOrderStatus:
        for target in ClientOrderStatus:
            if target in ALLOWED_TRANSITIONS[current]:
                validate_transition(current, target)
            else:
                with pytest.raises(DomainConflictError):
                    validate_transition(current, target)


def test_draft_creation_and_editing_are_limited_to_draft_state() -> None:
    draft = create_draft(customer(), 100, 200, Decimal("1.25"))
    edit_draft(draft, requested_robux=150, place_id=300)

    assert draft.current_status is ClientOrderStatus.DRAFT
    assert draft.requested_robux == 150
    assert draft.current_place_id == 300

    draft.current_status = ClientOrderStatus.PREORDER
    with pytest.raises(DomainConflictError):
        edit_draft(draft, requested_robux=200)


def test_preferred_rate_waits_then_activates_the_hard_limit() -> None:
    draft = create_draft(
        customer(),
        100,
        200,
        Decimal("4.5"),
        Decimal("4.1"),
        35,
    )

    enter_preorder(draft, NOW)

    assert draft.preferred_expires_at == NOW + timedelta(minutes=35)
    assert effective_purchase_rate(draft, NOW + timedelta(minutes=34)) == Decimal("4.1")
    assert activate_fallback(draft, NOW + timedelta(minutes=34)) is False
    assert activate_fallback(draft, NOW + timedelta(minutes=35)) is True
    assert draft.fallback_active is True
    assert effective_purchase_rate(draft, NOW + timedelta(minutes=35)) == Decimal("4.5")


def test_quick_order_disables_preferred_waiting_and_uses_the_hard_limit() -> None:
    draft = create_draft(
        customer(),
        857,
        200,
        Decimal("4.5"),
        preferred_mode_enabled=False,
    )

    enter_preorder(draft, NOW)

    assert draft.preferred_rate is None
    assert draft.preferred_timeout_minutes is None
    assert draft.preferred_expires_at is None
    assert draft.fallback_active is True
    assert effective_purchase_rate(draft, NOW) == Decimal("4.5")


def test_cancellation_is_terminal_and_preserves_the_order() -> None:
    client_order = order(ClientOrderStatus.PREORDER)
    cancel_order(client_order, NOW)

    assert client_order.current_status is ClientOrderStatus.CANCELLED
    assert client_order.cancelled_at == NOW
    with pytest.raises(DomainConflictError):
        cancel_order(client_order, NOW)


@pytest.mark.parametrize(
    "status",
    [ClientOrderStatus.PREORDER, ClientOrderStatus.PURCHASING],
)
def test_force_close_is_terminal_and_disables_local_retries(status: ClientOrderStatus) -> None:
    client_order = order(status)
    client_order.automatic_requeue_enabled = True
    client_order.last_requeue_at = NOW - timedelta(seconds=5)
    client_order.requeue_attempts = 7

    force_close_order(client_order, NOW)

    assert client_order.current_status is ClientOrderStatus.FORCE_CLOSED
    assert client_order.automatic_requeue_enabled is False
    assert client_order.last_requeue_at is None
    assert client_order.requeue_attempts == 0
    assert client_order.cancelled_at == NOW
    with pytest.raises(DomainConflictError):
        cancel_order(client_order, NOW)


def test_completion_sets_every_historical_financial_value_once() -> None:
    client_order = order(ClientOrderStatus.PURCHASING)
    complete_order(
        client_order,
        customer_receives=70,
        marketplace_cost=Decimal("10.0000"),
        marketplace_commission=Decimal("0.5000"),
        final_cost_usd=Decimal("10.5000"),
        final_cost_local_currency=Decimal("945.0000"),
        usd_exchange_rate=Decimal("90"),
        now=NOW,
    )

    assert client_order.current_status is ClientOrderStatus.COMPLETED
    assert client_order.customer_receives == 70
    assert client_order.usd_exchange_rate == Decimal("90")
    assert client_order.completed_at == NOW
    with pytest.raises(DomainConflictError):
        cancel_order(client_order, NOW)


def test_timeline_event_has_explicit_chronological_timestamp() -> None:
    client_order = order()
    event = create_timeline_event(
        client_order,
        TimelineEventType.ORDER_CREATED,
        " Order created. ",
        NOW,
    )

    assert event.client_order_id == client_order.id
    assert event.description == "Order created."
    assert event.created_at == NOW
