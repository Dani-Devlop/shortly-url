"""Tag management endpoints: rename (with merge) and delete — owner-scoped."""

from fastapi import APIRouter, Depends, Path
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models import Link, LinkTag, User
from app.schemas.link import TagActionOut, TagRenameRequest

router = APIRouter(prefix="/api/tags", tags=["tags"])


async def _owned_tag_links(db: AsyncSession, tag: str, user: User) -> list[int]:
    """IDs of the caller's links carrying ``tag`` (empty when unknown)."""
    rows = await db.execute(
        select(LinkTag.link_id)
        .join(Link, Link.id == LinkTag.link_id)
        .where(LinkTag.tag == tag, Link.owner_id == user.id)
    )
    return [int(link_id) for (link_id,) in rows.all()]


@router.post("/rename", response_model=TagActionOut)
async def rename_tag(
    payload: TagRenameRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TagActionOut:
    """Rename a tag across all of the caller's links.

    If a link already carries the target tag, the source row is removed and
    the link counts as *merged* (tag sets never grow, so the 6-tag cap holds).
    Unknown source tags → 404. Only the caller's links are touched.
    """
    link_ids = await _owned_tag_links(db, payload.source, user)
    if not link_ids:
        raise NotFoundError(f"Tag '{payload.source}' is not used by any of your links")
    # Links that already have the target: drop the source row (merge).
    merged_rows = await db.execute(
        select(LinkTag.link_id).where(
            LinkTag.tag == payload.target, LinkTag.link_id.in_(link_ids)
        )
    )
    merged_ids = [int(link_id) for (link_id,) in merged_rows.all()]
    if merged_ids:
        await db.execute(
            delete(LinkTag).where(
                LinkTag.tag == payload.source, LinkTag.link_id.in_(merged_ids)
            )
        )
    # Remaining links: rewrite the source tag to the target.
    rewrite_ids = [link_id for link_id in link_ids if link_id not in set(merged_ids)]
    if rewrite_ids:
        await db.execute(
            update(LinkTag)
            .where(LinkTag.tag == payload.source, LinkTag.link_id.in_(rewrite_ids))
            .values(tag=payload.target)
        )
    await db.commit()
    return TagActionOut(
        tag=payload.target,
        links_updated=len(rewrite_ids),
        links_merged=len(merged_ids),
    )


@router.delete("/{tag}", response_model=TagActionOut)
async def delete_tag(
    tag: str = Path(
        ...,
        pattern=r"^[a-z0-9][a-z0-9_-]{1,23}$",
        description="Tag to strip from all of the caller's links.",
    ),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TagActionOut:
    """Remove a tag from every one of the caller's links (links are kept)."""
    link_ids = await _owned_tag_links(db, tag, user)
    if not link_ids:
        raise NotFoundError(f"Tag '{tag}' is not used by any of your links")
    result = await db.execute(
        delete(LinkTag).where(LinkTag.tag == tag, LinkTag.link_id.in_(link_ids))
    )
    await db.commit()
    removed = int(result.rowcount or 0)
    return TagActionOut(tag=tag, links_updated=0, links_removed=removed)
