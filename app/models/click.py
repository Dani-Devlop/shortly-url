"""Click model — one row per recorded redirect."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Click(Base):
    __tablename__ = "clicks"

    id: Mapped[int] = mapped_column(primary_key=True)
    link_id: Mapped[int] = mapped_column(
        ForeignKey("links.id", ondelete="CASCADE"), index=True, nullable=False
    )
    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    # Privacy: salted SHA-256 of the visitor IP — never the raw address.
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Page that sent the visitor (Referer header), truncated — None = direct.
    referrer: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Coarse device class derived from the user agent at click time:
    # desktop | mobile | tablet | bot | other.
    device: Mapped[str] = mapped_column(
        String(16), nullable=False, default="other", server_default="other", index=True
    )

    link = relationship("Link", back_populates="clicks")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Click link_id={self.link_id}>"
