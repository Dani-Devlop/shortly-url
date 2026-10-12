"""Link business logic: creation, lookup, deletion, URL validation."""

import logging
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError, ConflictError
from app.core.redis import cache_delete, cache_set
from app.core.security import generate_short_code
from app.models import Link

logger = logging.getLogger(__name__)
settings = get_settings()

RESERVED_CODES = {
    "api", "health", "docs", "redoc", "openapi.json", "favicon.ico",
    "static", "assets", "admin", "dashboard", "login", "signup", "metrics",
}

MAX_CODE_ATTEMPTS = 10


class LinkExpiryUnset:
    """Sentinel type — 'do not touch the expiry' (distinct from explicit None)."""


_UNSET = LinkExpiryUnset()


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def validate_target_url(url: str) -> None:
    """Reject URLs that point back at this service (redirect loops / open-redirect abuse)."""
    host = _host_of(url)
    self_host = _host_of(settings.base_url)
    if host and self_host and host == self_host:
        raise ConflictError("Self-referencing URLs are not allowed")


async def get_link_by_code(db: AsyncSession, code: str) -> Link | None:
    return await db.scalar(select(Link).where(Link.code == code))


async def _generate_unique_code(db: AsyncSession) -> str:
    for _ in range(MAX_CODE_ATTEMPTS):
        code = generate_short_code()
        if await db.scalar(select(Link.id).where(Link.code == code)) is None:
            return code
    raise AppError(
        "Could not generate a unique short code, please retry",
        status_code=503,
        code="code_generation_failed",
    )


def _cache_payload(link: Link) -> dict:
    """Redis cache shape for a link. ``exp`` is an ISO string or None."""
    return {
        "url": link.original_url,
        "id": link.id,
        "exp": link.expires_at.isoformat() if link.expires_at else None,
    }


async def create_link(
    db: AsyncSession,
    *,
    original_url: str,
    owner_id: int,
    custom_code: str | None = None,
    expires_at: datetime | None = None,
) -> Link:
    """Create a link. Duplicate URLs from the same owner return the existing link."""
    validate_target_url(original_url)

    existing = await db.scalar(
        select(Link).where(Link.owner_id == owner_id, Link.original_url == original_url)
    )
    if existing is not None:
        return existing

    if custom_code:
        if custom_code.lower() in RESERVED_CODES:
            raise ConflictError(f"The code '{custom_code}' is reserved")
        if await db.scalar(select(Link.id).where(Link.code == custom_code)) is not None:
            raise ConflictError(f"The code '{custom_code}' is already in use")
        code = custom_code
    else:
        code = await _generate_unique_code(db)

    link = Link(code=code, original_url=original_url, owner_id=owner_id, expires_at=expires_at)
    db.add(link)
    await db.commit()
    await db.refresh(link)
    # Best-effort cache warm so the very first redirect is already hot.
    await cache_set(
        f"shortly:short:{code}",
        _cache_payload(link),
        settings.cache_ttl_seconds,
    )
    logger.info("created link code=%s owner_id=%s", code, owner_id)
    return link


async def delete_link(db: AsyncSession, link: Link) -> None:
    code = link.code
    await db.delete(link)
    await db.commit()
    # Invalidate the cached mapping so deleted codes 404 immediately.
    await cache_delete(f"shortly:short:{code}")
    logger.info("deleted link code=%s", code)


async def update_link(
    db: AsyncSession,
    link: Link,
    *,
    new_url: str | None = None,
    expires_at: datetime | None | LinkExpiryUnset = _UNSET,
) -> Link:
    """Update destination and/or expiry, then invalidate the link's cache.

    ``expires_at`` accepts:
    - ``_UNSET`` (default): leave the expiry untouched
    - ``None``: clear the expiry
    - a datetime: set the expiry
    """
    changed = False
    if new_url is not None:
        validate_target_url(new_url)
        if link.original_url != new_url:
            link.original_url = new_url
            changed = True
    if not isinstance(expires_at, LinkExpiryUnset):
        if link.expires_at != expires_at:
            link.expires_at = expires_at
            changed = True
    if changed:
        db.add(link)
        await db.commit()
        await db.refresh(link)
        await cache_delete(f"shortly:short:{link.code}")
        logger.info("updated link code=%s", link.code)
    return link
