"""Redis fixed-window rate limiter (fails open when Redis is down)."""

import logging

from app.core.config import get_settings
from app.core.exceptions import RateLimitError
from app.core.redis import get_redis

logger = logging.getLogger(__name__)
settings = get_settings()


async def enforce_rate_limit(identifier: str, *, cost: int = 1) -> None:
    """Raise :class:`RateLimitError` when the caller exceeds the configured budget.

    ``cost`` lets heavier requests (e.g. bulk shorten) consume several units.
    """
    redis = get_redis()
    if redis is None:
        return  # fail open — availability over strictness
    key = f"shortly:rl:{identifier}"
    window = max(1, settings.rate_limit_window_seconds)
    try:
        count = await redis.incr(key, max(1, cost))
        if count == max(1, cost):  # first hit in this window → (re)arm expiry
            await redis.expire(key, window)
        if count > settings.rate_limit_requests:
            ttl = await redis.ttl(key)
            retry_after = ttl if ttl and ttl > 0 else window
            raise RateLimitError(retry_after=retry_after)
    except RateLimitError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("rate limiter unavailable, failing open: %s", exc)
