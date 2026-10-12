"""Link management endpoints: shorten, list, delete."""

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.rate_limit import enforce_rate_limit
from app.core.security import hash_identifier
from app.db.session import get_db
from app.models import Link, User
from app.schemas.link import LinkOut, ShortenRequest
from app.services.link_service import create_link, delete_link, get_link_by_code
from app.services.stats_service import click_counts_for_links, get_total_clicks

router = APIRouter(prefix="/api", tags=["links"])
settings = get_settings()


def _to_out(link: Link, total_clicks: int) -> LinkOut:
    return LinkOut(
        id=link.id,
        code=link.code,
        short_url=f"{settings.base_url.rstrip('/')}/{link.code}",
        original_url=link.original_url,
        created_at=link.created_at,
        total_clicks=total_clicks,
    )


@router.post("/shorten", response_model=LinkOut, status_code=status.HTTP_201_CREATED)
async def shorten(
    payload: ShortenRequest,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkOut:
    """Create a short link. Re-submitting the same URL returns the existing link."""
    # Redis fixed-window limit per API key (fails open without Redis).
    await enforce_rate_limit(f"shorten:{hash_identifier(user.api_key)}")
    link = await create_link(
        db,
        original_url=str(payload.url),
        owner_id=user.id,
        custom_code=payload.custom_code,
    )
    out = _to_out(link, await get_total_clicks(db, link))
    response.headers["Location"] = out.short_url
    return out


@router.get("/links", response_model=list[LinkOut])
async def list_links(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[LinkOut]:
    """List the authenticated user's links, newest first, with click counts."""
    rows = (
        await db.execute(
            select(Link)
            .where(Link.owner_id == user.id)
            .order_by(Link.created_at.desc(), Link.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    counts = await click_counts_for_links(db, [link.id for link in rows])
    return [_to_out(link, counts.get(link.id, 0)) for link in rows]


@router.delete("/links/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link_by_code(
    code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a link owned by the authenticated user (cascades click rows)."""
    link = await get_link_by_code(db, code)
    if link is None or link.owner_id != user.id:
        raise NotFoundError(f"Short code '{code}' does not exist")
    await delete_link(db, link)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
