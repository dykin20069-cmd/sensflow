"""Immutable data transferred from application services to presentation."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from math import ceil
from uuid import UUID

from sensflow.domain.enums import (
    ClientOrderStatus,
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
    MANUAL_REORDER = "manual_reorder"
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
class PlaceIDSelectionDTO:
    """Place ID discovered for a pending Create Order conversation, if any."""

    username: str
    requested_robux: int
    discovered_place_id: int | None


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
    marketplace_rate: Decimal | None = None
    available_actions: tuple[OrderAction, ...] = ()


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
    automatic_reorder_enabled: bool
    automatic_reorder_interval_seconds: int
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
