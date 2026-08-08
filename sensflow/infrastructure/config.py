"""Centralized environment configuration."""

import os
from collections.abc import Mapping
from decimal import Decimal
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)

from sensflow.domain.enums import NotificationType


class ConfigurationError(RuntimeError):
    """Raised when application configuration is missing or invalid."""


class SettingsModel(BaseModel):
    """Base configuration model with immutable, explicit fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ApplicationSettings(SettingsModel):
    """Process-level application configuration."""

    environment: Literal["development", "test", "production"] = "development"
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("must be a valid IANA timezone") from error
        return value


class LoggingSettings(SettingsModel):
    """Structured logging configuration."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


class DatabaseSettings(SettingsModel):
    """PostgreSQL connection configuration."""

    url: SecretStr

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: SecretStr) -> SecretStr:
        raw_url = value.get_secret_value()
        if not raw_url:
            raise ValueError("must not be empty")
        if not raw_url.startswith("postgresql+asyncpg://"):
            raise ValueError("must use the postgresql+asyncpg driver")
        return value


class TelegramSettings(SettingsModel):
    """Telegram Bot API configuration."""

    bot_token: SecretStr = Field(min_length=1)
    operator_id: int = Field(gt=0)
    notifications_enabled: bool
    notification_categories: tuple[NotificationType, ...] = ()


class MarketplaceSettings(SettingsModel):
    """RBXCreate and marketplace defaults."""

    minimum_purchase_rate: Decimal = Field(default=Decimal("0"), ge=0)
    maximum_purchase_rate: Decimal = Field(gt=0)
    preferred_purchase_rate: Decimal = Field(default=Decimal("4.3"), gt=0)
    preferred_timeout_minutes: int = Field(default=35, gt=0)
    low_balance_threshold: Decimal = Field(default=Decimal("10"), ge=0)
    critical_balance_threshold: Decimal = Field(default=Decimal("5"), ge=0)
    stock_notifications_enabled: bool = True
    commission_rate: Decimal = Field(ge=0)
    stock_monitoring_interval_seconds: int = Field(gt=0)
    synchronization_interval_seconds: int = Field(gt=0)

    @model_validator(mode="before")
    @classmethod
    def default_preferred_rate(cls, values: object) -> object:
        if not isinstance(values, dict) or values.get("preferred_purchase_rate") is not None:
            return values
        maximum = values.get("maximum_purchase_rate")
        try:
            default = min(Decimal(str(maximum)), Decimal("4.3"))
        except Exception:
            return values
        return {**values, "preferred_purchase_rate": default}

    @model_validator(mode="after")
    def validate_rate_range(self) -> "MarketplaceSettings":
        if self.maximum_purchase_rate < self.minimum_purchase_rate:
            raise ValueError("maximum purchase rate must be at least minimum purchase rate")
        if self.preferred_purchase_rate > self.maximum_purchase_rate:
            raise ValueError("preferred purchase rate must not exceed maximum purchase rate")
        if self.critical_balance_threshold > self.low_balance_threshold:
            raise ValueError("critical balance threshold must not exceed low balance threshold")
        return self


class RbxcrateSettings(SettingsModel):
    """RBXCrate HTTP endpoint and authentication configuration."""

    api_key: SecretStr = Field(min_length=1)
    base_url: str = "https://rbxcrate.com"
    dry_run: bool = False

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("must be an absolute HTTP or HTTPS URL")
        if parsed.query or parsed.fragment:
            raise ValueError("must not contain a query or fragment")
        if parsed.path not in {"", "/"}:
            raise ValueError("must not contain a path")
        if parsed.username or parsed.password:
            raise ValueError("must not contain credentials")
        return normalized


class RobloxSettings(SettingsModel):
    """Optional Roblox API credentials."""

    api_key: SecretStr | None = None


class AutomationSettings(SettingsModel):
    """Automation defaults loaded at startup."""

    automatic_reorder_enabled: bool
    automatic_reorder_interval_seconds: Decimal = Field(
        default=Decimal("0.3"),
        ge=Decimal("0.3"),
    )
    auto_requeue_delay_seconds: Decimal = Field(
        default=Decimal("5"),
        ge=Decimal("0.3"),
    )


