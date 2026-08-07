"""Add the final V1 auto-requeue policy and notification categories.

Revision ID: 20260807_0004
Revises: 20260807_0003
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260807_0004"
down_revision: str | None = "20260807_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_NOTIFICATION_TYPES = (
    "stock_available",
    "auto_requeue_started",
    "auto_requeue_completed",
    "auto_requeue_failed",
)


def upgrade() -> None:
    """Persist the small amount of state required by guarded automatic requeue."""
    context = op.get_context()
    with context.autocommit_block():
        for value in NEW_NOTIFICATION_TYPES:
            op.execute(f"ALTER TYPE notification_type ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column(
        "client_orders",
        sa.Column(
            "automatic_requeue_enabled",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.add_column(
        "client_orders",
        sa.Column("last_requeue_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "client_orders",
        sa.Column(
            "requeue_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_client_orders_requeue_attempts_nonnegative"),
        "client_orders",
        "requeue_attempts >= 0",
    )

    op.add_column(
        "system_settings",
        sa.Column(
            "auto_requeue_delay_seconds",
            sa.Numeric(precision=8, scale=3),
            server_default=sa.text("5"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_system_settings_auto_requeue_delay_minimum"),
        "system_settings",
        "auto_requeue_delay_seconds >= 0.3",
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM system_settings WHERE marketplace_commission > 100
            ) THEN
                RAISE EXCEPTION
                    'Cannot normalize marketplace commission values above 100 percent';
            END IF;
        END
        $$
        """
    )
    op.execute(
        "UPDATE system_settings "
        "SET marketplace_commission = marketplace_commission / 100 "
        "WHERE marketplace_commission > 1"
    )
    op.execute(
        "ALTER TABLE system_settings DROP CONSTRAINT IF EXISTS "
        "ck_system_settings_marketplace_commission_nonnegative"
    )
    op.create_check_constraint(
        op.f("ck_system_settings_marketplace_commission_rate"),
        "system_settings",
        "marketplace_commission >= 0 AND marketplace_commission <= 1",
    )

    op.execute("UPDATE user_place_cache SET roblox_username = lower(roblox_username)")
    for value in NEW_NOTIFICATION_TYPES:
        op.execute(
            "UPDATE system_settings "
            f"SET notification_categories = array_append(notification_categories, '{value}') "
            "WHERE 'automatic_reorder' = ANY(notification_categories) "
            f"AND NOT ('{value}' = ANY(notification_categories))"
        )
    op.execute(
        "UPDATE system_settings "
        "SET notification_categories = "
        "array_remove(notification_categories, 'automatic_reorder')"
    )


def downgrade() -> None:
    """Remove V1 requeue state only when new notification rows are absent."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM notifications
                WHERE notification_type::text IN (
                    'stock_available',
                    'auto_requeue_started',
                    'auto_requeue_completed',
                    'auto_requeue_failed'
                )
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade while final V1 notification rows exist';
            END IF;
        END
        $$
        """
    )

    op.execute(
        "UPDATE system_settings "
        "SET notification_categories = "
        "array_append(notification_categories, 'automatic_reorder') "
        "WHERE notification_categories && "
        "ARRAY['stock_available', 'auto_requeue_started', "
        "'auto_requeue_completed', 'auto_requeue_failed']::notification_type[] "
        "AND NOT ('automatic_reorder' = ANY(notification_categories))"
    )
    for value in NEW_NOTIFICATION_TYPES:
        op.execute(
            "UPDATE system_settings "
            f"SET notification_categories = array_remove(notification_categories, '{value}')"
        )

    op.execute(
        "ALTER TABLE system_settings DROP CONSTRAINT IF EXISTS "
        "ck_system_settings_marketplace_commission_rate"
    )
    op.create_check_constraint(
        op.f("ck_system_settings_marketplace_commission_nonnegative"),
        "system_settings",
        "marketplace_commission >= 0",
    )
    op.execute(
        "ALTER TABLE system_settings DROP CONSTRAINT IF EXISTS "
        "ck_system_settings_auto_requeue_delay_minimum"
    )
    op.drop_column("system_settings", "auto_requeue_delay_seconds")

    op.execute(
        "ALTER TABLE client_orders DROP CONSTRAINT IF EXISTS "
        "ck_client_orders_requeue_attempts_nonnegative"
    )
    op.drop_column("client_orders", "requeue_attempts")
    op.drop_column("client_orders", "last_requeue_at")
    op.drop_column("client_orders", "automatic_requeue_enabled")

    op.execute("ALTER TYPE notification_type RENAME TO notification_type_final_v1")
    op.execute(
        "CREATE TYPE notification_type AS ENUM ("
        "'purchase_completed', 'marketplace_error', 'synchronization_failed', "
        "'application_restarted', 'application_recovered', 'automatic_reorder', "
        "'manual_reorder', 'order_cancelled')"
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
    op.execute("DROP TYPE notification_type_final_v1")
