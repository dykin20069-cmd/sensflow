"""Expected failures raised by deterministic business rules."""


class DomainError(Exception):
    """Base class for expected domain failures."""


class DomainValidationError(DomainError):
    """A value violates a business invariant."""


class DomainConflictError(DomainError):
    """An action is not valid for the entity's current state."""
