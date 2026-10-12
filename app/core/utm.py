"""UTM campaign templates — validation, normalisation and redirect merging.

A link may carry a *template* query string (e.g.
``utm_source=newsletter&utm_campaign=launch``). On redirect the template
parameters act as **fallbacks**: explicit params on the short URL win, and
params already present on the destination win over the template.
"""

from urllib.parse import parse_qsl, urlencode

MAX_TEMPLATE_LENGTH = 512
MAX_KEY_LENGTH = 32
MAX_VALUE_LENGTH = 256
_KEY_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
)


def normalize_utm_template(value: str | None) -> str | None:
    """Validate and canonicalise a UTM template query string.

    Returns ``None`` for blank input (meaning "no template"). Raises
    :class:`ValueError` with a human-readable message for invalid templates —
    Pydantic turns that into a 422 response.
    """
    if value is None:
        return None
    cleaned = value.strip().lstrip("?").strip()
    if not cleaned:
        return None

    if "#" in cleaned:
        raise ValueError("utm_template must not contain a fragment ('#')")
    if "://" in cleaned:
        raise ValueError("utm_template must be a query string, not a URL")
    if any(ch.isspace() for ch in cleaned):
        raise ValueError("utm_template must not contain whitespace")

    try:
        pairs = parse_qsl(cleaned, keep_blank_values=True, strict_parsing=False)
    except ValueError as exc:
        raise ValueError("utm_template is not a valid query string") from exc
    if not pairs:
        raise ValueError("utm_template must contain at least one key=value pair")

    for key, val in pairs:
        if not key or not set(key) <= _KEY_CHARS:
            raise ValueError(
                f"invalid parameter name '{key[:32]}' — use letters, digits, '-' or '_'"
            )
        if len(key) > MAX_KEY_LENGTH:
            raise ValueError(f"parameter name too long (max {MAX_KEY_LENGTH} chars)")
        if len(val) > MAX_VALUE_LENGTH:
            raise ValueError(
                f"parameter value for '{key[:32]}' too long (max {MAX_VALUE_LENGTH} chars)"
            )

    normalized = urlencode(pairs)
    if len(normalized) > MAX_TEMPLATE_LENGTH:
        raise ValueError(f"utm_template too long (max {MAX_TEMPLATE_LENGTH} chars)")
    return normalized


def parse_template(template: str | None) -> list[tuple[str, str]]:
    """Parse a stored template into ``(key, value)`` pairs (blank keys dropped)."""
    if not template:
        return []
    try:
        return [(k, v) for k, v in parse_qsl(template, keep_blank_values=True) if k]
    except ValueError:
        return []
