"""Customer identity, history, and archive business tests."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from sensflow.domain.customer.service import (
    RobloxIdentity,
    archive_customer,
    create_customer,
    create_manual_customer,
    refresh_identity,
    update_place_id,
)
from sensflow.domain.errors import DomainConflictError
from sensflow.infrastructure.database.models import Customer

NOW = datetime(2026, 8, 7, 8, 0, tzinfo=UTC)


def stored_customer() -> Customer:
    return Customer(
        id=uuid4(),
        roblox_user_id=42,
        current_username="OldName",
        current_place_id=100,
        archived=False,
        last_activity=NOW,
    )


def test_customer_is_created_only_from_verified_identity() -> None:
    customer = create_customer(RobloxIdentity(42, " Builderman "), 100, NOW)

    assert customer.roblox_user_id == 42
    assert customer.current_username == "Builderman"
    assert customer.current_place_id == 100
    assert customer.last_activity == NOW


def test_manual_customer_is_created_without_a_fake_roblox_identity() -> None:
    customer = create_manual_customer(" ManualCustomer ", 100, NOW)

    assert customer.roblox_user_id is None
    assert customer.current_username == "ManualCustomer"
    assert customer.current_place_id == 100


def test_first_verified_refresh_links_a_manual_customer_identity() -> None:
    customer = create_manual_customer("ManualCustomer", 100, NOW)

    history = refresh_identity(customer, RobloxIdentity(42, "VerifiedCustomer"), NOW)

    assert customer.roblox_user_id == 42
    assert customer.current_username == "VerifiedCustomer"
    assert history is not None
    assert history.username == "ManualCustomer"


def test_username_refresh_preserves_the_previous_name_exactly_once() -> None:
    customer = stored_customer()

    history = refresh_identity(customer, RobloxIdentity(42, "NewName"), NOW)
    unchanged = refresh_identity(customer, RobloxIdentity(42, "NewName"), NOW)

    assert history is not None
    assert history.username == "OldName"
    assert history.customer_id == customer.id
    assert customer.current_username == "NewName"
    assert unchanged is None


def test_username_refresh_rejects_a_different_permanent_identity() -> None:
    customer = stored_customer()

    with pytest.raises(DomainConflictError):
        refresh_identity(customer, RobloxIdentity(7, "Other"), NOW)

    assert customer.current_username == "OldName"


def test_place_update_and_archive_preserve_customer_history() -> None:
    customer = stored_customer()

    history = update_place_id(customer, 200, NOW)
    duplicate = update_place_id(customer, 200, NOW)
    changed = archive_customer(customer, True, NOW)
    unchanged = archive_customer(customer, True, NOW)

    assert history is not None
    assert history.place_id == 100
    assert duplicate is None
    assert customer.current_place_id == 200
    assert customer.archived is True
    assert changed is True
    assert unchanged is False
