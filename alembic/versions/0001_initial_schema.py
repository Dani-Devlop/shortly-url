"""initial schema — users, links, clicks

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("api_key", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_api_key"), "users", ["api_key"], unique=True)

    op.create_table(
        "links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("original_url", sa.String(length=2048), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_links_code"), "links", ["code"], unique=True)
    op.create_index(op.f("ix_links_owner_id"), "links", ["owner_id"])

    op.create_table(
        "clicks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("link_id", sa.Integer(), nullable=False),
        sa.Column(
            "clicked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(["link_id"], ["links.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_clicks_link_id"), "clicks", ["link_id"])
    op.create_index(op.f("ix_clicks_clicked_at"), "clicks", ["clicked_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_clicks_clicked_at"), table_name="clicks")
    op.drop_index(op.f("ix_clicks_link_id"), table_name="clicks")
    op.drop_table("clicks")
    op.drop_index(op.f("ix_links_owner_id"), table_name="links")
    op.drop_index(op.f("ix_links_code"), table_name="links")
    op.drop_table("links")
    op.drop_index(op.f("ix_users_api_key"), table_name="users")
    op.drop_table("users")
