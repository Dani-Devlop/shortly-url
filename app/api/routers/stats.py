"""Click analytics endpoints (owner-only): totals, daily series, sparklines,
global device mix, windowed referrers, per-link CSV export."""

import csv
import io

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models import Link, User
from app.schemas.link import (
    DailyStatPoint,
    DailyStats,
    DeviceBreakdownOut,
    DeviceStat,
    ReferrerStat,
    ReferrerWindowOut,
    SparklineItem,
    SparklinesOut,
    StatsOut,
)
from app.services.link_service import get_link_by_code
from app.services.stats_service import (
    get_daily_clicks,
    get_daily_clicks_for_links,
    get_device_breakdown_global,
    get_recent_clicks,
    get_referrer_stats,
    get_total_clicks,
)

router = APIRouter(prefix="/api/stats", tags=["stats"])

EXPORT_CLICKS_CAP = 10_000


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
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeviceBreakdownOut:
    """Device mix (desktop/mobile/tablet/bot/other) across the caller's links.

    NOTE: registered before ``/{code}`` so "devices" is never read as a code.
    """
    link_ids = list(
        (
            await db.execute(select(Link.id).where(Link.owner_id == user.id))
        ).scalars().all()
    )
    items, total = await get_device_breakdown_global(db, days=days, link_ids=link_ids)
    return DeviceBreakdownOut(
        window_days=days,
        total=total,
        items=[DeviceStat(device=device, clicks=clicks) for device, clicks in items],
    )


@router.get("/{code}", response_model=StatsOut)
async def link_stats(
    code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StatsOut:
    """Total clicks for a link."""
    link = await _owned_link(db, code, user)
    return StatsOut(
        code=link.code,
        original_url=link.original_url,
        total_clicks=await get_total_clicks(db, link),
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
    """
    link = await _owned_link(db, code, user)
    rows, total = await get_referrer_stats(db, link, days=days, limit=limit)
    return ReferrerWindowOut(
        code=link.code,
        window_days=days,
        total=total,
        items=[ReferrerStat(source=source or "direct", clicks=clicks) for source, clicks in rows],
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
