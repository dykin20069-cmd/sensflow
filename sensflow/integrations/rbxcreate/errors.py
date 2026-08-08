"""Typed failures exposed by the RBXCrate infrastructure adapter."""


class RbxcrateError(Exception):
    """Base class for expected RBXCrate failures."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        path: str | None = None,
        timestamp: str | None = None,
        response_text: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.path = path
        self.timestamp = timestamp
        self.response_text = response_text


class RbxcrateAuthenticationError(RbxcrateError):
    """API key authentication failed."""


class RbxcrateValidationError(RbxcrateError):
    """The request violates the remote API contract."""


class RbxcrateInsufficientStockError(RbxcrateError):
    """RBXCrate cannot currently fill the requested Robux amount."""


class RbxcrateInsufficientFundsError(RbxcrateError):
    """The RBXCrate account balance is insufficient."""


class RbxcrateOrderNotFoundError(RbxcrateError):
    """The requested remote resource was not found."""


class RbxcrateDuplicateOrderError(RbxcrateError):
    """The supplied external order ID already exists."""


class RbxcrateDailyLimitReachedError(RbxcrateError):
    """Roblox rejected the request because of its daily purchase limit."""


class RbxcrateUnsupportedStatusError(RbxcrateError):
    """The requested operation is unsupported for the remote order status."""


class RbxcrateApiError(RbxcrateError):
    """Transport, server, or unexpected response failure."""


def is_out_of_stock_error(error: RbxcrateError) -> bool:
    """Return whether RBXCrate rejected only the instant stock requirement."""
    return (
        error.status_code == 402
        and error.response_text is not None
        and "OUT_OF_STOCK" in error.response_text
    )
