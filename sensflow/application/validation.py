"""Conversion of untrusted presentation input into application models."""

from pydantic import BaseModel, TypeAdapter, ValidationError

from sensflow.application.commands import Username
from sensflow.application.errors import InputValidationError

_username_adapter = TypeAdapter(Username)
_positive_integer_adapter = TypeAdapter(int)


def validate_input[InputT: BaseModel](model: type[InputT], values: dict[str, object]) -> InputT:
    """Validate untrusted values and expose only safe field-level messages."""
    try:
        return model.model_validate(values)
    except ValidationError as error:
        issues = tuple(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors(include_input=False, include_url=False)
        )
        raise InputValidationError(issues) from None


def validate_username(value: object) -> str:
    """Validate and normalize a Roblox username input shape."""
    try:
        return _username_adapter.validate_python(value)
    except ValidationError as error:
        issue = error.errors(include_input=False, include_url=False)[0]["msg"]
        raise InputValidationError((f"username: {issue}",)) from None


def validate_positive_integer(value: object, field_name: str) -> int:
    """Parse a positive integer without adding domain-specific policy."""
    try:
        parsed = _positive_integer_adapter.validate_python(value)
    except ValidationError as error:
        issue = error.errors(include_input=False, include_url=False)[0]["msg"]
        raise InputValidationError((f"{field_name}: {issue}",)) from None
    if parsed <= 0:
        raise InputValidationError((f"{field_name}: must be greater than 0",))
    return parsed
