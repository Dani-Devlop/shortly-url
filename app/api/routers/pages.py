"""HTML dashboard at ``/`` — recent links, click counts, per-code lookup,
top links and client-side admin actions (copy / QR / edit / delete) — plus
the public, shareable stats page at ``/s/{code}``.
"""

import math
import os
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.db.session import get_db
from app.models import Click, Link
from app.services.stats_service import (
    count_clicks,
    count_unique_clicks,
    count_unique_clicks_global,
    get_daily_clicks_for_links,
    get_device_breakdown,
    get_device_breakdown_global,
    get_recent_clicks,
    get_recent_clicks_global,
    get_top_referrers,
)

router = APIRouter(tags=["pages"])

_templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "..", "..", "templates")
)

SPARKLINE_DAYS = 7
DELTA_WINDOW_DAYS = 14  # current week + previous week for the trend chip
DEVICE_PANEL_DAYS = 7
ACTIVITY_ROWS = 8
STATS_PAGE_DAYS = 14  # public stats page chart window
STATS_PAGE_RECENT = 8  # public stats page recent-click rows
STATS_PAGE_REFERRERS = 5
PUBLIC_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
DEVICE_CLASSES = ("desktop", "mobile", "tablet", "bot", "other")
PER_PAGE_CHOICES = (10, 25, 50)
TOP_LINKS_POOL = 200  # window scanned for the "Top links" panel


def _fmt_abs(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _fmt_rel(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = (datetime.now(UTC) - dt).total_seconds()
    if delta < 0:
        delta = 0
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    if delta < 7 * 86400:
        return f"{int(delta // 86400)}d ago"
    return _fmt_abs(dt)[:10]


def _expiry_view(expires_at: datetime | None) -> dict | None:
    """Render data for the expiry badge (None = never expires)."""
    if expires_at is None:
        return None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    delta = (expires_at - datetime.now(UTC)).total_seconds()
    if delta <= 0:
        return {"state": "expired", "label": "expired", "abs": _fmt_abs(expires_at)}
    days = delta / 86400
    if days < 1:
        label = f"in {max(1, int(delta // 3600))}h"
    elif days < 30:
        label = f"in {int(days)}d"
    else:
        label = _fmt_abs(expires_at)[:10]
    return {"state": "soon" if days < 2 else "live", "label": label, "abs": _fmt_abs(expires_at)}


def _sparkline_svg(points: list[int], width: int = 72, height: int = 26) -> str:
    """Server-rendered SVG polyline with a soft area fill (safe: numbers only)."""
    if not points:
        return ""
    max_value = max(points)
    pad = 2.0
    count = len(points)
    if count == 1:
        xs = [width / 2]
    else:
        step = (width - 2 * pad) / (count - 1)
        xs = [pad + i * step for i in range(count)]
    if max_value == 0:
        ys = [height - pad] * count
    else:
        ys = [
            height - pad - (value / max_value) * (height - 2 * pad)
            for value in points
        ]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys, strict=True))
    area_points = f"{pad},{height - pad} {line} {width - pad},{height - pad}"
    total = sum(points)
    return (
        f'<svg class="spark" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{total} clicks in the last {count} days">'
        f'<polygon points="{area_points}" class="spark-area"></polygon>'
        f'<polyline points="{line}" class="spark-line"></polyline>'
        f'</svg><span class="spark-total">{total}↗7d</span>'
    )


def _short_url(base_url: str, code: str) -> str:
    return f"{base_url.rstrip('/')}/{code}"


def _truncate(url: str, limit: int = 64) -> str:
    return url if len(url) <= limit else url[: limit - 1] + "…"


def _referrer_host(referrer: str | None) -> str | None:
    """Reduce a stored referer to its host (privacy-safe display form)."""
    if not referrer:
        return None
    try:
        host = urlparse(referrer).netloc
    except ValueError:
        return referrer[:64]
    return host[:64] if host else referrer[:64]


def _activity_view(rows: list) -> list[dict]:
    """Render data for the Live-activity panel rows."""
    return [
        {
            "code": code,
            "when": _fmt_rel(click.clicked_at),
            "when_abs": _fmt_abs(click.clicked_at),
            "device": click.device or "other",
            "referrer_host": _referrer_host(click.referrer),
            "ip_hash": (click.ip_hash or "")[:12] or None,
        }
        for click, code in rows
    ]


def _trend_label(current: int, previous: int) -> dict | None:
    """Chip data comparing this week's clicks with the previous week."""
    if previous <= 0 and current <= 0:
        return None
    if previous == 0:
        return {"direction": "up", "pct": "new", "title": f"{current} this week vs 0 before"}
    pct = round((current - previous) * 100 / previous)
    if pct > 0:
        return {"direction": "up", "pct": f"+{pct}%", "title": f"{pct}% vs previous week"}
    if pct < 0:
        return {"direction": "down", "pct": f"{pct}%", "title": f"{pct}% vs previous week"}
    return {"direction": "flat", "pct": "±0%", "title": "same as previous week"}


