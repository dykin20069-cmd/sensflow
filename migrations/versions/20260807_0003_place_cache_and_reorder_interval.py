"""Add remembered places and permit subsecond automatic reorder intervals.

Revision ID: 20260807_0003
Revises: 20260807_0002
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260807_0003"
down_revision: str | None = "20260807_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the small cache table and allow the documented 300ms interval."""
    op.create_table(
        "user_place_cache",
        sa.Column("roblox_username", sa.String(length=64), nullable=False),
        sa.Column("place_id", sa.BigInteger(), nullable=False),
        sa.Column("place_name", sa.String(length=255), nullable=False),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(roblox_username)) > 0",
            name=op.f("ck_user_place_cache_roblox_username_not_empty"),
        ),
        sa.CheckConstraint(
            "place_id > 0",
            name=op.f("ck_user_place_cache_place_id_positive"),
        ),
        sa.CheckConstraint(
            "length(btrim(place_name)) > 0",
            name=op.f("ck_user_place_cache_place_name_not_empty"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_place_cache"),
    )
    op.create_index(
        "uq_user_place_cache_roblox_username_lower",
        "user_place_cache",
        [sa.text("lower(roblox_username)")],
        unique=True,
    )

    op.execute(
        "ALTER TABLE system_settings "
        "DROP CONSTRAINT IF EXISTS ck_system_settings_reorder_interval_positive"
    )
    op.alter_column(
        "system_settings",
        "automatic_reorder_interval_seconds",
        existing_type=sa.Integer(),
        type_=sa.Numeric(precision=8, scale=3),
        existing_nullable=False,
        postgresql_using="automatic_reorder_interval_seconds::numeric(8,3)",
    )
    op.execute("UPDATE system_settings SET automatic_reorder_interval_seconds = 0.3")
    op.create_check_constraint(
        op.f("ck_system_settings_reorder_interval_minimum"),
        "system_settings",
        "automatic_reorder_interval_seconds >= 0.3",
    )


def downgrade() -> None:
    """Restore whole-second intervals only when all stored values are integral."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM system_settings
                WHERE automatic_reorder_interval_seconds <>
                    trunc(automatic_reorder_interval_seconds)
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade while subsecond automatic reorder intervals exist';
            END IF;
        END
        $$
        """
    )
    op.execute(
        "ALTER TABLE system_settings "
        "DROP CONSTRAINT IF EXISTS ck_system_settings_reorder_interval_minimum"
    )
    op.alter_column(
        "system_settings",
        "automatic_reorder_interval_seconds",
        existing_type=sa.Numeric(precision=8, scale=3),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="automatic_reorder_interval_seconds::integer",
    )
    op.create_check_constraint(
        op.f("ck_system_settings_reorder_interval_positive"),
        "system_settings",
        "automatic_reorder_interval_seconds > 0",
    )
    op.drop_index(
        "uq_user_place_cache_roblox_username_lower",
        table_name="user_place_cache",
    )
    op.drop_table("user_place_cache")
