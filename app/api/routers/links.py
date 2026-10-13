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
from app.models import Link, LinkTag, User
from app.schemas.link import (
    BulkActionItem,
    BulkActionOut,
    BulkActionRequest,
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
    set_archived,
    update_link,
)
from app.services.stats_service import (
    click_counts_for_links,
    count_unique_clicks,
    get_daily_clicks_for_links,
    get_device_breakdown,
    get_recent_clicks,
    get_referrer_device_stats,
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
        utm_template=link.utm_template,
        tags=link.tags,
        total_clicks=total_clicks,
        archived=link.archived,
        archived_at=link.archived_at,
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
        utm_template=payload.utm_template,
        tags=payload.tags,
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
        [
            "code", "short_url", "original_url", "total_clicks",
            "created_at", "expires_at", "tags", "archived",
        ]
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
                ";".join(link.tags),
                "yes" if link.archived else "no",
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
    tag: str | None = Query(
        default=None,
        max_length=32,
        description="Only return links carrying this tag (case-insensitive).",
    ),
    link_status: str = Query(
        default="active",
        alias="status",
        pattern="^(active|archived|all)$",
        description=(
            "Filter by archive state: active (default), archived, or all."
        ),
    ),
) -> LinkPageOut:
    """Paginated list of the authenticated user's links, newest first.

    Returns ``{items, total, limit, offset, status}`` — ``total`` counts the
    matching links so clients can compute page counts. Pass ``?tag=`` to
    filter by tag and ``?status=archived|all`` to include soft-deleted links.
    """
    base = select(Link).where(Link.owner_id == user.id)
    if link_status == "active":
        base = base.where(Link.archived.is_(False))
    elif link_status == "archived":
        base = base.where(Link.archived.is_(True))
    if tag:
        base = base.where(
            Link.id.in_(
                select(LinkTag.link_id).where(
                    LinkTag.tag == tag.strip().lower()
                )
            )
        )
    total = int(
        await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    )
    rows = (
        await db.execute(
            base.order_by(Link.created_at.desc(), Link.id.desc())
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
        status=link_status,
    )


async def _owned_link(db: AsyncSession, code: str, user: User) -> Link:
    link = await get_link_by_code(db, code)
    if link is None or link.owner_id != user.id:
        # 404 (not 403) to avoid leaking the existence of other users' links.
        raise NotFoundError(f"Short code '{code}' does not exist")
    return link


async def _apply_bulk_action(
    db: AsyncSession,
    user: User,
    action: str,
    codes: list[str],
) -> BulkActionOut:
    """Shared body of the bulk archive/restore/delete endpoints."""
    results: list[BulkActionItem] = []
    updated = 0
    for code in codes:
        link = await get_link_by_code(db, code)
        if link is None or link.owner_id != user.id:
            results.append(BulkActionItem(code=code, status="not_found"))
            continue
        if action == "delete":
            await delete_link(db, link)
        else:
            await set_archived(db, link, archived=(action == "archive"))
        results.append(BulkActionItem(code=code, status="ok"))
        updated += 1
    return BulkActionOut(
        action=action,
        updated=updated,
        not_found=len(results) - updated,
        results=results,
    )


@router.post("/links/bulk-action", response_model=BulkActionOut)
async def bulk_action(
    payload: BulkActionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BulkActionOut:
    """Archive, restore or delete up to 100 links in one call.

    Unknown codes (and codes owned by someone else) are reported per-code as
    ``not_found`` instead of failing the request; owned codes are processed
    independently, so a failure never blocks the rest of the batch.
    """
    return await _apply_bulk_action(db, user, payload.action, payload.codes)


@router.post("/links/{code}/archive", response_model=LinkOut)
async def archive_link(
    code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkOut:
    """Soft-delete a link: stats stay readable but ``GET /{code}`` returns 410.

    The short URL can be reinstated anytime with :func:`restore_link`.
    Idempotent — archiving an archived link returns it unchanged.
    """
    link = await _owned_link(db, code, user)
    link = await set_archived(db, link, archived=True)
    return _to_out(link, await get_total_clicks(db, link))


@router.post("/links/{code}/restore", response_model=LinkOut)
async def restore_link(
    code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkOut:
    """Reinstate an archived link (undo the soft-delete; redirects work again).

    Idempotent — restoring an active link returns it unchanged.
    """
    link = await _owned_link(db, code, user)
    link = await set_archived(db, link, archived=False)
    return _to_out(link, await get_total_clicks(db, link))


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
    referrer_rows, _referrer_total = await get_referrer_device_stats(
        db, link, days=None, limit=5
    )
    referrers = [
        ReferrerStat(source=source or "direct", clicks=clicks, devices=devices)
        for source, clicks, devices in referrer_rows
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
        utm_template=link.utm_template,
        tags=link.tags,
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
    """Update a link's destination, expiry, UTM template and/or tags (cache is invalidated).

    Send ``{"expires_at": null}`` to remove an expiry, ``{"utm_template": null}``
    to clear the campaign template, and ``{"tags": []}`` to clear all tags
    (``tags`` replaces the whole set whenever present).
    """
    link = await _owned_link(db, code, user)
    provided = payload.model_fields_set
    new_url = str(payload.url) if payload.url is not None else None
    expiry = (
        payload.expires_at if "expires_at" in provided else LinkExpiryUnset()
    )
    utm = payload.utm_template if "utm_template" in provided else LinkExpiryUnset()
    tags = payload.tags if "tags" in provided else LinkExpiryUnset()
    link = await update_link(
        db, link, new_url=new_url, expires_at=expiry, utm_template=utm, tags=tags
    )
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
