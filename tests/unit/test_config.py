"""Tests for centralized configuration loading."""

from decimal import Decimal
from pathlib import Path

import pytest

from sensflow.domain.enums import NotificationType
from sensflow.infrastructure.config import ConfigurationError, load_settings


@pytest.mark.unit
def test_load_settings_parses_all_groups(valid_environment: dict[str, str]) -> None:
    settings = load_settings(valid_environment)

    assert settings.application.environment == "test"
    assert settings.application.timezone == "Europe/Moscow"
    assert settings.logging.level == "WARNING"
    assert settings.telegram.operator_id == 123456789
    assert settings.telegram.notifications_enabled is True
    assert settings.telegram.notification_categories == (
        NotificationType.PURCHASE_COMPLETED,
        NotificationType.ORDER_CANCELLED,
    )
    assert settings.rbxcrate.base_url == "https://rbxcrate.example"
    assert settings.rbxcrate.api_key.get_secret_value() == "marketplace-secret"
    assert settings.rbxcrate.dry_run is False
    assert settings.marketplace.minimum_purchase_rate == Decimal("0")
    assert settings.marketplace.maximum_purchase_rate == Decimal("1.25")
    assert settings.marketplace.preferred_mode_default is True
    assert settings.marketplace.preferred_purchase_rate == Decimal("1.10")
    assert settings.marketplace.preferred_timeout_minutes == 35
    assert settings.marketplace.low_balance_threshold == Decimal("10")
    assert settings.marketplace.critical_balance_threshold == Decimal("5")
    assert settings.marketplace.stock_notifications_enabled is True
    assert settings.automation.automatic_reorder_enabled is False
    assert settings.automation.auto_requeue_delay_seconds == Decimal("5")
    assert settings.finance.usd_exchange_rate == Decimal("90.50")


@pytest.mark.unit
def test_secret_values_are_masked_in_settings_representation(
    valid_environment: dict[str, str],
) -> None:
    settings = load_settings(valid_environment)
    representation = repr(settings)

    assert "database-secret" not in representation
    assert "telegram-secret" not in representation
    assert "marketplace-secret" not in representation
    assert "roblox-secret" not in representation
    assert "**********" in representation


@pytest.mark.unit
def test_missing_required_configuration_is_reported_without_secret_values(
    valid_environment: dict[str, str],
) -> None:
    valid_environment.pop("TELEGRAM_OPERATOR_ID")
    valid_environment["TELEGRAM_BOT_TOKEN"] = "must-not-leak"

    with pytest.raises(ConfigurationError) as raised:
        load_settings(valid_environment)

    message = str(raised.value)
    assert "telegram.operator_id" in message
    assert "must-not-leak" not in message


@pytest.mark.unit
def test_application_timezone_is_fixed_to_moscow(valid_environment: dict[str, str]) -> None:
    valid_environment["APP_TIMEZONE"] = "Not/A_Timezone"

    settings = load_settings(valid_environment)

    assert settings.application.timezone == "Europe/Moscow"


@pytest.mark.unit
def test_database_url_requires_asyncpg(valid_environment: dict[str, str]) -> None:
    valid_environment["DATABASE_URL"] = "postgresql://user:password@localhost/sensflow"

    with pytest.raises(ConfigurationError, match=r"postgresql\+asyncpg"):
        load_settings(valid_environment)


@pytest.mark.unit
def test_rbxcrate_base_url_must_be_absolute(valid_environment: dict[str, str]) -> None:
    valid_environment["RBXCRATE_BASE_URL"] = "/relative"

    with pytest.raises(ConfigurationError, match=r"rbxcrate\.base_url"):
        load_settings(valid_environment)


@pytest.mark.unit
def test_legacy_rbxcreate_token_remains_a_safe_configuration_alias(
    valid_environment: dict[str, str],
) -> None:
    valid_environment.pop("RBXCRATE_API_KEY")
    valid_environment["RBXCREATE_API_TOKEN"] = "legacy-secret"

    settings = load_settings(valid_environment)

    assert settings.rbxcrate.api_key.get_secret_value() == "legacy-secret"


