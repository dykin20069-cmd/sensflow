"""Add persisted marketplace request guards.

Revision ID: 20260808_0007
Revises: 20260808_0006
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260808_0007"
down_revision: str | None = "20260808_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist purchase age, status polling, and rate-limit backoff state."""
    op.add_column(
        "marketplace_orders",
        sa.Column("purchase_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "marketplace_orders",
        sa.Column("last_status_check_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "marketplace_orders",
        sa.Column("status_check_backoff_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "marketplace_orders",
        sa.Column(
            "status_check_rate_limit_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE marketplace_orders "
        "SET purchase_started_at = created_at "
        "WHERE marketplace_status = 'active' AND purchase_started_at IS NULL"
    )
    op.create_check_constraint(
        op.f("ck_marketplace_orders_status_check_rate_limit_count_nonnegative"),
        "marketplace_orders",
        "status_check_rate_limit_count >= 0",
    )


def downgrade() -> None:
    """Remove request guard metadata without changing order state."""
    op.execute(
        "ALTER TABLE marketplace_orders DROP CONSTRAINT IF EXISTS "
        "ck_marketplace_orders_status_check_rate_limit_count_nonnegative"
    )
    op.drop_column("marketplace_orders", "status_check_rate_limit_count")
    op.drop_column("marketplace_orders", "status_check_backoff_until")
    op.drop_column("marketplace_orders", "last_status_check_at")
    op.drop_column("marketplace_orders", "purchase_started_at")
