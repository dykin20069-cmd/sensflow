"""Add the V2.1.1 default purchase mode and fixed operator timezone.

Revision ID: 20260808_0006
Revises: 20260808_0005
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260808_0006"
down_revision: str | None = "20260808_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist the default Preferred-mode choice and normalize display timezone."""
    op.add_column(
        "system_settings",
        sa.Column(
            "preferred_mode_default",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.execute("UPDATE system_settings SET application_timezone = 'Europe/Moscow'")


def downgrade() -> None:
    """Remove the V2.1.1 default-mode setting without touching order history."""
    op.drop_column("system_settings", "preferred_mode_default")
