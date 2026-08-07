"""Validated application command models."""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from sensflow.domain.enums import SettingField

Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class Command(BaseModel):
    """Base for immutable command input."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class OperatorCommand(Command):
    """Mutation requested by the configured Telegram operator."""

    operator_id: int = Field(gt=0)


class PrepareCreateOrderCommand(Command):
    """Input collected before Place ID selection."""

    username: Username
    requested_robux: int = Field(gt=0)


class CreateOrderCommand(PrepareCreateOrderCommand):
    """Complete input for the Create Order use case."""

    place_id: int = Field(gt=0)
    operator_id: int = Field(gt=0)


class OrderActionCommand(OperatorCommand):
    """Identify the Client Order targeted by an operator action."""

    order_id: UUID


class SystemActionCommand(OperatorCommand):
    """Authorize an operator-triggered operational action."""


class EditDraftCommand(OrderActionCommand):
    """Editable Draft values; omitted fields keep their current values."""

    requested_robux: int | None = Field(default=None, gt=0)
    place_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def require_change(self) -> "EditDraftCommand":
        if self.requested_robux is None and self.place_id is None:
            raise ValueError("at least one Draft field must be provided")
        return self


class FinalizePurchaseCommand(Command):
    """Validated marketplace completion data and explicit unresolved numeric policy."""

    order_id: UUID
    marketplace_order_id: UUID
    purchased_robux: int = Field(gt=0)
    marketplace_cost: Decimal = Field(ge=0)
    roblox_tax_rate: Decimal = Field(ge=0, lt=1)
    robux_rounding: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    money_rounding: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    money_quantum: Decimal = Field(default=Decimal("0.0001"), gt=0)


class CustomerActionCommand(OperatorCommand):
    """Identify the Customer targeted by an operator action."""

    customer_id: UUID


class UpdatePlaceIDCommand(CustomerActionCommand):
    """Structurally valid manual Place ID input."""

    place_id: int = Field(gt=0)


class ArchiveCustomerCommand(CustomerActionCommand):
    """Requested Customer archive state."""

    archived: bool = True


class UpdateSettingCommand(OperatorCommand):
    """Raw operator setting change awaiting business validation."""

    field: SettingField
    value: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
