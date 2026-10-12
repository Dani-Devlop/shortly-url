"""Redirect resolution with a Redis cache-aside layer."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.redis import cache_get, cache_set
from app.services.link_service import get_link_by_code

settings = get_settings()


async def resolve_target(db: AsyncSession, code: str) -> dict:
    """Return ``{"url": ..., "id": ...}`` for a short code.

    Cache hit → no DB round-trip. Miss → fetch from PostgreSQL and fill the cache.
    """
    cache_key = f"shortly:short:{code}"
    cached = await cache_get(cache_key)
    if isinstance(cached, dict) and {"url", "id"} <= cached.keys():
        return cached

    link = await get_link_by_code(db, code)
    if link is None:
        raise NotFoundError(f"Short code '{code}' does not exist")

    payload = {"url": link.original_url, "id": link.id}
    await cache_set(cache_key, payload, settings.cache_ttl_seconds)
    return payload
