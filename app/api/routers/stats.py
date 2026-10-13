"""Click analytics endpoints (owner-only): totals, daily series, sparklines,
global device mix, windowed referrers, global activity feed, per-link CSV."""

import csv
import io
import re
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.core.exceptions import ValidationError as SemanticValidationError
from app.db.session import get_db
from app.models import Link, User
from app.schemas.link import (
    ActivityItem,
    ActivityOut,
    CompareItem,
    CompareOut,
    DailyStatPoint,
    DailyStats,
    DeviceBreakdownOut,
    DeviceStat,
    HourCell,
    HoursOut,
    ReferrerStat,
    ReferrerWindowOut,
    SparklineItem,
    SparklinesOut,
    StatsOut,
    TagRollupItem,
    TagRollupOut,
)
from app.services.link_service import get_link_by_code
from app.services.stats_service import (
    count_clicks,
    count_unique_clicks,
    get_clicks_by_hour_for_links,
    get_daily_clicks,
    get_daily_clicks_for_links,
    get_device_breakdown_global,
    get_recent_clicks,
    get_recent_clicks_global,
    get_referrer_device_stats,
    get_tag_rollup,
    get_total_clicks,
)

router = APIRouter(prefix="/api/stats", tags=["stats"])

EXPORT_CLICKS_CAP = 10_000


def _referrer_host(referrer: str | None) -> str | None:
    """Reduce a stored referer to its host (privacy-safe display form)."""
    if not referrer:
        return None
    try:
        host = urlparse(referrer).netloc
    except ValueError:
        return referrer[:64]
    return host[:64] if host else referrer[:64]


async def _owned_link(db: AsyncSession, code: str, user: User):
    link = await get_link_by_code(db, code)
    if link is None or link.owner_id != user.id:
        # 404 (not 403) to avoid leaking the existence of other users' links.
        raise NotFoundError(f"Short code '{code}' does not exist")
    return link


