"""Click statistics: counting and daily aggregation (SQL is the source of truth)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import get_redis
from app.models import Click, Link

settings = get_settings()


async def count_clicks(db: AsyncSession, link_id: int) -> int:
    value = await db.scalar(
        select(func.count()).select_from(Click).where(Click.link_id == link_id)
    )
    return int(value or 0)


async def click_counts_for_links(db: AsyncSession, link_ids: list[int]) -> dict[int, int]:
    """Batched click counts for a set of links (avoids N+1 queries)."""
    if not link_ids:
        return {}
    rows = await db.execute(
        select(Click.link_id, func.count())
        .where(Click.link_id.in_(link_ids))
        .group_by(Click.link_id)
    )
    return {int(link_id): int(count) for link_id, count in rows.all()}


async def get_total_clicks(db: AsyncSession, link: Link) -> int:
    """Live counter from Redis with a DB fallback + cache backfill.

    SQL remains the source of truth: if the counter key is missing it is
    rebuilt from the ``clicks`` table.
    """
    redis = get_redis()
    if redis is None:
        return await count_clicks(db, link.id)
    key = f"shortly:clicks:{link.code}"
    try:
        raw = await redis.get(key)
        if raw is not None:
            return int(raw)
    except Exception:  # noqa: BLE001
        pass
    total = await count_clicks(db, link.id)
    try:
        await redis.set(key, total, ex=settings.counter_ttl_seconds)
    except Exception:  # noqa: BLE001
        pass
    return total


async def get_daily_clicks(
    db: AsyncSession, link: Link, days: int = 14
) -> list[tuple[str, int]]:
    """Aggregated clicks per day, newest first. Portable across PG/SQLite via func.date()."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    day = func.date(Click.clicked_at)
    rows = await db.execute(
        select(day.label("day"), func.count().label("clicks"))
        .where(Click.link_id == link.id, Click.clicked_at >= cutoff)
        .group_by(day)
        .order_by(day.desc())
    )
    return [(str(row.day), int(row.clicks)) for row in rows.all()]
