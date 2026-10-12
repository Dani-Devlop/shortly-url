"""Redirect resolution with a Redis cache-aside layer, expiry enforcement,
query-param forwarding (``/{code}?x=1`` → destination with ``x=1``) and
per-link UTM campaign templates."""

from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import GoneError, NotFoundError
from app.core.redis import cache_get, cache_set
from app.core.utm import parse_template
from app.services.link_service import get_link_by_code

settings = get_settings()

MAX_URL_LENGTH = 2048  # mirrors the shorten-request URL cap


def merge_query(destination: str, incoming_query: str, max_length: int = MAX_URL_LENGTH) -> str:
    """Append the short-URL's query string onto the destination URL.

    Incoming params win over same-named params already on the destination;
    unknown destination params (UTMs, keys, ...) are preserved. The result is
    inserted before any ``#fragment``. If the merged URL would exceed
    ``max_length`` (or parsing fails), the bare destination is returned.
    """
    if not incoming_query:
        return destination
    try:
        # Drop blank keys ("&=&&" yields ("", "") with keep_blank_values).
        incoming = [(key, value) for key, value in parse_qsl(incoming_query, keep_blank_values=True) if key]
        if not incoming:
            return destination
        parts = urlsplit(destination)
        incoming_keys = {key for key, _ in incoming}
        existing = parse_qsl(parts.query, keep_blank_values=True)
        merged = [(key, value) for key, value in existing if key not in incoming_keys]
        merged.extend(incoming)
        combined = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(merged), parts.fragment)
        )
    except ValueError:  # malformed destination or query — never break the redirect
        return destination
    return combined if len(combined) <= max_length else destination


def apply_template(
    destination: str,
    incoming_query: str,
    template: str | None,
    max_length: int = MAX_URL_LENGTH,
) -> str:
    """Redirect finalisation: UTM template + incoming params + destination.

    Precedence for the same parameter name (highest wins):
    1. incoming short-URL query (per-click intent)
    2. params already on the destination (page owner's intent)
    3. the link's UTM template (campaign defaults)

    Without a template the behaviour is exactly :func:`merge_query`.
    Output order: template keys first (position-stable), then any new
    destination keys, then any new incoming keys. Over-length results fall
    back to the bare destination; parsing errors never break the redirect.
    """
    template_params = parse_template(template)
    if not template_params:
        return merge_query(destination, incoming_query, max_length)
    try:
        parts = urlsplit(destination)
        merged: dict[str, str] = {}
        for key, value in template_params:
            merged.setdefault(key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            if key:
                merged[key] = value
        for key, value in parse_qsl(incoming_query, keep_blank_values=True):
            if key:
                merged[key] = value
        combined = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(list(merged.items())), parts.fragment)
        )
    except ValueError:  # malformed destination — never break the redirect
        return destination
    return combined if len(combined) <= max_length else destination


def _expired(exp: str | None) -> bool:
    """``exp`` is an ISO timestamp string (or None) carried in the cache payload."""
    if not exp:
        return False
    try:
        expiry = datetime.fromisoformat(exp)
    except ValueError:
        return False
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    return datetime.now(UTC) >= expiry


def _as_aware(value: datetime) -> datetime:
    """SQLite may hand back naive datetimes — treat them as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def resolve_target(db: AsyncSession, code: str) -> tuple[dict, bool]:
    """Return ``({"url": ..., "id": ..., "exp": ...}, cache_hit)`` for a short code.

    Cache hit → no DB round-trip. Miss → fetch from PostgreSQL and fill the cache.
    Raises :class:`GoneError` (410) when the link's ``expires_at`` has passed.
    """
    cache_key = f"shortly:short:{code}"
    cached = await cache_get(cache_key)
    if isinstance(cached, dict) and {"url", "id"} <= cached.keys():
        if _expired(cached.get("exp")):
            raise GoneError()
        return cached, True

    link = await get_link_by_code(db, code)
    if link is None:
        raise NotFoundError(f"Short code '{code}' does not exist")
    if link.expires_at is not None and datetime.now(UTC) >= _as_aware(link.expires_at):
        raise GoneError()

    payload = {
        "url": link.original_url,
        "id": link.id,
        "exp": link.expires_at.isoformat() if link.expires_at else None,
        "utm": link.utm_template,
    }
    await cache_set(cache_key, payload, settings.cache_ttl_seconds)
    return payload, False
