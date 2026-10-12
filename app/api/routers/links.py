"""Link management endpoints: shorten, bulk shorten, list, detail, update,
delete, CSV export."""

import csv
import io
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.rate_limit import enforce_rate_limit
from app.core.security import hash_identifier
from app.db.session import get_db
from app.models import Link, User
from app.schemas.link import (
    BulkResultItem,
    BulkShortenOut,
    BulkShortenRequest,
    DeviceStat,
    LinkDetailOut,
    LinkOut,
    LinkPageOut,
    LinkUpdate,
    RecentClickOut,
    ReferrerStat,
    ShortenRequest,
)
from app.services.link_service import (
    LinkExpiryUnset,
    create_link,
    delete_link,
    get_link_by_code,
    update_link,
)
from app.services.stats_service import (
    click_counts_for_links,
    count_unique_clicks,
    get_daily_clicks_for_links,
    get_device_breakdown,
    get_recent_clicks,
    get_top_referrers,
    get_total_clicks,
)

router = APIRouter(prefix="/api", tags=["links"])
settings = get_settings()

EXPORT_LINKS_CAP = 5000
EXPORT_CLICKS_CAP = 10_000


def _to_out(link: Link, total_clicks: int) -> LinkOut:
    return LinkOut(
        id=link.id,
        code=link.code,
        short_url=f"{settings.base_url.rstrip('/')}/{link.code}",
        original_url=link.original_url,
        created_at=link.created_at,
        expires_at=link.expires_at,
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
    budget = await enforce_rate_limit(f"shorten:{hash_identifier(user.api_key)}")
    if budget:
        response.headers.update(budget.headers())
    link = await create_link(
        db,
        original_url=str(payload.url),
        owner_id=user.id,
        custom_code=payload.custom_code,
        expires_at=payload.expires_at,
    )
    out = _to_out(link, await get_total_clicks(db, link))
    response.headers["Location"] = out.short_url
    return out


@router.post(
    "/shorten/bulk",
    response_model=BulkShortenOut,
    status_code=status.HTTP_201_CREATED,
)
async def shorten_bulk(
    payload: BulkShortenRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BulkShortenOut:
    """Shorten 1–25 URLs in one call. Each item is independent: duplicates and
    errors are reported per-item instead of failing the whole request."""
    await enforce_rate_limit(
        f"shorten:{hash_identifier(user.api_key)}", cost=len(payload.urls)
    )  # bulk consumes its full cost up-front; no useful remaining value to advertise
    results: list[BulkResultItem] = []
    for item in payload.urls:
        raw_url = str(item)
        try:
            existing = await db.scalar(
                select(Link).where(
                    Link.owner_id == user.id, Link.original_url == raw_url
                )
            )
            if existing is not None:
                results.append(
                    BulkResultItem(
                        url=raw_url,
                        status="duplicate",
                        code=existing.code,
                        short_url=f"{settings.base_url.rstrip('/')}/{existing.code}",
                    )
                )
                continue
            link = await create_link(db, original_url=raw_url, owner_id=user.id)
            results.append(
                BulkResultItem(
                    url=raw_url,
                    status="created",
                    code=link.code,
                    short_url=f"{settings.base_url.rstrip('/')}/{link.code}",
                )
            )
        except Exception as exc:  # noqa: BLE001 — per-item isolation
            await db.rollback()  # keep the session usable for the remaining items
            message = getattr(exc, "message", None) or str(exc)
            results.append(BulkResultItem(url=raw_url, status="error", error=str(message)))
    created = sum(1 for r in results if r.status == "created")
    duplicate = sum(1 for r in results if r.status == "duplicate")
    return BulkShortenOut(
        results=results,
        created=created,
        duplicate=duplicate,
        errors=len(results) - created - duplicate,
    )


@router.get("/links/export", response_class=Response, include_in_schema=False)
async def export_links_csv(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """CSV download of the authenticated user's links (click counts included)."""
    # NOTE: registered before /links/{code} so "export" is never read as a code.
    rows = (
        await db.execute(
            select(Link)
            .where(Link.owner_id == user.id)
            .order_by(Link.created_at.desc(), Link.id.desc())
            .limit(EXPORT_LINKS_CAP)
        )
    ).scalars().all()
    counts = await click_counts_for_links(db, [link.id for link in rows])

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        ["code", "short_url", "original_url", "total_clicks", "created_at", "expires_at"]
    )
    for link in rows:
        writer.writerow(
            [
                link.code,
                f"{settings.base_url.rstrip('/')}/{link.code}",
                link.original_url,
                counts.get(link.id, 0),
                link.created_at.isoformat() if link.created_at else "",
                link.expires_at.isoformat() if link.expires_at else "",
            ]
        )
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="shortly-links-{stamp}.csv"'
        },
    )


