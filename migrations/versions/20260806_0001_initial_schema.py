"""Create the SensFlow V1 database schema.

Revision ID: 20260806_0001
Revises: None
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260806_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

client_order_status = postgresql.ENUM(
    "draft",
    "preorder",
    "purchasing",
    "completed",
    "cancelled",
    name="client_order_status",
    create_type=False,
)
marketplace_order_status = postgresql.ENUM(
    "active",
    "completed",
    "cancelled",
    name="marketplace_order_status",
    create_type=False,
)
timeline_event_type = postgresql.ENUM(
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
    name="timeline_event_type",
    create_type=False,
)
notification_type = postgresql.ENUM(
    "purchase_completed",
    "marketplace_error",
    "synchronization_failed",
    "application_restarted",
    "application_recovered",
    "automatic_reorder",
    "manual_reorder",
    "order_cancelled",
    name="notification_type",
    create_type=False,
)
notification_delivery_status = postgresql.ENUM(
    "pending",
    "delivered",
    "failed",
    name="notification_delivery_status",
    create_type=False,
)
statistics_period = postgresql.ENUM(
    "daily",
    "weekly",
    "monthly",
    name="statistics_period",
    create_type=False,
)
system_log_level = postgresql.ENUM(
    "debug",
    "info",
    "warning",
    "error",
    "critical",
    name="system_log_level",
    create_type=False,
)

ENUM_TYPES = (
    client_order_status,
    marketplace_order_status,
    timeline_event_type,
    notification_type,
    notification_delivery_status,
    statistics_period,
    system_log_level,
)


def upgrade() -> None:
    """Create all V1 tables, constraints, indexes, and protection triggers."""
    connection = op.get_bind()
    for enum_type in ENUM_TYPES:
        enum_type.create(connection, checkfirst=False)

    op.create_table(
        "customers",
        sa.Column("roblox_user_id", sa.BigInteger(), nullable=False),
        sa.Column("current_username", sa.String(length=64), nullable=False),
        sa.Column("current_place_id", sa.BigInteger(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("archived", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "last_activity",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("roblox_user_id > 0", name=op.f("ck_customers_roblox_user_id_positive")),
        sa.CheckConstraint(
            "length(btrim(current_username)) > 0",
            name=op.f("ck_customers_current_username_not_empty"),
        ),
        sa.CheckConstraint(
            "current_place_id > 0", name=op.f("ck_customers_current_place_id_positive")
        ),
        sa.PrimaryKeyConstraint("id", name="pk_customers"),
        sa.UniqueConstraint("roblox_user_id", name="uq_customers_roblox_user_id"),
    )
    op.create_index("ix_customers_current_username", "customers", ["current_username"])

    op.create_table(
        "customer_username_history",
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(btrim(username)) > 0",
            name=op.f("ck_customer_username_history_username_not_empty"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_customer_username_history_customer_id_customers",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_customer_username_history"),
    )
    op.create_index(
        "ix_customer_username_history_customer_id_created_at",
        "customer_username_history",
        ["customer_id", "created_at"],
    )

    op.create_table(
        "customer_place_id_history",
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("place_id", sa.BigInteger(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "place_id > 0",
            name=op.f("ck_customer_place_id_history_place_id_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_customer_place_id_history_customer_id_customers",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_customer_place_id_history"),
    )
    op.create_index(
        "ix_customer_place_id_history_customer_id_created_at",
        "customer_place_id_history",
        ["customer_id", "created_at"],
    )

    op.create_table(
        "client_orders",
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_robux", sa.BigInteger(), nullable=False),
        sa.Column("customer_receives", sa.BigInteger(), nullable=True),
        sa.Column("current_status", client_order_status, server_default="draft", nullable=False),
        sa.Column("current_place_id", sa.BigInteger(), nullable=False),
        sa.Column("marketplace_rate_limit", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("marketplace_cost", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("marketplace_commission", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("final_cost_usd", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("final_cost_local_currency", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("usd_exchange_rate", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "requested_robux > 0", name=op.f("ck_client_orders_requested_robux_positive")
        ),
        sa.CheckConstraint(
            "customer_receives IS NULL OR customer_receives >= 0",
            name=op.f("ck_client_orders_customer_receives_nonnegative"),
        ),
        sa.CheckConstraint(
            "current_place_id > 0", name=op.f("ck_client_orders_current_place_id_positive")
        ),
        sa.CheckConstraint(
            "marketplace_rate_limit > 0",
            name=op.f("ck_client_orders_marketplace_rate_limit_positive"),
        ),
        sa.CheckConstraint(
            "marketplace_cost IS NULL OR marketplace_cost >= 0",
            name=op.f("ck_client_orders_marketplace_cost_nonnegative"),
        ),
        sa.CheckConstraint(
            "marketplace_commission IS NULL OR marketplace_commission >= 0",
            name=op.f("ck_client_orders_marketplace_commission_nonnegative"),
        ),
        sa.CheckConstraint(
            "final_cost_usd IS NULL OR final_cost_usd >= 0",
            name=op.f("ck_client_orders_final_cost_usd_nonnegative"),
        ),
        sa.CheckConstraint(
            "final_cost_local_currency IS NULL OR final_cost_local_currency >= 0",
            name=op.f("ck_client_orders_final_cost_local_currency_nonnegative"),
        ),
        sa.CheckConstraint(
            "usd_exchange_rate IS NULL OR usd_exchange_rate > 0",
            name=op.f("ck_client_orders_usd_exchange_rate_positive"),
        ),
        sa.CheckConstraint(
            "(current_status = 'completed' AND completed_at IS NOT NULL "
            "AND customer_receives IS NOT NULL AND marketplace_cost IS NOT NULL "
            "AND marketplace_commission IS NOT NULL AND final_cost_usd IS NOT NULL "
            "AND final_cost_local_currency IS NOT NULL AND usd_exchange_rate IS NOT NULL) "
            "OR (current_status <> 'completed' AND completed_at IS NULL)",
            name=op.f("ck_client_orders_completed_order_fields"),
        ),
        sa.CheckConstraint(
            "(current_status = 'cancelled' AND cancelled_at IS NOT NULL) "
            "OR (current_status <> 'cancelled' AND cancelled_at IS NULL)",
            name=op.f("ck_client_orders_cancelled_order_timestamp"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_client_orders_customer_id_customers",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_client_orders"),
    )
    op.create_index("ix_client_orders_customer_id", "client_orders", ["customer_id"])
    op.create_index("ix_client_orders_current_status", "client_orders", ["current_status"])
    op.create_index("ix_client_orders_created_at", "client_orders", ["created_at"])

    op.create_table(
        "marketplace_orders",
        sa.Column("client_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rbxcreate_order_id", sa.String(length=128), nullable=False),
        sa.Column(
            "marketplace_status", marketplace_order_status, server_default="active", nullable=False
        ),
        sa.Column("purchase_rate", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("requested_robux", sa.BigInteger(), nullable=False),
        sa.Column("purchased_robux", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("remaining_robux", sa.BigInteger(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(btrim(rbxcreate_order_id)) > 0",
            name=op.f("ck_marketplace_orders_rbxcreate_order_id_not_empty"),
        ),
        sa.CheckConstraint(
            "purchase_rate > 0", name=op.f("ck_marketplace_orders_purchase_rate_positive")
        ),
        sa.CheckConstraint(
            "requested_robux > 0",
            name=op.f("ck_marketplace_orders_requested_robux_positive"),
        ),
        sa.CheckConstraint(
            "purchased_robux >= 0",
            name=op.f("ck_marketplace_orders_purchased_robux_nonnegative"),
        ),
        sa.CheckConstraint(
            "remaining_robux >= 0",
            name=op.f("ck_marketplace_orders_remaining_robux_nonnegative"),
        ),
        sa.CheckConstraint(
            "purchased_robux + remaining_robux = requested_robux",
            name=op.f("ck_marketplace_orders_robux_amounts_consistent"),
        ),
        sa.CheckConstraint(
            "(marketplace_status = 'active' AND completed_at IS NULL AND cancelled_at IS NULL) "
            "OR (marketplace_status = 'completed' AND completed_at IS NOT NULL "
            "AND cancelled_at IS NULL AND remaining_robux = 0) "
            "OR (marketplace_status = 'cancelled' AND cancelled_at IS NOT NULL "
            "AND completed_at IS NULL)",
            name=op.f("ck_marketplace_orders_status_timestamps_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["client_order_id"],
            ["client_orders.id"],
            name="fk_marketplace_orders_client_order_id_client_orders",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_marketplace_orders"),
        sa.UniqueConstraint(
            "rbxcreate_order_id",
            name="uq_marketplace_orders_rbxcreate_order_id",
        ),
    )
    op.create_index(
        "ix_marketplace_orders_client_order_id",
        "marketplace_orders",
        ["client_order_id"],
    )
    op.create_index(
        "ix_marketplace_orders_marketplace_status",
        "marketplace_orders",
        ["marketplace_status"],
    )
    op.create_index(
        "uq_marketplace_orders_one_active_per_client_order",
        "marketplace_orders",
        ["client_order_id"],
        unique=True,
        postgresql_where=sa.text("marketplace_status = 'active'"),
    )

    op.create_table(
        "timeline_events",
        sa.Column("client_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", timeline_event_type, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(btrim(description)) > 0",
            name=op.f("ck_timeline_events_description_not_empty"),
        ),
        sa.ForeignKeyConstraint(
            ["client_order_id"],
            ["client_orders.id"],
            name="fk_timeline_events_client_order_id_client_orders",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_timeline_events"),
    )
    op.create_index(
        "ix_timeline_events_client_order_id_created_at",
        "timeline_events",
        ["client_order_id", "created_at"],
    )

    op.create_table(
        "notifications",
        sa.Column("client_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notification_type", notification_type, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "delivery_status",
            notification_delivery_status,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(btrim(title)) > 0",
            name=op.f("ck_notifications_title_not_empty"),
        ),
        sa.CheckConstraint(
            "length(btrim(message)) > 0",
            name=op.f("ck_notifications_message_not_empty"),
        ),
        sa.CheckConstraint(
            "(delivery_status = 'delivered' AND delivered_at IS NOT NULL) "
            "OR (delivery_status <> 'delivered' AND delivered_at IS NULL)",
            name=op.f("ck_notifications_delivery_timestamp_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["client_order_id"],
            ["client_orders.id"],
            name="fk_notifications_client_order_id_client_orders",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
    )
    op.create_index("ix_notifications_client_order_id", "notifications", ["client_order_id"])
    op.create_index("ix_notifications_delivery_status", "notifications", ["delivery_status"])

    op.create_table(
        "statistics",
        sa.Column("period", statistics_period, nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("total_orders", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("draft_orders", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("preorder_orders", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("purchasing_orders", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("completed_orders", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cancelled_orders", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "total_purchased_robux", sa.BigInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "total_amount_paid",
            sa.Numeric(precision=20, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "average_marketplace_rate",
            sa.Numeric(precision=20, scale=8),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "average_purchase_cost",
            sa.Numeric(precision=20, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "total_marketplace_commission",
            sa.Numeric(precision=20, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "total_orders >= 0", name=op.f("ck_statistics_total_orders_nonnegative")
        ),
        sa.CheckConstraint(
            "draft_orders >= 0", name=op.f("ck_statistics_draft_orders_nonnegative")
        ),
        sa.CheckConstraint(
            "preorder_orders >= 0", name=op.f("ck_statistics_preorder_orders_nonnegative")
        ),
        sa.CheckConstraint(
            "purchasing_orders >= 0", name=op.f("ck_statistics_purchasing_orders_nonnegative")
        ),
        sa.CheckConstraint(
            "completed_orders >= 0", name=op.f("ck_statistics_completed_orders_nonnegative")
        ),
        sa.CheckConstraint(
            "cancelled_orders >= 0", name=op.f("ck_statistics_cancelled_orders_nonnegative")
        ),
        sa.CheckConstraint(
            "total_purchased_robux >= 0",
            name=op.f("ck_statistics_total_purchased_robux_nonnegative"),
        ),
        sa.CheckConstraint(
            "total_amount_paid >= 0",
            name=op.f("ck_statistics_total_amount_paid_nonnegative"),
        ),
        sa.CheckConstraint(
            "average_marketplace_rate >= 0",
            name=op.f("ck_statistics_average_marketplace_rate_nonnegative"),
        ),
        sa.CheckConstraint(
            "average_purchase_cost >= 0",
            name=op.f("ck_statistics_average_purchase_cost_nonnegative"),
        ),
        sa.CheckConstraint(
            "total_marketplace_commission >= 0",
            name=op.f("ck_statistics_total_marketplace_commission_nonnegative"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_statistics"),
        sa.UniqueConstraint("period", "period_start", name="uq_statistics_period_start"),
    )

    op.create_table(
        "system_settings",
        sa.Column("maximum_purchase_rate", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column(
            "automatic_reorder_enabled", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column("automatic_reorder_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("marketplace_monitoring_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("synchronization_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("marketplace_commission", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("usd_exchange_rate", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column(
            "telegram_notifications_enabled", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column(
            "notification_categories",
            postgresql.ARRAY(notification_type),
            server_default=sa.text("'{}'::notification_type[]"),
            nullable=False,
        ),
        sa.Column("application_timezone", sa.String(length=64), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "maximum_purchase_rate > 0",
            name=op.f("ck_system_settings_maximum_purchase_rate_positive"),
        ),
        sa.CheckConstraint(
            "automatic_reorder_interval_seconds > 0",
            name=op.f("ck_system_settings_reorder_interval_positive"),
        ),
        sa.CheckConstraint(
            "marketplace_monitoring_interval_seconds > 0",
            name=op.f("ck_system_settings_monitoring_interval_positive"),
        ),
        sa.CheckConstraint(
            "synchronization_interval_seconds > 0",
            name=op.f("ck_system_settings_sync_interval_positive"),
        ),
        sa.CheckConstraint(
            "marketplace_commission >= 0",
            name=op.f("ck_system_settings_marketplace_commission_nonnegative"),
        ),
        sa.CheckConstraint(
            "usd_exchange_rate > 0",
            name=op.f("ck_system_settings_usd_exchange_rate_positive"),
        ),
        sa.CheckConstraint(
            "length(btrim(application_timezone)) > 0",
            name=op.f("ck_system_settings_application_timezone_not_empty"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_system_settings"),
    )
    op.create_index(
        "uq_system_settings_singleton",
        "system_settings",
        [sa.text("(true)")],
        unique=True,
    )

    op.create_table(
        "system_logs",
        sa.Column("log_level", system_log_level, nullable=False),
        sa.Column("module", sa.String(length=100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("related_entity", sa.String(length=255), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(btrim(module)) > 0",
            name=op.f("ck_system_logs_module_not_empty"),
        ),
        sa.CheckConstraint(
            "length(btrim(message)) > 0",
            name=op.f("ck_system_logs_message_not_empty"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_system_logs"),
    )
    op.create_index("ix_system_logs_created_at", "system_logs", ["created_at"])

    _create_protection_triggers()


def downgrade() -> None:
    """Remove all V1 database objects."""
    op.drop_table("system_logs")
    op.drop_index("uq_system_settings_singleton", table_name="system_settings")
    op.drop_table("system_settings")
    op.drop_table("statistics")
    op.drop_table("notifications")
    op.drop_table("timeline_events")
    op.drop_table("marketplace_orders")
    op.drop_table("client_orders")
    op.drop_table("customer_place_id_history")
    op.drop_table("customer_username_history")
    op.drop_table("customers")

    op.execute("DROP FUNCTION reject_protected_row_change()")

    connection = op.get_bind()
    for enum_type in reversed(ENUM_TYPES):
        enum_type.drop(connection, checkfirst=False)


def _create_protection_triggers() -> None:
    op.execute(
        """
        CREATE FUNCTION reject_protected_row_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% does not allow %', TG_TABLE_NAME, TG_OP;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table_name in (
        "customer_username_history",
        "customer_place_id_history",
        "timeline_events",
        "system_logs",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_append_only
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION reject_protected_row_change()
            """
        )

    for table_name in ("customers", "marketplace_orders"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_no_delete
            BEFORE DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION reject_protected_row_change()
            """
        )

    op.execute(
        """
        CREATE TRIGGER trg_client_orders_completed_immutable
        BEFORE UPDATE OR DELETE ON client_orders
        FOR EACH ROW
        WHEN (OLD.current_status = 'completed')
        EXECUTE FUNCTION reject_protected_row_change()
        """
    )
