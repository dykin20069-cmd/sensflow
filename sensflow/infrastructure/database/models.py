"""SQLAlchemy ORM models for the SensFlow V1 database."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sensflow.domain.enums import (
    ClientOrderStatus,
    MarketplaceOrderStatus,
    NotificationDeliveryStatus,
    NotificationType,
    StatisticsPeriod,
    SystemLogLevel,
    TimelineEventType,
)
from sensflow.infrastructure.database.base import (
    Base,
    CreatedAtMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

RATE_PRECISION = 20
RATE_SCALE = 8
MONEY_PRECISION = 20
MONEY_SCALE = 4


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


def _database_enum(enum_class: type[StrEnum], name: str) -> Enum[Any]:
    return Enum(
        enum_class,
        name=name,
        values_callable=_enum_values,
        validate_strings=True,
    )


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Persistent Roblox customer identity and current information."""

    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("roblox_user_id", name="uq_customers_roblox_user_id"),
        CheckConstraint("roblox_user_id > 0", name="roblox_user_id_positive"),
        CheckConstraint("length(btrim(current_username)) > 0", name="current_username_not_empty"),
        CheckConstraint("current_place_id > 0", name="current_place_id_positive"),
        Index("ix_customers_current_username", "current_username"),
    )

    roblox_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    current_username: Mapped[str] = mapped_column(String(64), nullable=False)
    current_place_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    last_activity: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    username_history: Mapped[list[CustomerUsernameHistory]] = relationship(
        back_populates="customer",
        order_by="CustomerUsernameHistory.created_at",
        passive_deletes=True,
    )
    place_id_history: Mapped[list[CustomerPlaceIDHistory]] = relationship(
        back_populates="customer",
        order_by="CustomerPlaceIDHistory.created_at",
        passive_deletes=True,
    )
    client_orders: Mapped[list[ClientOrder]] = relationship(
        back_populates="customer",
        passive_deletes=True,
    )


class CustomerUsernameHistory(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only history of a Customer's previous usernames."""

    __tablename__ = "customer_username_history"
    __table_args__ = (
        CheckConstraint("length(btrim(username)) > 0", name="username_not_empty"),
        Index(
            "ix_customer_username_history_customer_id_created_at",
            "customer_id",
            "created_at",
        ),
    )

    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="username_history")


class CustomerPlaceIDHistory(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only history of a Customer's previous Place IDs."""

    __tablename__ = "customer_place_id_history"
    __table_args__ = (
        CheckConstraint("place_id > 0", name="place_id_positive"),
        Index(
            "ix_customer_place_id_history_customer_id_created_at",
            "customer_id",
            "created_at",
        ),
    )

    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    place_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="place_id_history")


class ClientOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Primary customer purchase request."""

    __tablename__ = "client_orders"
    __table_args__ = (
        CheckConstraint("requested_robux > 0", name="requested_robux_positive"),
        CheckConstraint(
            "customer_receives IS NULL OR customer_receives >= 0",
            name="customer_receives_nonnegative",
        ),
        CheckConstraint("current_place_id > 0", name="current_place_id_positive"),
        CheckConstraint("marketplace_rate_limit > 0", name="marketplace_rate_limit_positive"),
        CheckConstraint(
            "marketplace_cost IS NULL OR marketplace_cost >= 0",
            name="marketplace_cost_nonnegative",
        ),
        CheckConstraint(
            "marketplace_commission IS NULL OR marketplace_commission >= 0",
            name="marketplace_commission_nonnegative",
        ),
        CheckConstraint(
            "final_cost_usd IS NULL OR final_cost_usd >= 0",
            name="final_cost_usd_nonnegative",
        ),
        CheckConstraint(
            "final_cost_local_currency IS NULL OR final_cost_local_currency >= 0",
            name="final_cost_local_currency_nonnegative",
        ),
        CheckConstraint(
            "usd_exchange_rate IS NULL OR usd_exchange_rate > 0",
            name="usd_exchange_rate_positive",
        ),
        CheckConstraint(
            "(current_status = 'completed' AND completed_at IS NOT NULL "
            "AND customer_receives IS NOT NULL AND marketplace_cost IS NOT NULL "
            "AND marketplace_commission IS NOT NULL AND final_cost_usd IS NOT NULL "
            "AND final_cost_local_currency IS NOT NULL AND usd_exchange_rate IS NOT NULL) "
            "OR (current_status <> 'completed' AND completed_at IS NULL)",
            name="completed_order_fields",
        ),
        CheckConstraint(
            "(current_status = 'cancelled' AND cancelled_at IS NOT NULL) "
            "OR (current_status <> 'cancelled' AND cancelled_at IS NULL)",
            name="cancelled_order_timestamp",
        ),
        Index("ix_client_orders_customer_id", "customer_id"),
        Index("ix_client_orders_current_status", "current_status"),
        Index("ix_client_orders_created_at", "created_at"),
    )

    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_robux: Mapped[int] = mapped_column(BigInteger, nullable=False)
    customer_receives: Mapped[int | None] = mapped_column(BigInteger)
    current_status: Mapped[ClientOrderStatus] = mapped_column(
        _database_enum(ClientOrderStatus, "client_order_status"),
        nullable=False,
        server_default=ClientOrderStatus.DRAFT.value,
    )
    current_place_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    marketplace_rate_limit: Mapped[Decimal] = mapped_column(
        Numeric(RATE_PRECISION, RATE_SCALE),
        nullable=False,
    )
    marketplace_cost: Mapped[Decimal | None] = mapped_column(Numeric(MONEY_PRECISION, MONEY_SCALE))
    marketplace_commission: Mapped[Decimal | None] = mapped_column(
        Numeric(MONEY_PRECISION, MONEY_SCALE)
    )
    final_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(MONEY_PRECISION, MONEY_SCALE))
    final_cost_local_currency: Mapped[Decimal | None] = mapped_column(
        Numeric(MONEY_PRECISION, MONEY_SCALE)
    )
    usd_exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(RATE_PRECISION, RATE_SCALE))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped[Customer] = relationship(back_populates="client_orders")
    marketplace_orders: Mapped[list[MarketplaceOrder]] = relationship(
        back_populates="client_order",
        order_by="MarketplaceOrder.created_at",
        passive_deletes=True,
    )
    timeline_events: Mapped[list[TimelineEvent]] = relationship(
        back_populates="client_order",
        order_by="TimelineEvent.created_at",
        passive_deletes=True,
    )
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="client_order",
        passive_deletes=True,
    )


class MarketplaceOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One RBXCreate execution attempt for a Client Order."""

    __tablename__ = "marketplace_orders"
    __table_args__ = (
        UniqueConstraint("rbxcreate_order_id", name="uq_marketplace_orders_rbxcreate_order_id"),
        CheckConstraint(
            "length(btrim(rbxcreate_order_id)) > 0", name="rbxcreate_order_id_not_empty"
        ),
        CheckConstraint("purchase_rate > 0", name="purchase_rate_positive"),
        CheckConstraint("requested_robux > 0", name="requested_robux_positive"),
        CheckConstraint("purchased_robux >= 0", name="purchased_robux_nonnegative"),
        CheckConstraint("remaining_robux >= 0", name="remaining_robux_nonnegative"),
        CheckConstraint(
            "purchased_robux + remaining_robux = requested_robux",
            name="robux_amounts_consistent",
        ),
        CheckConstraint(
            "(marketplace_status = 'active' AND completed_at IS NULL AND cancelled_at IS NULL) "
            "OR (marketplace_status = 'completed' AND completed_at IS NOT NULL "
            "AND cancelled_at IS NULL AND remaining_robux = 0) "
            "OR (marketplace_status = 'cancelled' AND cancelled_at IS NOT NULL "
            "AND completed_at IS NULL)",
            name="status_timestamps_consistent",
        ),
        Index("ix_marketplace_orders_client_order_id", "client_order_id"),
        Index("ix_marketplace_orders_marketplace_status", "marketplace_status"),
        Index(
            "uq_marketplace_orders_one_active_per_client_order",
            "client_order_id",
            unique=True,
            postgresql_where=text("marketplace_status = 'active'"),
        ),
    )

    client_order_id: Mapped[UUID] = mapped_column(
        ForeignKey("client_orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rbxcreate_order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    marketplace_status: Mapped[MarketplaceOrderStatus] = mapped_column(
        _database_enum(MarketplaceOrderStatus, "marketplace_order_status"),
        nullable=False,
        server_default=MarketplaceOrderStatus.ACTIVE.value,
    )
    purchase_rate: Mapped[Decimal] = mapped_column(
        Numeric(RATE_PRECISION, RATE_SCALE),
        nullable=False,
    )
    requested_robux: Mapped[int] = mapped_column(BigInteger, nullable=False)
    purchased_robux: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    remaining_robux: Mapped[int] = mapped_column(BigInteger, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    client_order: Mapped[ClientOrder] = relationship(back_populates="marketplace_orders")


class TimelineEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only Client Order timeline entry."""

    __tablename__ = "timeline_events"
    __table_args__ = (
        CheckConstraint("length(btrim(description)) > 0", name="description_not_empty"),
        Index(
            "ix_timeline_events_client_order_id_created_at",
            "client_order_id",
            "created_at",
        ),
    )

    client_order_id: Mapped[UUID] = mapped_column(
        ForeignKey("client_orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[TimelineEventType] = mapped_column(
        _database_enum(TimelineEventType, "timeline_event_type"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)

    client_order: Mapped[ClientOrder] = relationship(back_populates="timeline_events")


class Notification(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Auditable Telegram notification and delivery state."""

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint("length(btrim(title)) > 0", name="title_not_empty"),
        CheckConstraint("length(btrim(message)) > 0", name="message_not_empty"),
        CheckConstraint(
            "(delivery_status = 'delivered' AND delivered_at IS NOT NULL) "
            "OR (delivery_status <> 'delivered' AND delivered_at IS NULL)",
            name="delivery_timestamp_consistent",
        ),
        Index("ix_notifications_client_order_id", "client_order_id"),
        Index("ix_notifications_delivery_status", "delivery_status"),
    )

    client_order_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("client_orders.id", ondelete="SET NULL")
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        _database_enum(NotificationType, "notification_type"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_status: Mapped[NotificationDeliveryStatus] = mapped_column(
        _database_enum(NotificationDeliveryStatus, "notification_delivery_status"),
        nullable=False,
        server_default=NotificationDeliveryStatus.PENDING.value,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    client_order: Mapped[ClientOrder | None] = relationship(back_populates="notifications")


class Statistics(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Historical order and purchase statistics for one reporting period."""

    __tablename__ = "statistics"
    __table_args__ = (
        UniqueConstraint("period", "period_start", name="uq_statistics_period_start"),
        CheckConstraint("total_orders >= 0", name="total_orders_nonnegative"),
        CheckConstraint("draft_orders >= 0", name="draft_orders_nonnegative"),
        CheckConstraint("preorder_orders >= 0", name="preorder_orders_nonnegative"),
        CheckConstraint("purchasing_orders >= 0", name="purchasing_orders_nonnegative"),
        CheckConstraint("completed_orders >= 0", name="completed_orders_nonnegative"),
        CheckConstraint("cancelled_orders >= 0", name="cancelled_orders_nonnegative"),
        CheckConstraint("total_purchased_robux >= 0", name="total_purchased_robux_nonnegative"),
        CheckConstraint("total_amount_paid >= 0", name="total_amount_paid_nonnegative"),
        CheckConstraint(
            "average_marketplace_rate >= 0", name="average_marketplace_rate_nonnegative"
        ),
        CheckConstraint("average_purchase_cost >= 0", name="average_purchase_cost_nonnegative"),
        CheckConstraint(
            "total_marketplace_commission >= 0",
            name="total_marketplace_commission_nonnegative",
        ),
    )

    period: Mapped[StatisticsPeriod] = mapped_column(
        _database_enum(StatisticsPeriod, "statistics_period"),
        nullable=False,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    total_orders: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    draft_orders: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    preorder_orders: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    purchasing_orders: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    completed_orders: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    cancelled_orders: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    total_purchased_robux: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    total_amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(MONEY_PRECISION, MONEY_SCALE),
        nullable=False,
        server_default=text("0"),
    )
    average_marketplace_rate: Mapped[Decimal] = mapped_column(
        Numeric(RATE_PRECISION, RATE_SCALE),
        nullable=False,
        server_default=text("0"),
    )
    average_purchase_cost: Mapped[Decimal] = mapped_column(
        Numeric(MONEY_PRECISION, MONEY_SCALE),
        nullable=False,
        server_default=text("0"),
    )
    total_marketplace_commission: Mapped[Decimal] = mapped_column(
        Numeric(MONEY_PRECISION, MONEY_SCALE),
        nullable=False,
        server_default=text("0"),
    )


class SystemSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The single active application settings record."""

    __tablename__ = "system_settings"
    __table_args__ = (
        CheckConstraint("maximum_purchase_rate > 0", name="maximum_purchase_rate_positive"),
        CheckConstraint("automatic_reorder_interval_seconds > 0", name="reorder_interval_positive"),
        CheckConstraint(
            "marketplace_monitoring_interval_seconds > 0", name="monitoring_interval_positive"
        ),
        CheckConstraint("synchronization_interval_seconds > 0", name="sync_interval_positive"),
        CheckConstraint("marketplace_commission >= 0", name="marketplace_commission_nonnegative"),
        CheckConstraint("usd_exchange_rate > 0", name="usd_exchange_rate_positive"),
        CheckConstraint(
            "length(btrim(application_timezone)) > 0",
            name="application_timezone_not_empty",
        ),
        Index("uq_system_settings_singleton", text("(true)"), unique=True),
    )

    maximum_purchase_rate: Mapped[Decimal] = mapped_column(
        Numeric(RATE_PRECISION, RATE_SCALE),
        nullable=False,
    )
    automatic_reorder_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
    )
    automatic_reorder_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    marketplace_monitoring_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    synchronization_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    marketplace_commission: Mapped[Decimal] = mapped_column(
        Numeric(MONEY_PRECISION, MONEY_SCALE),
        nullable=False,
    )
    usd_exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(RATE_PRECISION, RATE_SCALE),
        nullable=False,
    )
    telegram_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
    )
    notification_categories: Mapped[list[NotificationType]] = mapped_column(
        ARRAY(_database_enum(NotificationType, "notification_type")),
        nullable=False,
        server_default=text("'{}'::notification_type[]"),
    )
    application_timezone: Mapped[str] = mapped_column(String(64), nullable=False)


class SystemLog(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only operational log record."""

    __tablename__ = "system_logs"
    __table_args__ = (
        CheckConstraint("length(btrim(module)) > 0", name="module_not_empty"),
        CheckConstraint("length(btrim(message)) > 0", name="message_not_empty"),
        Index("ix_system_logs_created_at", "created_at"),
    )

    log_level: Mapped[SystemLogLevel] = mapped_column(
        _database_enum(SystemLogLevel, "system_log_level"),
        nullable=False,
    )
    module: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    related_entity: Mapped[str | None] = mapped_column(String(255))
