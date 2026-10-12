"""HTML dashboard at ``/`` — recent links + click counts + per-code lookup."""

import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import Click, Link

router = APIRouter(tags=["pages"])

_templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "..", "..", "templates")
)


def _fmt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    return dt.strftime("%Y-%m-%d %H:%M")


async def _summary(db: AsyncSession) -> dict:
    total_links = int(
        await db.scalar(select(func.count()).select_from(Link)) or 0
    )
    total_clicks = int(
        await db.scalar(select(func.count()).select_from(Click)) or 0
    )
    return {"total_links": total_links, "total_clicks": total_clicks}


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(
    request: Request,
    code: str | None = Query(default=None, max_length=32),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    context: dict = {
        "summary": {"total_links": 0, "total_clicks": 0},
        "links": [],
        "lookup": code or "",
        "selected": None,
        "error": None,
    }
    try:
        context["summary"] = await _summary(db)

        recent = (
            await db.execute(
                select(Link).order_by(Link.created_at.desc(), Link.id.desc()).limit(50)
            )
        ).scalars().all()

        counts: dict[int, int] = {}
        if recent:
            rows = await db.execute(
                select(Click.link_id, func.count())
                .where(Click.link_id.in_([link.id for link in recent]))
                .group_by(Click.link_id)
            )
            counts = {int(link_id): int(n) for link_id, n in rows.all()}

        context["links"] = [
            {
                "code": link.code,
                "original_url": link.original_url,
                "clicks": counts.get(link.id, 0),
                "created_at": _fmt(link.created_at),
            }
            for link in recent
        ]

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
                    "original_url": link.original_url,
                    "total_clicks": total,
                    "created_at": _fmt(link.created_at),
                }
    except Exception:  # noqa: BLE001 — the panel must render even when the DB is down
        context["error"] = "Database unavailable — please try again in a moment."

    return _templates.TemplateResponse(
        request=request, name="dashboard.html", context=context
    )
