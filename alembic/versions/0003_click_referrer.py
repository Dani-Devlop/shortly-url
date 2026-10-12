"""click referrer — adds clicks.referrer (source-page analytics)

Revision ID: 0003
Revises: 0002
Create Date: 2025-01-03 00:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clicks",
        sa.Column("referrer", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clicks", "referrer")
