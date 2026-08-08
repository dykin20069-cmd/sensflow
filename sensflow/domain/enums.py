"""Shared V1 domain vocabulary used across application boundaries."""

from enum import StrEnum


class SettingField(StrEnum):
    """System Settings fields editable by the Version 1 operator."""

    MAXIMUM_PURCHASE_RATE = "maximum_purchase_rate"
    PREFERRED_PURCHASE_RATE = "preferred_purchase_rate"
    PREFERRED_TIMEOUT_MINUTES = "preferred_timeout_minutes"
    MARKETPLACE_COMMISSION = "marketplace_commission"
    USD_EXCHANGE_RATE = "usd_exchange_rate"
    AUTOMATIC_REORDER_ENABLED = "automatic_reorder_enabled"
    AUTOMATIC_REORDER_INTERVAL_SECONDS = "automatic_reorder_interval_seconds"
    AUTO_REQUEUE_DELAY_SECONDS = "auto_requeue_delay_seconds"
    MARKETPLACE_MONITORING_INTERVAL_SECONDS = "marketplace_monitoring_interval_seconds"
    SYNCHRONIZATION_INTERVAL_SECONDS = "synchronization_interval_seconds"
    TELEGRAM_NOTIFICATIONS_ENABLED = "telegram_notifications_enabled"
    STOCK_NOTIFICATIONS_ENABLED = "stock_notifications_enabled"
    LOW_BALANCE_THRESHOLD = "low_balance_threshold"
    CRITICAL_BALANCE_THRESHOLD = "critical_balance_threshold"
    NOTIFICATION_CATEGORIES = "notification_categories"
    APPLICATION_TIMEZONE = "application_timezone"


class ClientOrderStatus(StrEnum):
    DRAFT = "draft"
    PREORDER = "preorder"
    PURCHASING = "purchasing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MarketplaceOrderStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TimelineEventType(StrEnum):
    ORDER_CREATED = "order_created"
    PAYMENT_CONFIRMED = "payment_confirmed"
    PREORDER_CREATED = "preorder_created"
    PURCHASING_STARTED = "purchasing_started"
    MARKETPLACE_ORDER_CREATED = "marketplace_order_created"
    MARKETPLACE_ORDER_CANCELLED = "marketplace_order_cancelled"
    MARKETPLACE_ORDER_COMPLETED = "marketplace_order_completed"
    AUTOMATIC_REORDER = "automatic_reorder"
    MANUAL_REORDER = "manual_reorder"
    ORDER_COMPLETED = "order_completed"
    ORDER_CANCELLED = "order_cancelled"


class NotificationType(StrEnum):
    STOCK_AVAILABLE = "stock_available"
    LOW_BALANCE = "low_balance"
    CRITICAL_BALANCE = "critical_balance"
    AUTO_REQUEUE_STARTED = "auto_requeue_started"
    AUTO_REQUEUE_COMPLETED = "auto_requeue_completed"
    AUTO_REQUEUE_FAILED = "auto_requeue_failed"
    PURCHASE_COMPLETED = "purchase_completed"
    MARKETPLACE_ERROR = "marketplace_error"
    SYNCHRONIZATION_FAILED = "synchronization_failed"
    APPLICATION_RESTARTED = "application_restarted"
    APPLICATION_RECOVERED = "application_recovered"
    AUTOMATIC_REORDER = "automatic_reorder"
    MANUAL_REORDER = "manual_reorder"
    ORDER_CANCELLED = "order_cancelled"


class NotificationDeliveryStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class StatisticsPeriod(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class SystemLogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
