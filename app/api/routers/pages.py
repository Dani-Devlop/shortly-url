"""HTML dashboard at ``/`` — recent links, click counts, per-code lookup,
top links and client-side admin actions (copy / QR / edit / delete).
"""

import math
import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.db.session import get_db
from app.models import Click, Link
from app.services.stats_service import get_daily_clicks_for_links

router = APIRouter(tags=["pages"])

_templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "..", "..", "templates")
)

SPARKLINE_DAYS = 7
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
        entries, clicks_7d = await _links_with_counts(
            db, base_url, limit=per_page, offset=offset
        )
        context["summary"]["clicks_7d"] = clicks_7d
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