def _device_panel(
    items: list[tuple[str, int]], total: int
) -> list[dict]:
    """Render data for the devices panel: counts + share of the window."""
    if total <= 0:
        return []

    def rank(item: tuple[str, int]) -> tuple[int, int]:
        known = DEVICE_CLASSES.index(item[0]) if item[0] in DEVICE_CLASSES else len(DEVICE_CLASSES)
        return (-item[1], known)

    ranked = sorted(items, key=rank)
    return [
        {"device": device, "clicks": clicks, "pct": round(clicks * 100 / total)}
        for device, clicks in ranked
    ]


async def _links_with_counts(
    db: AsyncSession,
    base_url: str,
    limit: int = 50,
    offset: int = 0,
    with_sparks: bool = True,
) -> tuple[list[dict], int]:
    links = (
        await db.execute(
            select(Link)
            .order_by(Link.created_at.desc(), Link.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    counts = {}
    series = {}
    if links:
        link_ids = [link.id for link in links]
        rows = await db.execute(
            select(Click.link_id, func.count())
            .where(Click.link_id.in_(link_ids))
            .group_by(Click.link_id)
        )
        counts = {int(link_id): int(n) for link_id, n in rows.all()}
        if with_sparks:
            series = await get_daily_clicks_for_links(db, link_ids, days=SPARKLINE_DAYS)
    entries = [
        {
            "code": link.code,
            "short_url": _short_url(base_url, link.code),
            "original_url": link.original_url,
            "original_url_display": _truncate(link.original_url),
            "clicks": counts.get(link.id, 0),
            "created_abs": _fmt_abs(link.created_at),
            "created_rel": _fmt_rel(link.created_at),
            "expiry": _expiry_view(link.expires_at),
            "utm": link.utm_template,
            "sparkline": _sparkline_svg(series.get(link.id, [0] * SPARKLINE_DAYS))
            if with_sparks
            else "",
        }
        for link in links
    ]
    clicks_7d = sum(sum(points) for points in series.values())
    return entries, clicks_7d


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(
    request: Request,
    code: str | None = Query(default=None, max_length=32),
    sort: str = Query(default="recent", pattern="^(recent|clicks)$"),
    page: int = Query(default=1, ge=1, le=1000),
    per_page: int = Query(default=25, ge=1, le=100),
    bots: bool = Query(default=True, description="Include the 'bot' device class in the Devices panel."),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    if per_page not in PER_PAGE_CHOICES:
        per_page = 25
    context: dict = {
        "version": __version__,
        "summary": {"total_links": 0, "total_clicks": 0, "clicks_7d": 0, "avg_clicks": "0"},
        "links": [],
        "top_links": [],
        "lookup": code or "",
        "sort": sort,
        "page": page,
        "per_page": per_page,
        "per_page_choices": PER_PAGE_CHOICES,
        "pagination": None,
        "selected": None,
        "error": None,
        "spark_days": SPARKLINE_DAYS,
        "device_days": DEVICE_PANEL_DAYS,
        "devices": [],
        "devices_total": 0,
        "activity": [],
        "activity_total": 0,
        "trend": None,
        "unique_visitors": 0,
        "bots": bots,
    }
    try:
        total_links = int(
            await db.scalar(select(func.count()).select_from(Link)) or 0
        )
        total_clicks = int(
            await db.scalar(select(func.count()).select_from(Click)) or 0
        )
        context["summary"] = {
            "total_links": total_links,
            "total_clicks": total_clicks,
            "clicks_7d": 0,
            "avg_clicks": f"{total_clicks / total_links:.1f}" if total_links else "0",
        }

        total_pages = max(1, math.ceil(total_links / per_page))
        page = min(page, total_pages)  # clamp stale page numbers after deletions
        offset = (page - 1) * per_page

        base_url = str(request.base_url).rstrip("/")
        entries, _ = await _links_with_counts(
            db, base_url, limit=per_page, offset=offset
        )

        # Trend chip: this week vs previous week from one 14-day grouped query.
        page_link_ids = list(
            (
                await db.execute(
                    select(Link.id)
                    .order_by(Link.created_at.desc(), Link.id.desc())
                    .offset(offset)
                    .limit(per_page)
                )
            ).scalars().all()
        )
        series_14d = await get_daily_clicks_for_links(db, page_link_ids, days=DELTA_WINDOW_DAYS)
        current_week = sum(sum(points[7:]) for points in series_14d.values())
        previous_week = sum(sum(points[:7]) for points in series_14d.values())
        context["summary"]["clicks_7d"] = current_week
        context["trend"] = _trend_label(current_week, previous_week)
        if sort == "clicks":
            entries.sort(key=lambda item: item["clicks"], reverse=True)
        context["links"] = entries
        context["page"] = page
        context["pagination"] = {
            "page": page,
            "total_pages": total_pages,
            "total": total_links,
            "start": offset + 1 if total_links else 0,
            "end": min(offset + per_page, total_links),
            "has_prev": page > 1,
            "has_next": page < total_pages,
        }

        top_pool, _ = await _links_with_counts(
            db, base_url, limit=TOP_LINKS_POOL, with_sparks=False
        )
        context["top_links"] = sorted(
            top_pool, key=lambda item: item["clicks"], reverse=True
        )[:5]

        dev_items, dev_total = await get_device_breakdown_global(
            db, days=DEVICE_PANEL_DAYS, exclude_bots=not bots
        )
        context["devices"] = _device_panel(dev_items, dev_total)
        context["devices_total"] = dev_total

        context["unique_visitors"] = await count_unique_clicks_global(db)
        activity_rows = await get_recent_clicks_global(db, link_ids=None, limit=ACTIVITY_ROWS)
        context["activity"] = _activity_view(activity_rows)
        context["activity_total"] = len(context["activity"])

        if code:
            link = await db.scalar(select(Link).where(Link.code == code))
            if link is not None:
                total = int(
                    await db.scalar(
                        select(func.count()).select_from(Click).where(Click.link_id == link.id)
                    )
                    or 0
                )
                context["selected"] = {
                    "code": link.code,
                    "short_url": _short_url(base_url, link.code),
                    "original_url": link.original_url,
                    "total_clicks": total,
                    "created_abs": _fmt_abs(link.created_at),
                    "expiry": _expiry_view(link.expires_at),
                }
    except Exception:  # noqa: BLE001 — the panel must render even when the DB is down
        context["error"] = "Database unavailable — please try again in a moment."

    return _templates.TemplateResponse(
        request=request, name="dashboard.html", context=context
    )


def _stats_chart_bars(points: list[int]) -> list[dict]:
    """Render data for the public stats page's 14-day bar chart."""
    if not points:
        return []
    max_value = max(points)
    today = datetime.now(UTC).date()
    bars = []
    for index, value in enumerate(points):
        day = today - timedelta(days=len(points) - 1 - index)
        pct = round(value * 100 / max_value) if max_value else 0
        bars.append({"date": day.isoformat(), "clicks": value, "pct": max(pct, 6 if value else 0)})
    return bars


@router.get("/s/{code}", response_class=HTMLResponse, include_in_schema=False)
async def public_stats_page(
    request: Request,
    code: str,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Public, shareable stats page for one short link — no API key needed.

    Privacy posture mirrors the owner APIs: referrers are reduced to hosts,
    IP hashes are never shown. Unknown/malformed codes render a styled 404.
    """
    base_url = str(request.base_url).rstrip("/")
    context: dict = {
        "version": __version__,
        "not_found": False,
        "link": None,
        "total_clicks": 0,
        "unique_clicks": 0,
        "bars": [],
        "chart_days": STATS_PAGE_DAYS,
        "devices": [],
        "devices_total": 0,
        "referrers": [],
        "recent": [],
        "stats_url": f"{base_url}/s/{code}",
    }
    status_code = 200
    if not PUBLIC_CODE_PATTERN.match(code):
        context["not_found"] = True
        return _templates.TemplateResponse(
            request=request, name="stats.html", context=context, status_code=404
        )
    try:
        link = await db.scalar(select(Link).where(Link.code == code))
        if link is None:
            context["not_found"] = True
            status_code = 404
        else:
            total = await count_clicks(db, link.id)
            series = await get_daily_clicks_for_links(db, [link.id], days=STATS_PAGE_DAYS)
            points = series.get(link.id, [0] * STATS_PAGE_DAYS)
            dev_items = await get_device_breakdown(db, link)
            dev_total = sum(clicks for _, clicks in dev_items)
            refs = await get_top_referrers(db, link, limit=STATS_PAGE_REFERRERS)
            recent_rows = await get_recent_clicks(db, link, limit=STATS_PAGE_RECENT)
            context.update(
                {
                    "link": {
                        "code": link.code,
                        "short_url": _short_url(base_url, link.code),
                        "original_url": link.original_url,
                        "dest_host": _referrer_host(link.original_url) or link.original_url[:64],
                        "created_abs": _fmt_abs(link.created_at),
                        "expiry": _expiry_view(link.expires_at),
                        "utm": link.utm_template,
                    },
                    "total_clicks": total,
                    "unique_clicks": await count_unique_clicks(db, link.id),
                    "bars": _stats_chart_bars(points),
                    "devices": _device_panel(dev_items, dev_total),
                    "devices_total": dev_total,
                    "referrers": [
                        {
                            "source": source or "direct",
                            "clicks": clicks,
                            "host": _referrer_host(source) or "direct",
                        }
                        for source, clicks in refs
                    ],
                    "recent": [
                        {
                            "when": _fmt_rel(click.clicked_at),
                            "when_abs": _fmt_abs(click.clicked_at),
                            "device": click.device or "other",
                            "referrer_host": _referrer_host(click.referrer),
                        }
                        for click in recent_rows
                    ],
                }
            )
    except Exception:  # noqa: BLE001 — degrade gracefully when the DB is down
        context["error"] = "Database unavailable — please try again in a moment."
    return _templates.TemplateResponse(
        request=request, name="stats.html", context=context, status_code=status_code
    )
