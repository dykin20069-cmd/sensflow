"""Stateless Customer identity and history rules."""

from dataclasses import dataclass
from datetime import datetime

from sensflow.domain.errors import DomainConflictError, DomainValidationError
from sensflow.infrastructure.database.models import (
    Customer,
    CustomerPlaceIDHistory,
    CustomerUsernameHistory,
)


@dataclass(frozen=True, slots=True)
class RobloxIdentity:
    """Verified Roblox identity returned by the future Roblox adapter."""

    user_id: int
    username: str

    def __post_init__(self) -> None:
        if self.user_id <= 0:
            raise DomainValidationError("Roblox User ID must be greater than zero")
        object.__setattr__(self, "username", _validated_username(self.username))


def create_customer(identity: RobloxIdentity, place_id: int, now: datetime) -> Customer:
    """Create a Customer from a verified permanent identity."""
    _validate_place_id(place_id)
    return Customer(
        roblox_user_id=identity.user_id,
        current_username=identity.username,
        current_place_id=place_id,
        archived=False,
        last_activity=now,
    )


def create_manual_customer(username: str, place_id: int, now: datetime) -> Customer:
    """Create an unverified Customer without inventing a Roblox User ID."""
    _validate_place_id(place_id)
    return Customer(
        roblox_user_id=None,
        current_username=_validated_username(username),
        current_place_id=place_id,
        archived=False,
        last_activity=now,
    )


def refresh_identity(
    customer: Customer,
    identity: RobloxIdentity,
    now: datetime,
) -> CustomerUsernameHistory | None:
    """Apply a verified username change while preserving the permanent identity."""
    if customer.roblox_user_id is None:
        customer.roblox_user_id = identity.user_id
    elif identity.user_id != customer.roblox_user_id:
        raise DomainConflictError("Verified Roblox identity does not match the Customer")
    customer.last_activity = now
    if identity.username == customer.current_username:
        return None
    history = CustomerUsernameHistory(
        customer_id=customer.id,
        username=customer.current_username,
    )
    customer.current_username = identity.username
    return history


def update_place_id(
    customer: Customer,
    place_id: int,
    now: datetime,
) -> CustomerPlaceIDHistory | None:
    """Replace the current Place ID and preserve the prior value exactly once."""
    _validate_place_id(place_id)
    customer.last_activity = now
    if place_id == customer.current_place_id:
        return None
    history = CustomerPlaceIDHistory(
        customer_id=customer.id,
        place_id=customer.current_place_id,
    )
    customer.current_place_id = place_id
    return history


def archive_customer(customer: Customer, archived: bool, now: datetime) -> bool:
    """Set the archive flag without deleting Customer history."""
    changed = customer.archived != archived
    customer.archived = archived
    customer.last_activity = now
    return changed


def _validate_place_id(place_id: int) -> None:
    if place_id <= 0:
        raise DomainValidationError("Place ID must be greater than zero")


def _validated_username(username: str) -> str:
    normalized = username.strip()
    if not normalized:
        raise DomainValidationError("Roblox username must not be empty")
    if len(normalized) > 64:
        raise DomainValidationError("Roblox username must not exceed 64 characters")
    return normalized
