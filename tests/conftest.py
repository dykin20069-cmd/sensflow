"""Shared pytest fixtures."""

import pytest


@pytest.fixture
def valid_environment() -> dict[str, str]:
    """Return a complete, valid test environment."""
    return {
        "APP_ENVIRONMENT": "test",
        "PREFERRED_MODE_DEFAULT": "true",
        "LOG_LEVEL": "warning",
        "DATABASE_URL": "postgresql+asyncpg://user:database-secret@localhost:5432/sensflow",
        "TELEGRAM_BOT_TOKEN": "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        "TELEGRAM_OPERATOR_ID": "123456789",
        "TELEGRAM_NOTIFICATIONS_ENABLED": "true",
        "TELEGRAM_NOTIFICATION_CATEGORIES": "purchase_completed,order_cancelled",
        "RBXCRATE_API_KEY": "marketplace-secret",
        "RBXCRATE_BASE_URL": "https://rbxcrate.example",
        "ROBLOX_API_KEY": "roblox-secret",
        "MAX_PURCHASE_RATE": "1.25",
        "PREFERRED_PURCHASE_RATE": "1.10",
        "PREFERRED_TIMEOUT_MINUTES": "35",
        "LOW_BALANCE_THRESHOLD": "10",
        "CRITICAL_BALANCE_THRESHOLD": "5",
        "STOCK_NOTIFICATIONS_ENABLED": "true",
        "MARKETPLACE_COMMISSION_RATE": "0.05",
        "STOCK_MONITORING_INTERVAL_SECONDS": "15",
        "MARKETPLACE_SYNC_INTERVAL_SECONDS": "20",
        "AUTOMATIC_REORDER_ENABLED": "false",
        "AUTOMATIC_REORDER_INTERVAL_SECONDS": "300",
        "USD_EXCHANGE_RATE": "90.50",
    }