@pytest.mark.unit
def test_environment_example_contains_valid_application_configuration() -> None:
    environment = {
        key: value
        for line in Path(".env.example").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
        for key, value in [line.split("=", maxsplit=1)]
    }

    settings = load_settings(environment)

    assert settings.application.environment == "development"


def test_dry_run_and_interval_aliases_are_validated(
    valid_environment: dict[str, str],
) -> None:
    valid_environment["RBXCRATE_DRY_RUN"] = "true"
    valid_environment.pop("MARKETPLACE_SYNC_INTERVAL_SECONDS")
    valid_environment["SYNC_INTERVAL_SECONDS"] = "25"
    valid_environment.pop("AUTOMATIC_REORDER_INTERVAL_SECONDS")
    valid_environment["REORDER_CHECK_INTERVAL_SECONDS"] = "35"

    settings = load_settings(valid_environment)

    assert settings.rbxcrate.dry_run is True
    assert settings.marketplace.synchronization_interval_seconds == 25
    assert settings.automation.automatic_reorder_interval_seconds == 35


def test_purchase_rate_bounds_and_positive_intervals_fail_fast(
    valid_environment: dict[str, str],
) -> None:
    valid_environment["MIN_PURCHASE_RATE"] = "2"
    valid_environment["MAX_PURCHASE_RATE"] = "1"

    with pytest.raises(ConfigurationError, match="maximum purchase rate"):
        load_settings(valid_environment)

    valid_environment["MAX_PURCHASE_RATE"] = "2"
    valid_environment["MARKETPLACE_SYNC_INTERVAL_SECONDS"] = "0"
    with pytest.raises(ConfigurationError, match="synchronization_interval_seconds"):
        load_settings(valid_environment)

    valid_environment["MARKETPLACE_SYNC_INTERVAL_SECONDS"] = "1"
    valid_environment["AUTOMATIC_REORDER_INTERVAL_SECONDS"] = "0.2"
    with pytest.raises(ConfigurationError, match="automatic_reorder_interval_seconds"):
        load_settings(valid_environment)

    valid_environment["AUTOMATIC_REORDER_INTERVAL_SECONDS"] = "0.3"
    valid_environment["AUTO_REQUEUE_DELAY_SECONDS"] = "0.2"
    with pytest.raises(ConfigurationError, match="auto_requeue_delay_seconds"):
        load_settings(valid_environment)


def test_v2_rate_and_balance_thresholds_are_validated(
    valid_environment: dict[str, str],
) -> None:
    valid_environment["PREFERRED_PURCHASE_RATE"] = "1.5"
    with pytest.raises(ConfigurationError, match="preferred purchase rate"):
        load_settings(valid_environment)

    valid_environment["PREFERRED_PURCHASE_RATE"] = "1.1"
    valid_environment["CRITICAL_BALANCE_THRESHOLD"] = "11"
    with pytest.raises(ConfigurationError, match="critical balance threshold"):
        load_settings(valid_environment)


@pytest.mark.parametrize(
    ("environment_name", "location"),
    [
        ("TELEGRAM_BOT_TOKEN", "telegram.bot_token"),
        ("TELEGRAM_OPERATOR_ID", "telegram.operator_id"),
        ("DATABASE_URL", "database.url"),
        ("RBXCRATE_API_KEY", "rbxcrate.api_key"),
    ],
)
def test_critical_configuration_names_are_operator_friendly(
    valid_environment: dict[str, str],
    environment_name: str,
    location: str,
) -> None:
    valid_environment.pop(environment_name)

    with pytest.raises(ConfigurationError) as raised:
        load_settings(valid_environment)

    assert environment_name in str(raised.value)
    assert location in str(raised.value)
