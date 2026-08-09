"""Add local force-closed order states.

Revision ID: 20260809_0008
Revises: 20260808_0007
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260809_0008"
down_revision: str | None = "20260808_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add terminal local states and update their timestamp constraints."""
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE client_order_status ADD VALUE IF NOT EXISTS 'force_closed'")
        op.execute("ALTER TYPE marketplace_order_status ADD VALUE IF NOT EXISTS 'force_closed'")

    op.execute(
        "ALTER TABLE client_orders DROP CONSTRAINT IF EXISTS "
        "ck_client_orders_cancelled_order_timestamp"
    )
    op.create_check_constraint(
        op.f("ck_client_orders_cancelled_order_timestamp"),
        "client_orders",
        "(current_status IN ('cancelled', 'force_closed') AND cancelled_at IS NOT NULL) "
        "OR (current_status NOT IN ('cancelled', 'force_closed') AND cancelled_at IS NULL)",
    )

    op.execute(
        "ALTER TABLE marketplace_orders DROP CONSTRAINT IF EXISTS "
        "ck_marketplace_orders_status_timestamps_consistent"
    )
    op.create_check_constraint(
        op.f("ck_marketplace_orders_status_timestamps_consistent"),
        "marketplace_orders",
        "(marketplace_status = 'active' AND completed_at IS NULL AND cancelled_at IS NULL) "
        "OR (marketplace_status = 'completed' AND completed_at IS NOT NULL "
        "AND cancelled_at IS NULL AND remaining_robux = 0) "
        "OR (marketplace_status IN ('cancelled', 'force_closed') "
        "AND cancelled_at IS NOT NULL AND completed_at IS NULL)",
    )


def downgrade() -> None:
    """Remove force-closed states only when no retained rows use them."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM client_orders WHERE current_status::text = 'force_closed'
            ) OR EXISTS (
                SELECT 1 FROM marketplace_orders
                WHERE marketplace_status::text = 'force_closed'
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade while FORCE_CLOSED Client or Marketplace Orders exist';
            END IF;
        END
        $$
        """
    )

    op.execute(
        "ALTER TABLE client_orders DROP CONSTRAINT IF EXISTS "
        "ck_client_orders_cancelled_order_timestamp"
    )
    op.execute(
        "ALTER TABLE marketplace_orders DROP CONSTRAINT IF EXISTS "
        "ck_marketplace_orders_status_timestamps_consistent"
    )
    op.execute("DROP INDEX IF EXISTS uq_marketplace_orders_one_active_per_client_order")

    op.execute("ALTER TYPE client_order_status RENAME TO client_order_status_force_closed")
    op.execute(
        "CREATE TYPE client_order_status AS ENUM "
        "('draft', 'preorder', 'purchasing', 'completed', 'cancelled')"
    )
    op.execute("ALTER TABLE client_orders ALTER COLUMN current_status DROP DEFAULT")
    op.execute(
        "ALTER TABLE client_orders ALTER COLUMN current_status TYPE client_order_status "
        "USING current_status::text::client_order_status"
    )
    op.execute(
        "ALTER TABLE client_orders ALTER COLUMN current_status "
        "SET DEFAULT 'draft'::client_order_status"
    )
    op.execute("DROP TYPE client_order_status_force_closed")

    op.execute(
        "ALTER TYPE marketplace_order_status RENAME TO marketplace_order_status_force_closed"
    )
    op.execute("CREATE TYPE marketplace_order_status AS ENUM ('active', 'completed', 'cancelled')")
    op.execute("ALTER TABLE marketplace_orders ALTER COLUMN marketplace_status DROP DEFAULT")
    op.execute(
        "ALTER TABLE marketplace_orders ALTER COLUMN marketplace_status "
        "TYPE marketplace_order_status USING marketplace_status::text::marketplace_order_status"
    )
    op.execute(
        "ALTER TABLE marketplace_orders ALTER COLUMN marketplace_status "
        "SET DEFAULT 'active'::marketplace_order_status"
    )
    op.execute("DROP TYPE marketplace_order_status_force_closed")

    op.create_check_constraint(
        op.f("ck_client_orders_cancelled_order_timestamp"),
        "client_orders",
        "(current_status = 'cancelled' AND cancelled_at IS NOT NULL) "
        "OR (current_status <> 'cancelled' AND cancelled_at IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_marketplace_orders_status_timestamps_consistent"),
        "marketplace_orders",
        "(marketplace_status = 'active' AND completed_at IS NULL AND cancelled_at IS NULL) "
        "OR (marketplace_status = 'completed' AND completed_at IS NOT NULL "
        "AND cancelled_at IS NULL AND remaining_robux = 0) "
        "OR (marketplace_status = 'cancelled' AND cancelled_at IS NOT NULL "
        "AND completed_at IS NULL)",
    )
    op.create_index(
        "uq_marketplace_orders_one_active_per_client_order",
        "marketplace_orders",
        ["client_order_id"],
        unique=True,
        postgresql_where=sa.text("marketplace_status = 'active'"),
    )
