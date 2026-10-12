"""Click analytics endpoints (owner-only)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models import User
from app.schemas.link import DailyStatPoint, DailyStats, StatsOut
from app.services.link_service import get_link_by_code
from app.services.stats_service import get_daily_clicks, get_total_clicks

router = APIRouter(prefix="/api/stats", tags=["stats"])


async def _owned_link(db: AsyncSession, code: str, user: User):
    link = await get_link_by_code(db, code)
    if link is None or link.owner_id != user.id:
        # 404 (not 403) to avoid leaking the existence of other users' links.
        raise NotFoundError(f"Short code '{code}' does not exist")
    return link


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
