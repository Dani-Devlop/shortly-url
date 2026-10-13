"""Click statistics: counting and daily aggregation (SQL is the source of truth)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import get_redis
from app.models import Click, Link, LinkTag

settings = get_settings()


async def count_clicks(db: AsyncSession, link_id: int) -> int:
    value = await db.scalar(
        select(func.count()).select_from(Click).where(Click.link_id == link_id)
    )
    return int(value or 0)


async def count_unique_clicks(db: AsyncSession, link_id: int) -> int:
    """Distinct visitors for one link (NULL ip_hash rows are not counted)."""
    value = await db.scalar(
        select(func.count(func.distinct(Click.ip_hash))).where(Click.link_id == link_id)
    )
    return int(value or 0)


async def count_unique_clicks_global(
    db: AsyncSession, link_ids: list[int] | None = None
) -> int:
    """Distinct visitors across the given links (``None`` = all links)."""
    stmt = select(func.count(func.distinct(Click.ip_hash)))
    if link_ids is not None:
        if not link_ids:
            return 0
        stmt = stmt.where(Click.link_id.in_(link_ids))
    value = await db.scalar(stmt)
    return int(value or 0)


async def get_recent_clicks_global(
    db: AsyncSession, link_ids: list[int] | None = None, limit: int = 20
) -> list[tuple[Click, str]]:
    """Newest clicks across the given links (``None`` = all links).

    Returns ``(click, code)`` pairs, newest first, for the activity feed.
    """
    stmt = select(Click, Link.code).join(Link, Click.link_id == Link.id)
    if link_ids is not None:
        if not link_ids:
            return []
        stmt = stmt.where(Click.link_id.in_(link_ids))
    stmt = stmt.order_by(Click.clicked_at.desc(), Click.id.desc()).limit(limit)
    return [(click, str(code)) for click, code in (await db.execute(stmt)).all()]


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
    db: AsyncSession, link: Link, limit: int = 20, exclude_bots: bool = False
) -> list[Click]:
    """Most recent click rows, newest first (for the link-detail view).

    ``exclude_bots=True`` hides crawler-class rows (public page's human view).
    """
    stmt = select(Click).where(Click.link_id == link.id)
    if exclude_bots:
        stmt = stmt.where(Click.device != "bot")
    rows = await db.execute(
        stmt.order_by(Click.clicked_at.desc(), Click.id.desc()).limit(limit)
    )
    return list(rows.scalars().all())


async def get_top_referrers(
    db: AsyncSession,
    link: Link,
    limit: int = 5,
    days: int | None = None,
    exclude_bots: bool = False,
) -> list[tuple[str | None, int]]:
    """Traffic sources ranked by clicks.

    ``days=None`` aggregates all-time; an integer restricts the window to the
    last N days (rolling). Returns ``(referrer_or_None, clicks)`` — ``None``
    means direct traffic. Ties break alphabetically for deterministic output.
    ``exclude_bots=True`` drops crawler clicks from the ranking.
    """
    stmt = select(Click.referrer, func.count().label("clicks")).where(
        Click.link_id == link.id
    )
    if days is not None:
        stmt = stmt.where(Click.clicked_at >= datetime.now(UTC) - timedelta(days=days))
    if exclude_bots:
        stmt = stmt.where(Click.device != "bot")
    rows = await db.execute(
        stmt.group_by(Click.referrer)
        .order_by(func.count().desc(), Click.referrer.asc())
        .limit(limit)
    )
    return [(row.referrer, int(row.clicks)) for row in rows.all()]


async def get_referrer_device_stats(
    db: AsyncSession,
    link: Link,
    days: int | None,
    limit: int,
    exclude_bots: bool = False,
) -> tuple[list[tuple[str | None, int, dict[str, int]]], int]:
    """Referrer × device cross-tab from ONE grouped query.

    Returns ``(items, total)`` where each item is
    ``(referrer_or_None, clicks, {device: clicks})`` ranked by clicks desc
    with ties broken alphabetically (direct traffic — ``None`` — sorts first
    on ties, consistently across PostgreSQL and SQLite). ``total`` counts
    every click in scope, including sources beyond ``limit``. ``days=None``
    aggregates all-time; ``exclude_bots=True`` drops the crawler class from
    both the ranking and each source's device map.
    """
    stmt = select(Click.referrer, Click.device, func.count().label("clicks")).where(
        Click.link_id == link.id
    )
    if days is not None:
        stmt = stmt.where(Click.clicked_at >= datetime.now(UTC) - timedelta(days=days))
    if exclude_bots:
        stmt = stmt.where(Click.device != "bot")
    rows = await db.execute(stmt.group_by(Click.referrer, Click.device))
    devices_by_ref: dict[str | None, dict[str, int]] = {}
    for referrer, device, clicks in rows.all():
        devices_by_ref.setdefault(referrer, {})[str(device)] = int(clicks)
    items = sorted(
        ((ref, sum(dev.values()), dev) for ref, dev in devices_by_ref.items()),
        key=lambda item: (-item[1], item[0] or ""),
    )
    total = sum(clicks for _, clicks, _ in items)
    return items[:limit], total


async def get_device_breakdown(
    db: AsyncSession, link: Link, exclude_bots: bool = False
) -> list[tuple[str, int]]:
    """All-time device mix for one link, ranked by clicks (deterministic ties).

    ``exclude_bots=True`` drops the crawler class (public page's human view).
    """
    stmt = select(Click.device, func.count().label("clicks")).where(
        Click.link_id == link.id
    )
    if exclude_bots:
        stmt = stmt.where(Click.device != "bot")
    rows = await db.execute(
        stmt.group_by(Click.device)
        .order_by(func.count().desc(), Click.device.asc())
    )
    return [(str(row.device), int(row.clicks)) for row in rows.all()]


async def get_device_breakdown_global(
    db: AsyncSession,
    days: int = 7,
    link_ids: list[int] | None = None,
    exclude_bots: bool = False,
) -> tuple[list[tuple[str, int]], int]:
    """Device mix over a rolling window, optionally scoped to specific links.

    ``exclude_bots=True`` drops the crawler class from the breakdown. Returns
    ``(items, total)`` where items cover every class present in the window
    (``other`` included), ranked by clicks. A zero-click window yields
    ``([], 0)`` so the dashboard can show an empty state.
    """
    stmt = select(Click.device, func.count().label("clicks"))
    if link_ids is not None:
        if not link_ids:
            return [], 0
        stmt = stmt.where(Click.link_id.in_(link_ids))
    if exclude_bots:
        stmt = stmt.where(Click.device != "bot")
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = await db.execute(
        stmt.where(Click.clicked_at >= cutoff)
        .group_by(Click.device)
        .order_by(func.count().desc(), Click.device.asc())
    )
    items = [(str(row.device), int(row.clicks)) for row in rows.all()]
    return items, sum(count for _, count in items)


async def get_clicks_by_hour_for_links(
    db: AsyncSession,
    link_ids: list[int],
    days: int = 30,
    exclude_bots: bool = False,
) -> dict[tuple[int, int], int]:
    """Click counts per (day-of-week, hour-of-day) over a rolling window.

    Returns ``{(dow, hour): clicks}`` for the cells that have data — callers
    zero-fill the 7×24 grid. ``dow`` is 0=Sunday … 6=Saturday and ``hour`` is
    0–23, both in UTC, portable across PostgreSQL (``EXTRACT``) and SQLite
    (``strftime``). ``exclude_bots=True`` hides crawler-class clicks.
    """
    if not link_ids:
        return {}
    cutoff = datetime.now(UTC) - timedelta(days=days)
    is_pg = bool(getattr(getattr(db, "bind", None), "dialect", None)) and (
        db.bind.dialect.name == "postgresql"  # type: ignore[union-attr]
    )
    if is_pg:
        dow = func.extract("dow", Click.clicked_at)  # 0=Sunday, matches SQLite %w
        hour = func.extract("hour", Click.clicked_at)
    else:  # SQLite / fallback
        dow = func.strftime("%w", Click.clicked_at)
        hour = func.strftime("%H", Click.clicked_at)
    cell_stmt = select(
        dow.label("dow"), hour.label("hour"), func.count().label("clicks")
    ).where(Click.link_id.in_(link_ids), Click.clicked_at >= cutoff)
    if exclude_bots:
        cell_stmt = cell_stmt.where(Click.device != "bot")
    rows = await db.execute(cell_stmt.group_by(dow, hour))
    cells: dict[tuple[int, int], int] = {}
    for dow_value, hour_value, clicks in rows.all():
        cells[(int(dow_value), int(hour_value))] = int(clicks)
    return cells


async def get_tag_rollup(
    db: AsyncSession, owner_id: int | None, days: int = 30
) -> list[dict[str, int | str]]:
    """Click analytics aggregated per tag over a rolling window.

    ``owner_id=None`` aggregates across ALL links (single-tenant dashboard
    view); an integer scopes the rollup to that owner's links. Returns one
    entry per tag carried by the in-scope links (zero-click tags included):
    ``{"tag", "links", "clicks", "unique_visitors"}`` ranked by clicks desc,
    ties alphabetical. ``links`` counts the in-scope links carrying the tag
    (all-time, not window-limited). Two grouped queries.
    """
    cutoff = datetime.now(UTC) - timedelta(days=days)
    click_stmt = (
        select(
            LinkTag.tag,
            func.count(Click.id).label("clicks"),
            func.count(func.distinct(Click.ip_hash)).label("visitors"),
        )
        .select_from(Click)
        .join(LinkTag, LinkTag.link_id == Click.link_id)
        .join(Link, Link.id == Click.link_id)
        .where(Click.clicked_at >= cutoff)
    )
    link_stmt = (
        select(LinkTag.tag, func.count(func.distinct(LinkTag.link_id)))
        .select_from(LinkTag)
        .join(Link, Link.id == LinkTag.link_id)
    )
    if owner_id is not None:
        click_stmt = click_stmt.where(Link.owner_id == owner_id)
        link_stmt = link_stmt.where(Link.owner_id == owner_id)
    click_rows = await db.execute(click_stmt.group_by(LinkTag.tag))
    click_map = {str(tag): (int(clicks), int(visitors or 0)) for tag, clicks, visitors in click_rows.all()}
    link_rows = await db.execute(link_stmt.group_by(LinkTag.tag))
    link_map = {str(tag): int(n) for tag, n in link_rows.all()}
    items: list[dict[str, int | str]] = []
    for tag in set(link_map) | set(click_map):
        clicks, visitors = click_map.get(tag, (0, 0))
        items.append(
            {
                "tag": tag,
                "links": link_map.get(tag, 0),
                "clicks": clicks,
                "unique_visitors": visitors,
            }
        )
    items.sort(key=lambda item: (-int(item["clicks"]), str(item["tag"])))
    return items


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
