"""Application errors safe to translate at presentation boundaries."""


class ApplicationError(Exception):
    """Base class for expected application-layer failures."""


class InputValidationError(ApplicationError):
    """Input could not be converted into a valid command or query."""

    def __init__(self, issues: tuple[str, ...]) -> None:
        super().__init__("; ".join(issues))
        self.issues = issues


class NotFoundError(ApplicationError):
    """A requested entity does not exist."""

    def __init__(self, entity_name: str) -> None:
        super().__init__(f"{entity_name} was not found")
        self.entity_name = entity_name


class ConflictError(ApplicationError):
    """An operation conflicts with current persisted state."""


class AuthorizationError(ApplicationError):
    """The caller is not the configured operator."""


class FeatureUnavailableError(ApplicationError):
    """A use case is intentionally unavailable in the current milestone."""

    def __init__(self, feature_name: str) -> None:
        super().__init__(f"{feature_name} is not available yet")
        self.feature_name = feature_name


class MarketplaceIntegrationError(ApplicationError):
    """A safe application-level representation of an RBXCrate failure."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type


class MarketplaceRateLimitedError(MarketplaceIntegrationError):
    """RBXCrate asked SensFlow to temporarily stop status polling."""


class RobloxIntegrationError(ApplicationError):
    """A safe application-level representation of an official Roblox API failure."""


class UnknownMarketplaceStatusError(MarketplaceIntegrationError):
    """RBXCrate returned a status that has no approved V1 mapping."""

    def __init__(self, status: str) -> None:
        super().__init__(f"RBXCrate returned an unsupported order status: {status}")
        self.status = status


class MarketplaceCancellationUnsupportedError(MarketplaceIntegrationError):
    """RBXCrate requires status synchronization instead of cancellation."""
