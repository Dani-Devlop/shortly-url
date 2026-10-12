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
from PIL import Image

from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.db.session import get_session_factory
from app.services.click_service import click_task
from app.services.redirect_service import apply_template, resolve_target

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

    # Query-param forwarding + UTM template: the link's campaign params act as
    # fallbacks; explicit short-URL params win, destination params beat the template.
    target = apply_template(payload["url"], request.url.query, payload.get("utm"))

    return RedirectResponse(
        url=target,
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
    size: int = Query(default=256, ge=64, le=1024, description="Image width/height in pixels (SVG and PNG)."),
) -> Response:
    """QR code pointing at the short URL (public, cacheable).

    ``format=svg`` (default) returns vector SVG; ``format=png`` a raster image.
    ``size`` scales the rendered image (64–1024 px, default 256).
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
        image = qr.make_image(image_factory=qrcode.image.pil.PilImage).get_image()
        resized = image.resize((size, size), Image.NEAREST)  # crisp modules, exact pixels
        resized.save(buffer, format="PNG")
        media_type = "image/png"
    else:
        image = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
        svg_text = image.to_string().decode("utf-8")
        # Normalise the root <svg> width/height to the requested size (px).
        svg_text = re.sub(
            r'(<svg[^>]*?)\swidth="[^"]*"\sheight="[^"]*"',
            rf'\1 width="{size}" height="{size}"',
            svg_text,
            count=1,
        )
        buffer.write(svg_text.encode("utf-8"))
        media_type = "image/svg+xml"

    return Response(
        content=buffer.getvalue(),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
