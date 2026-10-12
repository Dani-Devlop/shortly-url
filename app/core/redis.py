"""Redis client with graceful degradation.

Every cache operation is best-effort: if Redis is unavailable the helpers
silently no-op (and log), so the API keeps working against the database.
"""

import json
import logging
from typing import Any

from redis.asyncio import Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_client: Redis | None = None


async def init_redis() -> Redis | None:
    """Connect to Redis at startup; never raises."""
    global _client
    if not settings.redis_enabled:
        logger.info("redis disabled (REDIS_URL empty) — running in DB-only mode")
        return None
    try:
        client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            health_check_interval=30,
        )
        await client.ping()
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis unavailable, continuing without cache: %s", exc)
        _client = None
        return None
    _client = client
    logger.info("redis connected")
    return _client


def get_redis() -> Redis | None:
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:  # noqa: BLE001
            pass
        _client = None


async def cache_get(key: str) -> Any | None:
    if _client is None:
        return None
    try:
        raw = await _client.get(key)
        return json.loads(raw) if raw is not None else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache_get failed for %s: %s", key, exc)
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    if _client is None:
        return
    try:
        await _client.set(key, json.dumps(value), ex=ttl_seconds)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache_set failed for %s: %s", key, exc)


async def cache_delete(key: str) -> None:
    if _client is None:
        return
    try:
        await _client.delete(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache_delete failed for %s: %s", key, exc)


async def incr_counter(key: str) -> int | None:
    if _client is None:
        return None
    try:
        return int(await _client.incr(key))
    except Exception as exc:  # noqa: BLE001
        logger.warning("incr_counter failed for %s: %s", key, exc)
        return None
