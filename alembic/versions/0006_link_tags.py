"""link_tags — per-link tag association table (organise/filter links)

Revision ID: 0006
Revises: 0005
Create Date: 2025-01-06 00:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "link_tags",
        sa.Column(
            "link_id",
            sa.Integer(),
            sa.ForeignKey("links.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tag", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("link_id", "tag", name="pk_link_tags"),
    )
    op.create_index("ix_link_tags_tag", "link_tags", ["tag"])
    op.create_index("ix_link_tags_link_id", "link_tags", ["link_id"])


def downgrade() -> None:
    op.drop_index("ix_link_tags_link_id", table_name="link_tags")
    op.drop_index("ix_link_tags_tag", table_name="link_tags")
    op.drop_table("link_tags")
