"""Immutable data transferred from application services to presentation."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from math import ceil
from uuid import UUID

from sensflow.domain.enums import (
    ClientOrderStatus,
    MarketplaceOrderStatus,
    NotificationType,
    StatisticsPeriod,
    TimelineEventType,
)


class OrderAction(StrEnum):
    """Business actions currently valid for one order."""

    CONFIRM_PAYMENT = "confirm_payment"
    EDIT_DRAFT = "edit_draft"
    DELETE_DRAFT = "delete_draft"
    START_PURCHASE = "start_purchase"
    FORCE_PURCHASE = "force_purchase"
    MANUAL_REORDER = "manual_reorder"
    ENABLE_AUTO_REQUEUE = "enable_auto_requeue"
    DISABLE_AUTO_REQUEUE = "disable_auto_requeue"
    CANCEL = "cancel"
    REFRESH = "refresh"
    TIMELINE = "timeline"


class CustomerAction(StrEnum):
    """Business actions currently valid for one Customer."""

    REFRESH = "refresh"
    UPDATE_PLACE_ID = "update_place_id"
    ARCHIVE = "archive"


@dataclass(frozen=True, slots=True)
class PageDTO[ItemT]:
    """One page of application output."""

    items: tuple[ItemT, ...]
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, ceil(self.total_items / self.page_size))


@dataclass(frozen=True, slots=True)
class ActionResultDTO:
    """Safe operator-facing result of a future mutating use case."""

    message: str
    order_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class StockAvailabilityDTO:
    """Whether one requested amount fits the current persisted stock policy."""

    available: bool
    maximum_purchase_rate: Decimal


@dataclass(frozen=True, slots=True)
class RememberedPlaceDTO:
    """The most recently selected place for a normalized Roblox username."""

    place_id: int
    place_name: str


@dataclass(frozen=True, slots=True)
class PublicPlaceDTO:
    """One official public Roblox place offered to the operator."""

    place_id: int
    universe_id: int
    place_name: str
    visits: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PlaceIDSelectionDTO:
    """Remembered and official public places for a pending Create Order."""

    username: str
    requested_robux: int
    roblox_user_id: int | None = None
    remembered_place: RememberedPlaceDTO | None = None
    public_places: tuple[PublicPlaceDTO, ...] = ()


@dataclass(frozen=True, slots=True)
class TimelineEventDTO:
    """Client Order timeline entry."""

    event_type: TimelineEventType
    description: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class OrderSummaryDTO:
    """Compact Client Order list item."""

    id: UUID
    customer_username: str
    status: ClientOrderStatus
    requested_robux: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class OrderStatusCountsDTO:
    """Counts used by the status-grouped Orders menu."""

    counts: dict[ClientOrderStatus, int]


@dataclass(frozen=True, slots=True)
class OrderDetailDTO:
    """All documented fields for the Client Order details screen."""

    id: UUID
    customer_username: str
    status: ClientOrderStatus
    requested_robux: int
    customer_receives: int | None
    current_place_id: int
    marketplace_rate_limit: Decimal
    marketplace_cost: Decimal | None
    marketplace_commission: Decimal | None
    final_cost_usd: Decimal | None
    final_cost_local_currency: Decimal | None
    created_at: datetime
    completed_at: datetime | None
    timeline: tuple[TimelineEventDTO, ...]
    preferred_rate: Decimal | None = None
    preferred_timeout_minutes: int | None = None
    preferred_expires_at: datetime | None = None
    fallback_active: bool = False
    executed_rate: Decimal | None = None
    marketplace_rate: Decimal | None = None
    marketplace_status: MarketplaceOrderStatus | None = None
    marketplace_order_reference: str | None = None
    waiting_seconds: int | None = None
    next_automatic_retry_seconds: Decimal | None = None
    remembered_place: bool = False
    automatic_requeue_enabled: bool = True
    requeue_attempts: int = 0
    last_requeue_at: datetime | None = None
    available_actions: tuple[OrderAction, ...] = ()


@dataclass(frozen=True, slots=True)
class MarketplaceStockDTO:
    """One RBXCrate rate tier safe for operator presentation."""

    rate: Decimal
    accounts_count: int
    max_instant_order: int
    total_robux_amount: int


@dataclass(frozen=True, slots=True)
class CurrentStockDTO:
    """Current typed stock snapshot and the rate policy applied to it."""

    items: tuple[MarketplaceStockDTO, ...]
    maximum_purchase_rate: Decimal
    preferred_rate: Decimal
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class UsernameHistoryDTO:
    """Historical Customer username."""

    username: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PlaceIDHistoryDTO:
    """Historical Customer Place ID."""

    place_id: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CustomerSummaryDTO:
    """Compact Customer search item."""

    id: UUID
    username: str
    roblox_user_id: int | None
    current_place_id: int
    archived: bool


@dataclass(frozen=True, slots=True)
class CustomerDetailDTO(CustomerSummaryDTO):
    """All documented fields for the Customer details screen."""

    notes: str | None
    username_history: tuple[UsernameHistoryDTO, ...]
    place_id_history: tuple[PlaceIDHistoryDTO, ...]
    orders: tuple[OrderSummaryDTO, ...]
    available_actions: tuple[CustomerAction, ...] = ()


@dataclass(frozen=True, slots=True)
class StatisticsDTO:
    """One persisted daily, weekly, or monthly Statistics projection."""

    period: StatisticsPeriod
    period_start: date
    total_orders: int
    draft_orders: int
    preorder_orders: int
    purchasing_orders: int
    completed_orders: int
    cancelled_orders: int
    total_purchased_robux: int
    total_amount_paid: Decimal
    average_marketplace_rate: Decimal
    average_purchase_cost: Decimal
    total_marketplace_commission: Decimal


@dataclass(frozen=True, slots=True)
class SettingsDTO:
    """Persisted operator-editable System Settings."""

    maximum_purchase_rate: Decimal
    preferred_purchase_rate: Decimal
    preferred_timeout_minutes: int
    low_balance_threshold: Decimal
    critical_balance_threshold: Decimal
    stock_notifications_enabled: bool
    automatic_reorder_enabled: bool
    automatic_reorder_interval_seconds: Decimal
    auto_requeue_delay_seconds: Decimal
    marketplace_monitoring_interval_seconds: int
    synchronization_interval_seconds: int
    marketplace_commission: Decimal
    usd_exchange_rate: Decimal
    telegram_notifications_enabled: bool
    notification_categories: tuple[NotificationType, ...]
    application_timezone: str


@dataclass(frozen=True, slots=True)
class SystemStatusDTO:
    """Non-sensitive runtime availability for the System Status screen."""

    application_available: bool
    database_available: bool
    telegram_available: bool
    marketplace_available: bool | None
    automation_available: bool | None
    rbxcrate_balance: Decimal | None = None
    active_marketplace_orders: int | None = None
    pending_preorders: int | None = None
