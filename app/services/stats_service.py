"""Click statistics: counting and daily aggregation (SQL is the source of truth)."""

from datetime import UTC, datetime, timedelta

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
    cutoff = datetime.now(UTC) - timedelta(days=days)
    day = func.date(Click.clicked_at)
    rows = await db.execute(
        select(day.label("day"), func.count().label("clicks"))
        .where(Click.link_id == link.id, Click.clicked_at >= cutoff)
        .group_by(day)
        .order_by(day.desc())
    )
    return [(str(row.day), int(row.clicks)) for row in rows.all()]


async def get_recent_clicks(
    db: AsyncSession, link: Link, limit: int = 20
) -> list[Click]:
    """Most recent click rows, newest first (for the link-detail view)."""
    rows = await db.execute(
        select(Click)
        .where(Click.link_id == link.id)
        .order_by(Click.clicked_at.desc(), Click.id.desc())
        .limit(limit)
    )
    return list(rows.scalars().all())


async def get_top_referrers(
    db: AsyncSession, link: Link, limit: int = 5, days: int | None = None
) -> list[tuple[str | None, int]]:
    """Traffic sources ranked by clicks.

    ``days=None`` aggregates all-time; an integer restricts the window to the
    last N days (rolling). Returns ``(referrer_or_None, clicks)`` — ``None``
    means direct traffic. Ties break alphabetically for deterministic output.
    """
    stmt = select(Click.referrer, func.count().label("clicks")).where(
        Click.link_id == link.id
    )
    if days is not None:
        stmt = stmt.where(Click.clicked_at >= datetime.now(UTC) - timedelta(days=days))
    rows = await db.execute(
        stmt.group_by(Click.referrer)
        .order_by(func.count().desc(), Click.referrer.asc())
        .limit(limit)
    )
    return [(row.referrer, int(row.clicks)) for row in rows.all()]


async def get_referrer_stats(
    db: AsyncSession, link: Link, days: int, limit: int
) -> tuple[list[tuple[str | None, int]], int]:
    """Windowed referrer breakdown for one link plus the window's click total."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    total = int(
        await db.scalar(
            select(func.count())
            .select_from(Click)
            .where(Click.link_id == link.id, Click.clicked_at >= cutoff)
        )
        or 0
    )
    items = await get_top_referrers(db, link, limit=limit, days=days)
    return items, total


async def get_device_breakdown(db: AsyncSession, link: Link) -> list[tuple[str, int]]:
    """All-time device mix for one link, ranked by clicks (deterministic ties)."""
    rows = await db.execute(
        select(Click.device, func.count().label("clicks"))
        .where(Click.link_id == link.id)
        .group_by(Click.device)
        .order_by(func.count().desc(), Click.device.asc())
    )
    return [(str(row.device), int(row.clicks)) for row in rows.all()]


async def get_device_breakdown_global(
    db: AsyncSession, days: int = 7, link_ids: list[int] | None = None
) -> tuple[list[tuple[str, int]], int]:
    """Device mix over a rolling window, optionally scoped to specific links.

    Returns ``(items, total)`` where items cover every class present in the
    window (``other`` included), ranked by clicks. A zero-click window yields
    ``([], 0)`` so the dashboard can show an empty state.
    """
    stmt = select(Click.device, func.count().label("clicks"))
    if link_ids is not None:
        if not link_ids:
            return [], 0
        stmt = stmt.where(Click.link_id.in_(link_ids))
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = await db.execute(
        stmt.where(Click.clicked_at >= cutoff)
        .group_by(Click.device)
        .order_by(func.count().desc(), Click.device.asc())
    )
    items = [(str(row.device), int(row.clicks)) for row in rows.all()]
    return items, sum(count for _, count in items)


async def get_daily_clicks_for_links(
    db: AsyncSession, link_ids: list[int], days: int = 7
) -> dict[int, list[int]]:
    """Zero-filled per-day click series for several links in one query.

    Returns ``{link_id: [oldest, ..., newest]}`` with exactly ``days`` buckets.
    Portable across PG/SQLite via ``func.date()``.
    """
    if not link_ids:
        return {}
    cutoff = datetime.now(UTC) - timedelta(days=days - 1)
    # Normalise the cutoff to the start of that day so the window is inclusive.
    cutoff = cutoff.replace(hour=0, minute=0, second=0, microsecond=0)
    day = func.date(Click.clicked_at)
    rows = await db.execute(
        select(Click.link_id, day.label("day"), func.count().label("clicks"))
        .where(Click.link_id.in_(link_ids), Click.clicked_at >= cutoff)
        .group_by(Click.link_id, day)
    )
    by_day: dict[int, dict[str, int]] = {}
    for link_id, day_value, clicks in rows.all():
        by_day.setdefault(int(link_id), {})[str(day_value)] = int(clicks)

    today = datetime.now(UTC).date()
    series: dict[int, list[int]] = {}
    for link_id in link_ids:
        counts = by_day.get(link_id, {})
        points = []
        for offset in range(days - 1, -1, -1):
            day_key = str(today - timedelta(days=offset))
            points.append(counts.get(day_key, 0))
        series[link_id] = points
    return series
