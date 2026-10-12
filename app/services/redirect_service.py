"""Redirect resolution with a Redis cache-aside layer and expiry enforcement."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import GoneError, NotFoundError
from app.core.redis import cache_get, cache_set
from app.services.link_service import get_link_by_code

settings = get_settings()


def _expired(exp: str | None) -> bool:
    """``exp`` is an ISO timestamp string (or None) carried in the cache payload."""
    if not exp:
        return False
    try:
        expiry = datetime.fromisoformat(exp)
    except ValueError:
        return False
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    return datetime.now(UTC) >= expiry


def _as_aware(value: datetime) -> datetime:
    """SQLite may hand back naive datetimes — treat them as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def resolve_target(db: AsyncSession, code: str) -> tuple[dict, bool]:
    """Return ``({"url": ..., "id": ..., "exp": ...}, cache_hit)`` for a short code.

    Cache hit → no DB round-trip. Miss → fetch from PostgreSQL and fill the cache.
    Raises :class:`GoneError` (410) when the link's ``expires_at`` has passed.
    """
    cache_key = f"shortly:short:{code}"
    cached = await cache_get(cache_key)
    if isinstance(cached, dict) and {"url", "id"} <= cached.keys():
        if _expired(cached.get("exp")):
            raise GoneError()
        return cached, True

    link = await get_link_by_code(db, code)
    if link is None:
        raise NotFoundError(f"Short code '{code}' does not exist")
    if link.expires_at is not None and datetime.now(UTC) >= _as_aware(link.expires_at):
        raise GoneError()

    payload = {
        "url": link.original_url,
        "id": link.id,
        "exp": link.expires_at.isoformat() if link.expires_at else None,
    }
    await cache_set(cache_key, payload, settings.cache_ttl_seconds)
    return payload, False
