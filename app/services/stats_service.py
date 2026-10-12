"""Click statistics: counting and daily aggregation (SQL is the source of truth)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Click, Link


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
    return await count_clicks(db, link.id)


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
