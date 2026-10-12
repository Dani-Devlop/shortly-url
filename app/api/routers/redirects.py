"""Public redirect endpoint — the hot path (Redis cache + background click tracking)
plus the QR-code view for a short link (SVG or PNG).
"""

import io
import re

import qrcode
import qrcode.image.pil  # noqa: F401 — registers the PIL image factory
import qrcode.image.svg
from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse, Response

from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.db.session import get_session_factory
from app.services.click_service import click_task
from app.services.redirect_service import resolve_target

router = APIRouter(tags=["redirect"])

# Strict allow-list for short codes: blocks traversal/SQLi/XSS payloads up-front.
CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@router.get("/{code}", include_in_schema=False)
async def redirect_by_code(
    code: str,
    request: Request,
) -> RedirectResponse:
    if not CODE_PATTERN.match(code):
        raise NotFoundError(f"Short code '{code}' does not exist")

    # Short-lived explicit session: fully released *before* the response (and
    # therefore the background click task) runs — no pool slot is held across
    # the redirect.
    async with get_session_factory()() as db:
        payload, cache_hit = await resolve_target(db, code)

    return RedirectResponse(
        url=payload["url"],
        status_code=302,  # 302 (not 301) so browsers don't cache past analytics
        headers={
            "Cache-Control": "no-store",
            "X-Robots-Tag": "noindex",
            "X-Cache": "HIT" if cache_hit else "MISS",
        },
        background=click_task(
            link_id=int(payload["id"]),
            code=code,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            referrer=request.headers.get("referer"),
        ),
    )


@router.get("/{code}/qr", include_in_schema=False)
async def qr_code(
    code: str,
    format: str = Query(default="svg", pattern="^(svg|png)$"),
) -> Response:
    """QR code pointing at the short URL (public, cacheable).

    ``format=svg`` (default) returns vector SVG; ``format=png`` a raster image.
    """
    if not CODE_PATTERN.match(code):
        raise NotFoundError(f"Short code '{code}' does not exist")

    async with get_session_factory()() as db:
        payload, _ = await resolve_target(db, code)
    short_url = f"{get_settings().base_url.rstrip('/')}/{code}"

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=12, border=2)
    qr.add_data(short_url)
    qr.make(fit=True)
    buffer = io.BytesIO()
    if format == "png":
        qr.make_image(image_factory=qrcode.image.pil.PilImage).save(buffer, format="PNG")
        media_type = "image/png"
    else:
        qr.make_image(image_factory=qrcode.image.svg.SvgPathImage).save(buffer)
        media_type = "image/svg+xml"

    return Response(
        content=buffer.getvalue(),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