@router.get("/sparklines", response_model=SparklinesOut)
async def sparklines(
    days: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SparklinesOut:
    """Per-link zero-filled daily click series for the dashboard sparklines.

    NOTE: registered before ``/{code}`` so "sparklines" is never read as a code.
    """
    rows = (
        await db.execute(
            select(Link)
            .where(Link.owner_id == user.id)
            .order_by(Link.created_at.desc(), Link.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    series = await get_daily_clicks_for_links(db, [link.id for link in rows], days=days)
    items = [
        SparklineItem(
            code=link.code,
            total_clicks=sum(series.get(link.id, [])),
            points=series.get(link.id, [0] * days),
        )
        for link in rows
    ]
    return SparklinesOut(window_days=days, items=items)


@router.get("/devices", response_model=DeviceBreakdownOut)
async def devices(
    days: int = Query(default=7, ge=1, le=90),
    exclude_bots: bool = Query(default=False, description="Drop the 'bot' device class from the breakdown."),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeviceBreakdownOut:
    """Device mix (desktop/mobile/tablet/bot/other) across the caller's links.

    Set ``exclude_bots=true`` to hide crawler traffic. The ``total`` always
    counts exactly the clicks covered by the returned items.

    NOTE: registered before ``/{code}`` so "devices" is never read as a code.
    """
    link_ids = list(
        (
            await db.execute(select(Link.id).where(Link.owner_id == user.id))
        ).scalars().all()
    )
    items, total = await get_device_breakdown_global(
        db, days=days, link_ids=link_ids, exclude_bots=exclude_bots
    )
    return DeviceBreakdownOut(
        window_days=days,
        total=total,
        items=[DeviceStat(device=device, clicks=clicks) for device, clicks in items],
    )


@router.get("/activity", response_model=ActivityOut)
async def activity_feed(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActivityOut:
    """The caller's most recent clicks across all their links (newest first).

    NOTE: registered before ``/{code}`` so "activity" is never read as a code.
    Referrers are reduced to their host and IP hashes are truncated to 12
    characters, mirroring the detail view's privacy posture.
    """
    link_ids = list(
        (
            await db.execute(select(Link.id).where(Link.owner_id == user.id))
        ).scalars().all()
    )
    rows = await get_recent_clicks_global(db, link_ids=link_ids, limit=limit)
    items = [
        ActivityItem(
            code=code,
            clicked_at=click.clicked_at,
            device=click.device or "other",
            referrer_host=_referrer_host(click.referrer),
            ip_hash=click.ip_hash[:12] if click.ip_hash else None,
        )
        for click, code in rows
    ]
    return ActivityOut(items=items, limit=limit)


@router.get("/tags", response_model=TagRollupOut)
async def tag_rollup(
    days: int = Query(default=30, ge=1, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TagRollupOut:
    """Click performance aggregated per tag across the caller's links.

    Every tag the caller uses is returned (zero-click tags included), ranked
    by clicks in the window, ties alphabetical. ``links`` counts the caller's
    links carrying the tag all-time.

    NOTE: registered before ``/{code}`` so "tags" is never read as a code.
    """
    items = await get_tag_rollup(db, user.id, days=days)
    rollup = [
        TagRollupItem(
            tag=str(item["tag"]),
            links=int(item["links"]),
            clicks=int(item["clicks"]),
            unique_visitors=int(item["unique_visitors"]),
        )
        for item in items
    ]
    return TagRollupOut(
        window_days=days,
        total_clicks=sum(item.clicks for item in rollup),
        items=rollup,
    )


@router.get("/tags/export", response_class=Response, include_in_schema=False)
async def export_tags_csv(
    days: int = Query(default=30, ge=1, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """CSV rollup of click performance per tag (same data as ``/api/stats/tags``)."""
    items = await get_tag_rollup(db, user.id, days=days)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["tag", "links", "clicks", "unique_visitors"])
    for item in items:
        writer.writerow(
            [item["tag"], item["links"], item["clicks"], item["unique_visitors"]]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="shortly-tags.csv"'},
    )


_CODE_SPLIT_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


@router.get("/compare", response_model=CompareOut)
async def compare_codes(
    codes: str = Query(
        ...,
        min_length=3,
        max_length=80,
        description="Exactly two short codes, comma-separated (e.g. codes=a,b).",
    ),
    days: int = Query(default=14, ge=1, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompareOut:
    """Side-by-side comparison of exactly two of the caller's links.

    Returns per-code totals, unique visitors and a zero-filled daily series
    over the window (one grouped query). Unknown or foreign codes → 404.
    """
    parts = [part.strip() for part in codes.split(",")]
    parts = [part for part in parts if part]
    if len(parts) != 2:
        raise SemanticValidationError("provide exactly two codes, e.g. codes=a,b")
    if parts[0] == parts[1]:
        raise SemanticValidationError("pick two different codes to compare")
    for part in parts:
        if not _CODE_SPLIT_RE.match(part):
            raise SemanticValidationError(f"invalid short code '{part[:32]}'")
    links = []
    for code in parts:
        link = await get_link_by_code(db, code)
        if link is None or link.owner_id != user.id:
            raise NotFoundError(f"Short code '{code}' does not exist")
        links.append(link)
    series = await get_daily_clicks_for_links(db, [link.id for link in links], days=days)
    items = [
        CompareItem(
            code=link.code,
            original_url=link.original_url,
            total_clicks=await count_clicks(db, link.id),
            unique_clicks=await count_unique_clicks(db, link.id),
            points=series.get(link.id, [0] * days),
        )
        for link in links
    ]
    return CompareOut(window_days=days, items=items)


@router.get("/{code}", response_model=StatsOut)
async def link_stats(
    code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StatsOut:
    """Total and unique clicks for a link."""
    link = await _owned_link(db, code, user)
    return StatsOut(
        code=link.code,
        original_url=link.original_url,
        total_clicks=await get_total_clicks(db, link),
        unique_clicks=await count_unique_clicks(db, link.id),
        created_at=link.created_at,
    )


@router.get("/{code}/daily", response_model=DailyStats)
async def link_daily_stats(
    code: str,
    days: int = Query(default=14, ge=1, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DailyStats:
    """Clicks aggregated per day over a rolling window (1–90 days)."""
    link = await _owned_link(db, code, user)
    items = [
        DailyStatPoint(date=day, clicks=clicks)
        for day, clicks in await get_daily_clicks(db, link, days=days)
    ]
    return DailyStats(
        code=link.code,
        window_days=days,
        total=sum(item.clicks for item in items),
        items=items,
    )


@router.get("/{code}/referrers", response_model=ReferrerWindowOut)
async def link_referrer_window(
    code: str,
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=10, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReferrerWindowOut:
    """Top traffic sources for one link within a rolling window (1–90 days).

    ``items`` are ranked sources (``direct`` when the referer was absent);
    ``total`` counts every click in the window, including beyond ``limit``.
    Each item carries a ``devices`` cross-tab (clicks per device class for
    that source) so clients can render stacked bars without extra calls.
    """
    link = await _owned_link(db, code, user)
    rows, total = await get_referrer_device_stats(db, link, days=days, limit=limit)
    return ReferrerWindowOut(
        code=link.code,
        window_days=days,
        total=total,
        items=[
            ReferrerStat(source=source or "direct", clicks=clicks, devices=devices)
            for source, clicks, devices in rows
        ],
    )


@router.get("/{code}/hours", response_model=HoursOut)
async def link_hours(
    code: str,
    days: int = Query(default=30, ge=1, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HoursOut:
    """Clicks by (day-of-week, hour-of-day) over a rolling window — a 7×24 heatmap.

    Always returns exactly 168 zero-filled cells (Sunday 00:00 first, UTC).
    ``total`` is the window's click count; ``peak`` the busiest single cell.
    """
    link = await _owned_link(db, code, user)
    raw = await get_clicks_by_hour_for_links(db, [link.id], days=days)
    cells = [
        HourCell(dow=dow, hour=hour, clicks=raw.get((dow, hour), 0))
        for dow in range(7)
        for hour in range(24)
    ]
    total = sum(cell.clicks for cell in cells)
    return HoursOut(
        code=link.code,
        window_days=days,
        total=total,
        peak=max((cell.clicks for cell in cells), default=0),
        cells=cells,
    )


@router.get("/{code}/export", response_class=Response, include_in_schema=False)
async def export_clicks_csv(
    code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """CSV download of a link's individual clicks (newest first, capped)."""
    link = await _owned_link(db, code, user)
    clicks = await get_recent_clicks(db, link, limit=EXPORT_CLICKS_CAP)

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["clicked_at", "ip_hash", "user_agent", "referrer", "device"])
    for click in clicks:
        writer.writerow(
            [
                click.clicked_at.isoformat() if click.clicked_at else "",
                (click.ip_hash or "")[:12],  # truncated for privacy, as in detail view
                click.user_agent or "",
                click.referrer or "direct",
                click.device or "other",
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{link.code}-clicks.csv"'
        },
    )
