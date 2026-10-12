"""clicks.device — coarse device-class column for audience analytics

Revision ID: 0004
Revises: 0003
Create Date: 2025-01-04 00:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default backfills existing rows; the Python-side default covers new ones.
    op.add_column(
        "clicks",
        sa.Column(
            "device",
            sa.String(length=16),
            nullable=False,
            server_default="other",
        ),
    )
    op.create_index("ix_clicks_device", "clicks", ["device"])


def downgrade() -> None:
    op.drop_index("ix_clicks_device", table_name="clicks")
    op.drop_column("clicks", "device")
