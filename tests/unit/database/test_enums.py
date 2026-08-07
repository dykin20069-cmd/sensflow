"""Tests for persisted enum contracts."""

import pytest

from sensflow.infrastructure.database.enums import (
    ClientOrderStatus,
    MarketplaceOrderStatus,
    NotificationDeliveryStatus,
    NotificationType,
    StatisticsPeriod,
    SystemLogLevel,
    TimelineEventType,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("enum_class", "expected_values"),
    [
        (
            ClientOrderStatus,
            ["draft", "preorder", "purchasing", "completed", "cancelled"],
        ),
        (MarketplaceOrderStatus, ["active", "completed", "cancelled"]),
        (
            TimelineEventType,
            [
                "order_created",
                "payment_confirmed",
                "preorder_created",
                "purchasing_started",
                "marketplace_order_created",
                "marketplace_order_cancelled",
                "marketplace_order_completed",
                "automatic_reorder",
                "manual_reorder",
                "order_completed",
                "order_cancelled",
            ],
        ),
        (
            NotificationType,
            [
                "purchase_completed",
                "marketplace_error",
                "synchronization_failed",
                "application_restarted",
                "application_recovered",
                "automatic_reorder",
                "manual_reorder",
                "order_cancelled",
            ],
        ),
        (NotificationDeliveryStatus, ["pending", "delivered", "failed"]),
        (StatisticsPeriod, ["daily", "weekly", "monthly"]),
        (SystemLogLevel, ["debug", "info", "warning", "error", "critical"]),
    ],
)
def test_persisted_enum_values(enum_class: type, expected_values: list[str]) -> None:
    assert [member.value for member in enum_class] == expected_values
