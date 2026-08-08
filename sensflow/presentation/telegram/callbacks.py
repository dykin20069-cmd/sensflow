"""Compact typed callback payloads for Telegram inline keyboards."""

from enum import StrEnum
from uuid import UUID

from aiogram.filters.callback_data import CallbackData

from sensflow.application.commands import SettingField
from sensflow.domain.enums import ClientOrderStatus, NotificationType, StatisticsPeriod


class MainSection(StrEnum):
    DASHBOARD = "dashboard"
    CREATE_ORDER = "create"
    ACTIVE_ORDERS = "active"
    PREORDERS = "preorders"
    CURRENT_STOCK = "stock"
    ORDERS = "orders"
    CUSTOMERS = "customers"
    STATISTICS = "statistics"
    SETTINGS = "settings"
    SYSTEM_STATUS = "status"


class NavigationAction(StrEnum):
    NOOP = "noop"
    HOME = "home"
    BACK = "back"
    REFRESH = "refresh"
    CLOSE = "close"


class NavigationTarget(StrEnum):
    MAIN = "main"
    CREATE_ORDER = "create"
    ORDER_EDIT = "order_edit"
    CUSTOMER_DETAILS = "customer_details"
    ORDERS = "orders"
    CUSTOMERS = "customers"
    STATISTICS = "statistics"
    SETTINGS = "settings"
    SYSTEM_STATUS = "status"
    CURRENT_STOCK = "stock"


class OrderCallbackAction(StrEnum):
    LIST = "list"
    SEARCH = "search"
    DETAILS = "details"
    CONFIRM_PAYMENT = "pay"
    EDIT_DRAFT = "edit"
    DELETE_DRAFT = "delete"
    START_PURCHASE = "start"
    MANUAL_REORDER = "reorder"
    TOGGLE_AUTO_REQUEUE = "auto_requeue"
    CANCEL = "cancel"
    REFRESH = "refresh"
    REPEAT = "repeat"
    TIMELINE = "timeline"
    REUSE_SIMILAR = "reuse"
    CREATE_DUPLICATE = "duplicate"
    ABORT_CREATE = "abort_create"


class PlaceCallbackAction(StrEnum):
    SELECT = "select"
    USE_REMEMBERED = "remembered"
    CHOOSE_PUBLIC = "public"
    ENTER_MANUALLY = "manual"
    REFRESH = "refresh"
    SEND_PREORDER = "preorder"
    RETRY_STOCK = "retry_stock"


class PurchaseMode(StrEnum):
    QUICK = "quick"
    PREFERRED = "preferred"


class NotificationCategoryGroup(StrEnum):
    PURCHASES = "purchases"
    STOCK_ALERTS = "stock"
    LOW_BALANCE = "low_balance"
    CRITICAL_BALANCE = "critical_balance"
    ERRORS = "errors"
    ORDER_STATUS = "order_status"


NOTIFICATION_CATEGORY_TYPES: dict[NotificationCategoryGroup, frozenset[NotificationType]] = {
    NotificationCategoryGroup.PURCHASES: frozenset({NotificationType.PURCHASE_COMPLETED}),
    NotificationCategoryGroup.STOCK_ALERTS: frozenset({NotificationType.STOCK_AVAILABLE}),
    NotificationCategoryGroup.LOW_BALANCE: frozenset({NotificationType.LOW_BALANCE}),
    NotificationCategoryGroup.CRITICAL_BALANCE: frozenset({NotificationType.CRITICAL_BALANCE}),
    NotificationCategoryGroup.ERRORS: frozenset(
        {
            NotificationType.AUTO_REQUEUE_FAILED,
            NotificationType.MARKETPLACE_ERROR,
            NotificationType.SYNCHRONIZATION_FAILED,
        }
    ),
    NotificationCategoryGroup.ORDER_STATUS: frozenset(
        {
            NotificationType.AUTO_REQUEUE_STARTED,
            NotificationType.AUTO_REQUEUE_COMPLETED,
            NotificationType.APPLICATION_RESTARTED,
            NotificationType.APPLICATION_RECOVERED,
            NotificationType.AUTOMATIC_REORDER,
            NotificationType.MANUAL_REORDER,
            NotificationType.ORDER_CANCELLED,
        }
    ),
}


class CustomerCallbackAction(StrEnum):
    DETAILS = "details"
    REFRESH = "refresh"
    UPDATE_PLACE_ID = "place"
    ARCHIVE = "archive"


class SettingsCallbackAction(StrEnum):
    EDIT = "edit"
    TOGGLE = "toggle"


class SystemCallbackAction(StrEnum):
    RUN_RECOVERY = "recover"
    RUN_SYNC = "sync"


class PageScope(StrEnum):
    ORDERS = "orders"
    CUSTOMERS = "customers"


class MenuCallback(CallbackData, prefix="m"):
    section: MainSection


class NavigationCallback(CallbackData, prefix="n"):
    action: NavigationAction
    target: NavigationTarget = NavigationTarget.MAIN


class OrderCallback(CallbackData, prefix="o"):
    action: OrderCallbackAction
    order_id: UUID | None = None
    status: ClientOrderStatus | None = None


class PlaceCallback(CallbackData, prefix="pl"):
    action: PlaceCallbackAction
    index: int = -1


class PurchaseModeCallback(CallbackData, prefix="pm"):
    mode: PurchaseMode


class CustomerCallback(CallbackData, prefix="c"):
    action: CustomerCallbackAction
    customer_id: UUID


class SettingsCallback(CallbackData, prefix="s"):
    action: SettingsCallbackAction
    field: SettingField


class NotificationCategoryCallback(CallbackData, prefix="nc"):
    category: NotificationCategoryGroup


class StatisticsCallback(CallbackData, prefix="st"):
    period: StatisticsPeriod


class SystemCallback(CallbackData, prefix="sys"):
    action: SystemCallbackAction


class PageCallback(CallbackData, prefix="p"):
    scope: PageScope
    page: int
    key: str = ""
