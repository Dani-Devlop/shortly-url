"""links.utm_template — per-link default UTM/campaign query parameters

Revision ID: 0005
Revises: 0004
Create Date: 2025-01-05 00:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "links",
        sa.Column("utm_template", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("links", "utm_template")