class FinanceSettings(SettingsModel):
    """Financial defaults loaded at startup."""

    usd_exchange_rate: Decimal = Field(gt=0)


class Settings(SettingsModel):
    """Complete centralized application configuration."""

    application: ApplicationSettings
    logging: LoggingSettings
    database: DatabaseSettings
    telegram: TelegramSettings
    marketplace: MarketplaceSettings
    rbxcrate: RbxcrateSettings
    roblox: RobloxSettings
    automation: AutomationSettings
    finance: FinanceSettings


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Load and validate settings from environment variables."""
    source = os.environ if environ is None else environ

    values = {
        "application": {
            "environment": source.get("APP_ENVIRONMENT", "development"),
            "timezone": source.get("APP_TIMEZONE", "UTC"),
        },
        "logging": {"level": source.get("LOG_LEVEL", "INFO").upper()},
        "database": {"url": source.get("DATABASE_URL")},
        "telegram": {
            "bot_token": source.get("TELEGRAM_BOT_TOKEN"),
            "operator_id": source.get("TELEGRAM_OPERATOR_ID"),
            "notifications_enabled": source.get("TELEGRAM_NOTIFICATIONS_ENABLED"),
            "notification_categories": tuple(
                category.strip()
                for category in source.get("TELEGRAM_NOTIFICATION_CATEGORIES", "").split(",")
                if category.strip()
            ),
        },
        "marketplace": {
            "minimum_purchase_rate": source.get("MIN_PURCHASE_RATE", "0"),
            "maximum_purchase_rate": source.get("MAX_PURCHASE_RATE"),
            "preferred_purchase_rate": source.get("PREFERRED_PURCHASE_RATE"),
            "preferred_timeout_minutes": source.get("PREFERRED_TIMEOUT_MINUTES", "35"),
            "low_balance_threshold": source.get("LOW_BALANCE_THRESHOLD", "10"),
            "critical_balance_threshold": source.get("CRITICAL_BALANCE_THRESHOLD", "5"),
            "stock_notifications_enabled": source.get("STOCK_NOTIFICATIONS_ENABLED", "true"),
            "commission_rate": source.get("MARKETPLACE_COMMISSION_RATE"),
            "stock_monitoring_interval_seconds": source.get("STOCK_MONITORING_INTERVAL_SECONDS"),
            "synchronization_interval_seconds": source.get("MARKETPLACE_SYNC_INTERVAL_SECONDS")
            or source.get("SYNC_INTERVAL_SECONDS"),
        },
        "rbxcrate": {
            "api_key": source.get("RBXCRATE_API_KEY") or source.get("RBXCREATE_API_TOKEN"),
            "base_url": source.get("RBXCRATE_BASE_URL", "https://rbxcrate.com"),
            "dry_run": source.get("RBXCRATE_DRY_RUN", "false"),
        },
        "roblox": {"api_key": source.get("ROBLOX_API_KEY") or None},
        "automation": {
            "automatic_reorder_enabled": source.get("AUTOMATIC_REORDER_ENABLED"),
            "automatic_reorder_interval_seconds": source.get("AUTOMATIC_REORDER_INTERVAL_SECONDS")
            or source.get("REORDER_CHECK_INTERVAL_SECONDS", "0.3"),
            "auto_requeue_delay_seconds": source.get("AUTO_REQUEUE_DELAY_SECONDS", "5"),
        },
        "finance": {"usd_exchange_rate": source.get("USD_EXCHANGE_RATE")},
    }

    try:
        return Settings.model_validate(values)
    except ValidationError as error:
        details = []
        for issue in error.errors(include_input=False, include_url=False):
            location = ".".join(str(part) for part in issue["loc"])
            environment_name = _CRITICAL_ENVIRONMENT_NAMES.get(location)
            label = location if environment_name is None else f"{location} ({environment_name})"
            details.append(f"{label}: {issue['msg']}")
        raise ConfigurationError("; ".join(details)) from None


_CRITICAL_ENVIRONMENT_NAMES = {
    "database.url": "DATABASE_URL",
    "telegram.bot_token": "TELEGRAM_BOT_TOKEN",
    "telegram.operator_id": "TELEGRAM_OPERATOR_ID",
    "rbxcrate.api_key": "RBXCRATE_API_KEY",
}
