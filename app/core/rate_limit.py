"""Redis fixed-window rate limiter (fails open when Redis is down)."""

import logging
import time
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.exceptions import RateLimitError
from app.core.redis import get_redis

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass(frozen=True)
class RateLimitBudget:
    """State of the caller's fixed window, surfaced as X-RateLimit-* headers."""

    limit: int
    remaining: int
    reset_epoch: int  # unix seconds when the window rolls over

    def headers(self) -> dict[str, str]:
        return {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_epoch),
        }


async def enforce_rate_limit(identifier: str, *, cost: int = 1) -> RateLimitBudget | None:
    """Raise :class:`RateLimitError` when the caller exceeds the configured budget.

    ``cost`` lets heavier requests (e.g. bulk shorten) consume several units.
    Returns the caller's :class:`RateLimitBudget` so endpoints can attach
    ``X-RateLimit-*`` headers, or ``None`` when limiting is unavailable
    (Redis down → fail open) and therefore no headers should be advertised.
    """
    redis = get_redis()
    if redis is None:
        return None  # fail open — availability over strictness
    key = f"shortly:rl:{identifier}"
    window = max(1, settings.rate_limit_window_seconds)
    limit = max(1, settings.rate_limit_requests)
    cost = max(1, cost)
    try:
        count = await redis.incr(key, cost)
        if count == cost:  # first hit in this window → (re)arm expiry
            await redis.expire(key, window)
        ttl = await redis.ttl(key)
        ttl = ttl if ttl and ttl > 0 else window
        budget = RateLimitBudget(
            limit=limit,
            remaining=limit - count,
            reset_epoch=int(time.time() + ttl),
        )
        if count > limit:
            raise RateLimitError(retry_after=ttl, budget=budget)
        return budget
    except RateLimitError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("rate limiter unavailable, failing open: %s", exc)
        return None
