"""Public redirect endpoint — the hot path."""

import re

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.services.link_service import get_link_by_code

router = APIRouter(tags=["redirect"])

# Strict allow-list for short codes: blocks traversal/SQLi/XSS payloads up-front.
CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


@router.get("/{code}", include_in_schema=False)
async def redirect_by_code(code: str, db: AsyncSession = Depends(get_db)):
    link = await get_link_by_code(db, code)
    if link is None:
        raise NotFoundError(f"Short code '{code}' does not exist")
    from fastapi.responses import RedirectResponse

    return RedirectResponse(
        url=link.original_url,
        status_code=302,
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"},
    )
