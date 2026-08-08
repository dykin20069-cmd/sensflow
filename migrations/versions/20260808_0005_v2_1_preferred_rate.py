"""Add mandatory V2.1 preferred purchasing and alert settings.

Revision ID: 20260808_0005
Revises: 20260807_0004
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260808_0005"
down_revision: str | None = "20260807_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_NOTIFICATION_TYPES = ("low_balance", "critical_balance")


def upgrade() -> None:
    """Persist V2.1 order policy, execution rate, and alert configuration."""
    context = op.get_context()
    with context.autocommit_block():
        for value in NEW_NOTIFICATION_TYPES:
            op.execute(f"ALTER TYPE notification_type ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column(
        "client_orders",
        sa.Column("preferred_rate", sa.Numeric(precision=20, scale=8), nullable=True),
    )
    op.add_column(
        "client_orders",
        sa.Column("preferred_timeout_minutes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "client_orders",
        sa.Column("preferred_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "client_orders",
        sa.Column(
            "fallback_active",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "client_orders",
        sa.Column("executed_rate", sa.Numeric(precision=20, scale=8), nullable=True),
    )
    op.execute(
        "UPDATE client_orders "
        "SET preferred_rate = LEAST(marketplace_rate_limit, 4.3), "
        "preferred_timeout_minutes = 35, "
        "fallback_active = current_status IN ('preorder', 'purchasing') "
        "WHERE current_status <> 'completed'"
    )
    op.create_check_constraint(
        op.f("ck_client_orders_preferred_rate_valid"),
        "client_orders",
        "preferred_rate IS NULL OR "
        "(preferred_rate > 0 AND preferred_rate <= marketplace_rate_limit)",
    )
    op.create_check_constraint(
        op.f("ck_client_orders_preferred_timeout_positive"),
        "client_orders",
        "preferred_timeout_minutes IS NULL OR preferred_timeout_minutes > 0",
    )
    op.create_check_constraint(
        op.f("ck_client_orders_executed_rate_positive"),
        "client_orders",
        "executed_rate IS NULL OR executed_rate > 0",
    )

    op.add_column(
        "system_settings",
        sa.Column("preferred_purchase_rate", sa.Numeric(precision=20, scale=8), nullable=True),
    )
    op.add_column(
        "system_settings",
        sa.Column(
            "preferred_timeout_minutes",
            sa.Integer(),
            server_default=sa.text("35"),
            nullable=False,
        ),
    )
    op.add_column(
        "system_settings",
        sa.Column(
            "low_balance_threshold",
            sa.Numeric(precision=20, scale=4),
            server_default=sa.text("10"),
            nullable=False,
        ),
    )
    op.add_column(
        "system_settings",
        sa.Column(
            "critical_balance_threshold",
            sa.Numeric(precision=20, scale=4),
            server_default=sa.text("5"),
            nullable=False,
        ),
    )
    op.add_column(
        "system_settings",
        sa.Column(
            "stock_notifications_enabled",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE system_settings SET preferred_purchase_rate = LEAST(maximum_purchase_rate, 4.3)"
    )
    op.alter_column(
        "system_settings",
        "preferred_purchase_rate",
        existing_type=sa.Numeric(precision=20, scale=8),
        nullable=False,
        server_default=sa.text("4.3"),
    )
    op.create_check_constraint(
        op.f("ck_system_settings_preferred_purchase_rate_valid"),
        "system_settings",
        "preferred_purchase_rate > 0 AND preferred_purchase_rate <= maximum_purchase_rate",
    )
    op.create_check_constraint(
        op.f("ck_system_settings_preferred_timeout_positive"),
        "system_settings",
        "preferred_timeout_minutes > 0",
    )
    op.create_check_constraint(
        op.f("ck_system_settings_low_balance_threshold_nonnegative"),
        "system_settings",
        "low_balance_threshold >= 0",
    )
    op.create_check_constraint(
        op.f("ck_system_settings_critical_balance_threshold_valid"),
        "system_settings",
        "critical_balance_threshold >= 0 AND critical_balance_threshold <= low_balance_threshold",
    )
    for value in NEW_NOTIFICATION_TYPES:
        op.execute(
            "UPDATE system_settings "
            f"SET notification_categories = array_append(notification_categories, '{value}') "
            f"WHERE NOT ('{value}' = ANY(notification_categories))"
        )


def downgrade() -> None:
    """Remove V2.1 state only when V2.1 notifications are no longer retained."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM notifications
                WHERE notification_type::text IN ('low_balance', 'critical_balance')
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade while V2.1 notification rows exist';
            END IF;
        END
        $$
        """
    )
    for value in NEW_NOTIFICATION_TYPES:
        op.execute(
            "UPDATE system_settings "
            f"SET notification_categories = array_remove(notification_categories, '{value}')"
        )

    for constraint in (
        "ck_system_settings_critical_balance_threshold_valid",
        "ck_system_settings_low_balance_threshold_nonnegative",
        "ck_system_settings_preferred_timeout_positive",
        "ck_system_settings_preferred_purchase_rate_valid",
    ):
        op.execute(f"ALTER TABLE system_settings DROP CONSTRAINT IF EXISTS {constraint}")
    op.drop_column("system_settings", "stock_notifications_enabled")
    op.drop_column("system_settings", "critical_balance_threshold")
    op.drop_column("system_settings", "low_balance_threshold")
    op.drop_column("system_settings", "preferred_timeout_minutes")
    op.drop_column("system_settings", "preferred_purchase_rate")

    for constraint in (
        "ck_client_orders_executed_rate_positive",
        "ck_client_orders_preferred_timeout_positive",
        "ck_client_orders_preferred_rate_valid",
    ):
        op.execute(f"ALTER TABLE client_orders DROP CONSTRAINT IF EXISTS {constraint}")
    op.drop_column("client_orders", "executed_rate")
    op.drop_column("client_orders", "fallback_active")
    op.drop_column("client_orders", "preferred_expires_at")
    op.drop_column("client_orders", "preferred_timeout_minutes")
    op.drop_column("client_orders", "preferred_rate")

    op.execute("ALTER TYPE notification_type RENAME TO notification_type_v2_1")
    op.execute(
        "CREATE TYPE notification_type AS ENUM ("
        "'stock_available', 'auto_requeue_started', 'auto_requeue_completed', "
        "'auto_requeue_failed', 'purchase_completed', 'marketplace_error', "
        "'synchronization_failed', 'application_restarted', 'application_recovered', "
        "'automatic_reorder', 'manual_reorder', 'order_cancelled')"
    )
    op.execute(
        "ALTER TABLE notifications ALTER COLUMN notification_type "
        "TYPE notification_type USING notification_type::text::notification_type"
    )
    op.execute("ALTER TABLE system_settings ALTER COLUMN notification_categories DROP DEFAULT")
    op.execute(
        "ALTER TABLE system_settings ALTER COLUMN notification_categories "
        "TYPE notification_type[] USING notification_categories::text::notification_type[]"
    )
    op.execute(
        "ALTER TABLE system_settings ALTER COLUMN notification_categories "
        "SET DEFAULT '{}'::notification_type[]"
    )
    op.execute("DROP TYPE notification_type_v2_1")
