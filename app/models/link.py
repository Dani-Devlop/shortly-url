"""Link model — a short code mapping to an original URL."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class LinkTag(Base):
    """Association row: one tag on one link (composite PK, cascade delete)."""

    __tablename__ = "link_tags"

    link_id: Mapped[int] = mapped_column(
        ForeignKey("links.id", ondelete="CASCADE"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(String(32), primary_key=True, index=True)

    link = relationship("Link", back_populates="tag_rows", viewonly=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LinkTag link_id={self.link_id} tag={self.tag}>"


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    original_url: Mapped[str] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    utm_template: Mapped[str | None] = mapped_column(String(512), nullable=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    owner = relationship("User", back_populates="links")
    tag_rows = relationship(
        "LinkTag",
        back_populates="link",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="LinkTag.tag",
        # Auto-load with a second SELECT on every Link fetch — avoids async
        # lazy-load (MissingGreenlet) surprises; tag counts are tiny.
        lazy="selectin",
    )
    clicks = relationship(
        "Click",
        back_populates="link",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def tags(self) -> list[str]:
        """Tag names, alphabetical (view of ``tag_rows``)."""
        return [row.tag for row in self.tag_rows]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Link code={self.code}>"
