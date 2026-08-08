"""System Settings defaults and field validation."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sensflow.domain.enums import NotificationType, SettingField
from sensflow.domain.errors import DomainValidationError
from sensflow.infrastructure.database.models import SystemSettings


@dataclass(frozen=True, slots=True)
class SettingsDefaults:
    """Non-secret defaults used to initialize the singleton settings row."""

    maximum_purchase_rate: Decimal
    automatic_reorder_enabled: bool
    automatic_reorder_interval_seconds: Decimal
    marketplace_monitoring_interval_seconds: int
    synchronization_interval_seconds: int
    marketplace_commission: Decimal
    usd_exchange_rate: Decimal
    telegram_notifications_enabled: bool
    notification_categories: tuple[NotificationType, ...]
    application_timezone: str
    auto_requeue_delay_seconds: Decimal = Decimal("5")
    preferred_purchase_rate: Decimal | None = None
    preferred_timeout_minutes: int = 35
    low_balance_threshold: Decimal = Decimal("10")
    critical_balance_threshold: Decimal = Decimal("5")
    stock_notifications_enabled: bool = True
    preferred_mode_default: bool = True


def create_settings(defaults: SettingsDefaults) -> SystemSettings:
    """Create the one persistent settings row from validated process defaults."""
    settings = SystemSettings(
        maximum_purchase_rate=defaults.maximum_purchase_rate,
        preferred_mode_default=defaults.preferred_mode_default,
        preferred_purchase_rate=(
            min(defaults.maximum_purchase_rate, Decimal("4.3"))
            if defaults.preferred_purchase_rate is None
            else defaults.preferred_purchase_rate
        ),
        preferred_timeout_minutes=defaults.preferred_timeout_minutes,
        low_balance_threshold=defaults.low_balance_threshold,
        critical_balance_threshold=defaults.critical_balance_threshold,
        stock_notifications_enabled=defaults.stock_notifications_enabled,
        automatic_reorder_enabled=defaults.automatic_reorder_enabled,
        automatic_reorder_interval_seconds=defaults.automatic_reorder_interval_seconds,
        auto_requeue_delay_seconds=defaults.auto_requeue_delay_seconds,
        marketplace_monitoring_interval_seconds=defaults.marketplace_monitoring_interval_seconds,
        synchronization_interval_seconds=defaults.synchronization_interval_seconds,
        marketplace_commission=defaults.marketplace_commission,
        usd_exchange_rate=defaults.usd_exchange_rate,
        telegram_notifications_enabled=defaults.telegram_notifications_enabled,
        notification_categories=list(defaults.notification_categories),
        application_timezone=defaults.application_timezone,
    )
    validate_settings(settings)
    return settings


def update_setting(settings: SystemSettings, field: SettingField, raw_value: str) -> object:
    """Parse, validate, and apply one operator-editable setting."""
    value = _parse_setting(field, raw_value)
    setattr(settings, field.value, value)
    validate_settings(settings)
    return value


def validate_settings(settings: SystemSettings) -> None:
    """Enforce all field-level SystemSettings invariants before persistence."""
    _positive_decimal(settings.maximum_purchase_rate, "Maximum purchase rate")
    _positive_decimal(settings.preferred_purchase_rate, "Preferred purchase rate")
    if settings.preferred_purchase_rate > settings.maximum_purchase_rate:
        raise DomainValidationError("Preferred purchase rate must not exceed maximum purchase rate")
    if settings.preferred_timeout_minutes <= 0:
        raise DomainValidationError("Preferred timeout must be greater than zero")
    _nonnegative_decimal(settings.low_balance_threshold, "Low balance threshold")
    _nonnegative_decimal(settings.critical_balance_threshold, "Critical balance threshold")
    if settings.critical_balance_threshold > settings.low_balance_threshold:
        raise DomainValidationError(
            "Critical balance threshold must not exceed low balance threshold"
        )
    _rate_decimal(settings.marketplace_commission, "Marketplace commission")
    _positive_decimal(settings.usd_exchange_rate, "USD exchange rate")
    if settings.automatic_reorder_interval_seconds < Decimal("0.3"):
        raise DomainValidationError("Automatic reorder interval must be at least 0.3 seconds")
    if settings.auto_requeue_delay_seconds < Decimal("0.3"):
        raise DomainValidationError("Auto requeue delay must be at least 0.3 seconds")
    for value, name in (
        (settings.marketplace_monitoring_interval_seconds, "Marketplace monitoring interval"),
        (settings.synchronization_interval_seconds, "Synchronization interval"),
    ):
        if value <= 0:
            raise DomainValidationError(f"{name} must be greater than zero")
    _timezone(settings.application_timezone)


def _parse_setting(field: SettingField, raw_value: str) -> object:
    value = raw_value.strip()
    if field in {
        SettingField.AUTOMATIC_REORDER_INTERVAL_SECONDS,
        SettingField.AUTO_REQUEUE_DELAY_SECONDS,
        SettingField.MAXIMUM_PURCHASE_RATE,
        SettingField.PREFERRED_PURCHASE_RATE,
        SettingField.LOW_BALANCE_THRESHOLD,
        SettingField.CRITICAL_BALANCE_THRESHOLD,
        SettingField.MARKETPLACE_COMMISSION,
        SettingField.USD_EXCHANGE_RATE,
    }:
        try:
            return Decimal(value)
        except InvalidOperation as error:
            raise DomainValidationError(f"{field.value} must be a decimal number") from error
    if field in {
        SettingField.MARKETPLACE_MONITORING_INTERVAL_SECONDS,
        SettingField.SYNCHRONIZATION_INTERVAL_SECONDS,
        SettingField.PREFERRED_TIMEOUT_MINUTES,
    }:
        try:
            return int(value)
        except ValueError as error:
            raise DomainValidationError(f"{field.value} must be a whole number") from error
    if field in {
        SettingField.AUTOMATIC_REORDER_ENABLED,
        SettingField.TELEGRAM_NOTIFICATIONS_ENABLED,
        SettingField.STOCK_NOTIFICATIONS_ENABLED,
        SettingField.PREFERRED_MODE_DEFAULT,
    }:
        normalized = value.casefold()
        if normalized in {"true", "yes", "1", "on"}:
            return True
        if normalized in {"false", "no", "0", "off"}:
            return False
        raise DomainValidationError(f"{field.value} must be true or false")
    if field is SettingField.NOTIFICATION_CATEGORIES:
        if value.casefold() in {"none", "off"}:
            return []
        try:
            return [
                NotificationType(item.strip().casefold())
                for item in value.split(",")
                if item.strip()
            ]
        except ValueError as error:
            raise DomainValidationError(
                "Notification categories contain an unknown value"
            ) from error
    raise DomainValidationError("Setting field is not supported")


def _positive_decimal(value: Decimal, name: str) -> None:
    if not value.is_finite() or value <= 0:
        raise DomainValidationError(f"{name} must be finite and greater than zero")


def _rate_decimal(value: Decimal, name: str) -> None:
    if not value.is_finite() or not Decimal("0") <= value <= Decimal("1"):
        raise DomainValidationError(f"{name} must be a decimal rate between 0 and 1")


def _nonnegative_decimal(value: Decimal, name: str) -> None:
    if not value.is_finite() or value < 0:
        raise DomainValidationError(f"{name} must be finite and nonnegative")


def _timezone(value: str) -> None:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise DomainValidationError("Application timezone must be a valid IANA timezone") from error