@router.get("/links", response_model=LinkPageOut)
async def list_links(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> LinkPageOut:
    """Paginated list of the authenticated user's links, newest first.

    Returns ``{items, total, limit, offset}`` — ``total`` counts all the
    user's links so clients can compute page counts.
    """
    total = int(
        await db.scalar(
            select(func.count()).select_from(Link).where(Link.owner_id == user.id)
        )
        or 0
    )
    rows = (
        await db.execute(
            select(Link)
            .where(Link.owner_id == user.id)
            .order_by(Link.created_at.desc(), Link.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    counts = await click_counts_for_links(db, [link.id for link in rows])
    return LinkPageOut(
        items=[_to_out(link, counts.get(link.id, 0)) for link in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


async def _owned_link(db: AsyncSession, code: str, user: User) -> Link:
    link = await get_link_by_code(db, code)
    if link is None or link.owner_id != user.id:
        # 404 (not 403) to avoid leaking the existence of other users' links.
        raise NotFoundError(f"Short code '{code}' does not exist")
    return link


@router.get("/links/{code}", response_model=LinkDetailOut)
async def link_detail(
    code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkDetailOut:
    """Full detail for one of the user's links: the 20 most recent clicks,
    the all-time top traffic sources and device mix, unique visitors and a
    zero-filled 14-day daily series (for the dashboard insights chart)."""
    link = await _owned_link(db, code, user)
    recent = [
        RecentClickOut(
            clicked_at=click.clicked_at,
            ip_hash=click.ip_hash[:12] if click.ip_hash else None,
            user_agent=click.user_agent,
            referrer=click.referrer,
            device=click.device or "other",
        )
        for click in await get_recent_clicks(db, link, limit=20)
    ]
    referrers = [
        ReferrerStat(source=source or "direct", clicks=clicks)
        for source, clicks in await get_top_referrers(db, link, limit=5)
    ]
    devices = [
        DeviceStat(device=device, clicks=clicks)
        for device, clicks in await get_device_breakdown(db, link)
    ]
    daily_14d = (await get_daily_clicks_for_links(db, [link.id], days=14)).get(
        link.id, [0] * 14
    )
    return LinkDetailOut(
        id=link.id,
        code=link.code,
        short_url=f"{settings.base_url.rstrip('/')}/{link.code}",
        original_url=link.original_url,
        created_at=link.created_at,
        expires_at=link.expires_at,
        total_clicks=await get_total_clicks(db, link),
        unique_clicks=await count_unique_clicks(db, link.id),
        recent_clicks=recent,
        top_referrers=referrers,
        device_breakdown=devices,
        daily_14d=daily_14d,
    )


@router.patch("/links/{code}", response_model=LinkOut)
async def update_link_fields(
    code: str,
    payload: LinkUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkOut:
    """Update a link's destination and/or expiry (cache is invalidated).

    Send ``{"expires_at": null}`` to remove an expiry.
    """
    link = await _owned_link(db, code, user)
    provided = payload.model_fields_set
    new_url = str(payload.url) if payload.url is not None else None
    expiry = (
        payload.expires_at if "expires_at" in provided else LinkExpiryUnset()
    )
    link = await update_link(db, link, new_url=new_url, expires_at=expiry)
    return _to_out(link, await get_total_clicks(db, link))


@router.delete("/links/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link_by_code(
    code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a link owned by the authenticated user (cascades click rows)."""
    link = await _owned_link(db, code, user)
    await delete_link(db, link)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
