"""Financial snapshot and System Settings business tests."""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

import pytest

from sensflow.domain.enums import NotificationType, SettingField
from sensflow.domain.errors import DomainValidationError
from sensflow.domain.finance.service import (
    calculate_customer_receives,
    calculate_financial_snapshot,
)
from sensflow.domain.settings.service import SettingsDefaults, create_settings, update_setting


def defaults() -> SettingsDefaults:
    return SettingsDefaults(
        maximum_purchase_rate=Decimal("1.25"),
        automatic_reorder_enabled=True,
        automatic_reorder_interval_seconds=300,
        marketplace_monitoring_interval_seconds=30,
        synchronization_interval_seconds=20,
        marketplace_commission=Decimal("0.05"),
        usd_exchange_rate=Decimal("90"),
        telegram_notifications_enabled=True,
        notification_categories=(NotificationType.PURCHASE_COMPLETED,),
        application_timezone="UTC",
    )


def test_robux_calculation_uses_explicit_tax_and_rounding_policy() -> None:
    assert (
        calculate_customer_receives(
            101,
            tax_rate=Decimal("0.30"),
            rounding=ROUND_DOWN,
        )
        == 70
    )

    with pytest.raises(DomainValidationError):
        calculate_customer_receives(100, tax_rate=Decimal("1"), rounding=ROUND_DOWN)


def test_finance_uses_decimal_and_returns_a_stable_historical_snapshot() -> None:
    snapshot = calculate_financial_snapshot(
        marketplace_cost=Decimal("10.005"),
        commission_rate=Decimal("0.05"),
        usd_exchange_rate=Decimal("90"),
        money_quantum=Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )

    assert snapshot.marketplace_cost == Decimal("10.0050")
    assert snapshot.marketplace_commission == Decimal("0.5003")
    assert snapshot.final_cost_usd == Decimal("10.5053")
    assert snapshot.final_cost_local_currency == Decimal("945.4770")
    assert snapshot.usd_exchange_rate == Decimal("90")


def test_production_finance_rounds_cost_fee_total_and_rubles_to_cents() -> None:
    base_usd = Decimal(571) / Decimal(1000) * Decimal("4.5")

    snapshot = calculate_financial_snapshot(
        marketplace_cost=base_usd,
        commission_rate=Decimal("0.05"),
        usd_exchange_rate=Decimal("87"),
        money_quantum=Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    assert snapshot.marketplace_cost == Decimal("2.57")
    assert snapshot.marketplace_commission == Decimal("0.13")
    assert snapshot.final_cost_usd == Decimal("2.70")
    assert snapshot.final_cost_local_currency == Decimal("234.90")


def test_settings_service_parses_every_value_shape_and_rejects_invalid_values() -> None:
    settings = create_settings(defaults())

    update_setting(settings, SettingField.MAXIMUM_PURCHASE_RATE, "1.50")
    update_setting(settings, SettingField.AUTOMATIC_REORDER_ENABLED, "off")
    update_setting(settings, SettingField.AUTOMATIC_REORDER_INTERVAL_SECONDS, "0.3")
    update_setting(settings, SettingField.AUTO_REQUEUE_DELAY_SECONDS, "5")
    update_setting(settings, SettingField.SYNCHRONIZATION_INTERVAL_SECONDS, "45")
    update_setting(
        settings,
        SettingField.NOTIFICATION_CATEGORIES,
        "purchase_completed, order_cancelled",
    )
    update_setting(settings, SettingField.APPLICATION_TIMEZONE, "Europe/Moscow")

    assert settings.maximum_purchase_rate == Decimal("1.50")
    assert settings.automatic_reorder_enabled is False
    assert settings.automatic_reorder_interval_seconds == Decimal("0.3")
    assert settings.auto_requeue_delay_seconds == Decimal("5")
    assert settings.synchronization_interval_seconds == 45
    assert settings.notification_categories == [
        NotificationType.PURCHASE_COMPLETED,
        NotificationType.ORDER_CANCELLED,
    ]
    assert settings.application_timezone == "Europe/Moscow"

    with pytest.raises(DomainValidationError):
        update_setting(settings, SettingField.USD_EXCHANGE_RATE, "0")
    with pytest.raises(DomainValidationError):
        update_setting(settings, SettingField.AUTOMATIC_REORDER_INTERVAL_SECONDS, "0.2")
    with pytest.raises(DomainValidationError):
        update_setting(settings, SettingField.MARKETPLACE_COMMISSION, "5")
