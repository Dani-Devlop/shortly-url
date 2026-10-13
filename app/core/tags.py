"""Tag normalisation for link organisation (case/whitespace tolerant)."""

import re

TAG_MAX = 6  # tags per link
TAG_MIN_LEN = 2
TAG_MAX_LEN = 24
_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def normalize_tags(raw: list[str] | None) -> list[str]:
    """Normalise a list of raw tag strings into a clean, deduped list.

    Rules:
    - trim, lowercase, collapse inner whitespace runs to ``-``
    - drop empties; dedupe preserving first-seen order
    - keep 2–24 chars matching ``[a-z0-9][a-z0-9_-]*``
    - at most :data:`TAG_MAX` tags per link

    Raises ``ValueError`` with a client-safe message on invalid input.
    """
    if not raw:
        return []
    if not isinstance(raw, list) or any(not isinstance(t, str) for t in raw):
        raise ValueError("tags must be a list of strings")
    if len(raw) > TAG_MAX:
        raise ValueError(f"at most {TAG_MAX} tags per link")
    seen: list[str] = []
    for item in raw:
        tag = re.sub(r"\s+", "-", item.strip().lower())
        if not tag:
            continue
        if len(tag) < TAG_MIN_LEN or len(tag) > TAG_MAX_LEN:
            raise ValueError(
                f"tag '{item[:32]}' must be {TAG_MIN_LEN}-{TAG_MAX_LEN} characters"
            )
        if not _TAG_RE.match(tag):
            raise ValueError(
                f"tag '{item[:32]}' may only contain letters, digits, '-', '_' "
                "(spaces become '-')"
            )
        if tag not in seen:
            seen.append(tag)
    return seen


def tag_hue(tag: str) -> int:
    """Deterministic hue (0–359) for a tag — used for chip colouring."""
    acc = 0
    for ch in tag:
        acc = (acc * 31 + ord(ch)) % 360
    return acc
