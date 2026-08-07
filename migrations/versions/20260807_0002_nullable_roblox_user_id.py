"""Allow Customers to exist before Roblox identity verification.

Revision ID: 20260807_0002
Revises: 20260806_0001
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260807_0002"
down_revision: str | None = "20260806_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Permit unverified Customers while preserving validated real Roblox IDs."""
    op.drop_constraint(
        "uq_customers_roblox_user_id",
        "customers",
        type_="unique",
    )
    op.drop_constraint(
        "ck_customers_roblox_user_id_positive",
        "customers",
        type_="check",
    )
    op.alter_column(
        "customers",
        "roblox_user_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.create_check_constraint(
        "ck_customers_roblox_user_id_positive",
        "customers",
        "roblox_user_id IS NULL OR roblox_user_id > 0",
    )
    op.create_index(
        "uq_customers_roblox_user_id_not_null",
        "customers",
        ["roblox_user_id"],
        unique=True,
        postgresql_where=sa.text("roblox_user_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Restore the required-ID schema only when no unverified Customers remain."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM customers WHERE roblox_user_id IS NULL) THEN
                RAISE EXCEPTION
                    'Cannot downgrade while Customers with NULL roblox_user_id exist';
            END IF;
        END
        $$
        """
    )
    op.drop_index(
        "uq_customers_roblox_user_id_not_null",
        table_name="customers",
    )
    op.drop_constraint(
        "ck_customers_roblox_user_id_positive",
        "customers",
        type_="check",
    )
    op.alter_column(
        "customers",
        "roblox_user_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_customers_roblox_user_id_positive",
        "customers",
        "roblox_user_id > 0",
    )
    op.create_unique_constraint(
        "uq_customers_roblox_user_id",
        "customers",
        ["roblox_user_id"],
    )
