"""Pydantic v2 request/response schemas."""

import re
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.core.tags import normalize_tags
from app.core.utm import normalize_utm_template

CODE_FIELD_PATTERN = r"^[A-Za-z0-9_-]{1,32}$"


def _ensure_future(value: datetime | None) -> datetime | None:
    """Reject expiry timestamps that are already in the past (1s clock slack)."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    if value <= datetime.now(UTC) + timedelta(seconds=1):
        raise ValueError("expires_at must be in the future")
    return value


class ShortenRequest(BaseModel):
    url: HttpUrl = Field(
        ...,
        examples=["https://example.com/some/long/path"],
        description="Original URL to shorten (http/https, max 2048 chars).",
    )
    custom_code: str | None = Field(
        default=None,
        min_length=4,
        max_length=16,
        pattern=r"^[A-Za-z0-9_-]+$",
        examples=["my-link"],
        description="Optional custom alias: 4–16 chars, letters/digits/-/_ only.",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Optional expiry timestamp (ISO 8601). Expired links return 410 Gone.",
    )
    utm_template: str | None = Field(
        default=None,
        max_length=512,
        examples=["utm_source=newsletter&utm_campaign=launch"],
        description=(
            "Optional default UTM query params appended on redirect. Explicit "
            "params on the short URL and on the destination take precedence."
        ),
    )
    tags: list[str] = Field(
        default_factory=list,
        max_length=6,
        examples=[["docs", "launch"]],
        description=(
            "Optional organisation tags (max 6): trimmed/lowercased, 2–24 chars, "
            "letters/digits/-/_ — spaces become '-'. Filter lists with ?tag=."
        ),
    )

    @model_validator(mode="after")
    def _validate(self) -> "ShortenRequest":
        self.expires_at = _ensure_future(self.expires_at)
        try:
            self.utm_template = normalize_utm_template(self.utm_template)
            self.tags = normalize_tags(self.tags)
        except ValueError as exc:
            raise ValueError(str(exc)) from None
        return self


class BulkShortenRequest(BaseModel):
    urls: list[HttpUrl] = Field(
        ...,
        min_length=1,
        max_length=25,
        examples=[["https://example.com/a", "https://example.com/b"]],
        description="1–25 URLs to shorten in one call.",
    )


class BulkResultItem(BaseModel):
    url: str
    status: str  # created | duplicate | error
    code: str | None = None
    short_url: str | None = None
    error: str | None = None


class BulkShortenOut(BaseModel):
    results: list[BulkResultItem]
    created: int
    duplicate: int
    errors: int


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    short_url: str
    original_url: str
    created_at: datetime
    expires_at: datetime | None = None
    utm_template: str | None = Field(
        default=None,
        description="Default UTM params appended on redirect (campaign template).",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Organisation tags (alphabetical, lowercased).",
    )
    total_clicks: int = 0
    archived: bool = Field(
        default=False,
        description="Soft-deleted: stats stay readable but the short URL returns 410.",
    )
    archived_at: datetime | None = Field(
        default=None,
        description="When the link was archived (null while active).",
    )


class BulkActionRequest(BaseModel):
    """Body for POST /api/links/bulk-action."""

    action: str = Field(
        ...,
        pattern="^(archive|restore|delete)$",
        description="What to do with every listed code.",
    )
    codes: list[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        examples=[["repo", "pydocs"]],
        description="1–100 short codes owned by the authenticated user.",
    )

    @model_validator(mode="after")
    def _validate(self) -> "BulkActionRequest":
        pattern = re.compile(CODE_FIELD_PATTERN)
        bad = [c for c in self.codes if not pattern.match(c)]
        if bad:
            raise ValueError(f"invalid short code(s): {', '.join(bad[:5])}")
        return self


class BulkActionItem(BaseModel):
    """Per-code result of a bulk action."""

    code: str
    status: str = Field(description="ok | not_found")


class BulkActionOut(BaseModel):
    """Envelope for POST /api/links/bulk-action."""

    action: str
    updated: int = Field(description="Codes the action was applied to.")
    not_found: int = Field(description="Codes that don't exist or belong to someone else.")
    results: list[BulkActionItem]


class StatsOut(BaseModel):
    code: str
    original_url: str
    total_clicks: int
    unique_clicks: int = Field(
        default=0,
        description="Distinct visitors (unique ip_hash) across all clicks.",
    )
    created_at: datetime


class DailyStatPoint(BaseModel):
    date: date
    clicks: int


class DailyStats(BaseModel):
    code: str
    window_days: int
    total: int
    items: list[DailyStatPoint]


class LinkUpdate(BaseModel):
    url: HttpUrl | None = Field(
        default=None,
        examples=["https://example.com/new/destination"],
        description="New destination URL (http/https, max 2048 chars).",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="New expiry timestamp. Send null to remove the expiry."
    )
    utm_template: str | None = Field(
        default=None,
        max_length=512,
        description="New UTM template. Send null to clear it.",
    )
    tags: list[str] | None = Field(
        default=None,
        max_length=6,
        description=(
            "Replaces the whole tag set. Send [] (or null, explicitly) to clear "
            "all tags; omit the field to leave tags untouched."
        ),
    )

    @model_validator(mode="after")
    def _validate(self) -> "LinkUpdate":
        provided = self.model_fields_set
        if "url" in provided and self.url is None:
            raise ValueError("url cannot be null")
        if not provided & {"url", "expires_at", "utm_template", "tags"}:
            raise ValueError(
                "provide at least one of 'url', 'expires_at', 'utm_template' or 'tags'"
            )
        if "expires_at" in provided:
            self.expires_at = _ensure_future(self.expires_at)
        if "utm_template" in provided:
            try:
                self.utm_template = normalize_utm_template(self.utm_template)
            except ValueError as exc:
                raise ValueError(str(exc)) from None
        if "tags" in provided:
            try:
                self.tags = normalize_tags(self.tags)
            except ValueError as exc:
                raise ValueError(str(exc)) from None
        return self


class RecentClickOut(BaseModel):
    clicked_at: datetime
    ip_hash: str | None = None
    user_agent: str | None = None
    referrer: str | None = Field(
        default=None,
        description="Referer of the click; null means direct (no referrer).",
    )
    device: str = Field(
        default="other",
        description="Coarse device class: desktop | mobile | tablet | bot | other.",
    )


class ReferrerStat(BaseModel):
    source: str = Field(description="Referrer URL, or 'direct' when the header was absent.")
    clicks: int


class DeviceStat(BaseModel):
    device: str = Field(description="desktop | mobile | tablet | bot | other")
    clicks: int


class DeviceBreakdownOut(BaseModel):
    """Envelope for GET /api/stats/devices."""

    window_days: int
    total: int = Field(description="Clicks recorded in the window across all devices.")
    items: list[DeviceStat]


class ReferrerWindowOut(BaseModel):
    """Envelope for GET /api/stats/{code}/referrers."""

    code: str
    window_days: int
    total: int = Field(description="Clicks recorded in the window (all sources).")
    items: list[ReferrerStat]


class LinkDetailOut(LinkOut):
    recent_clicks: list[RecentClickOut] = Field(
        default_factory=list,
        description="Most recent clicks (max 20), newest first.",
    )
    top_referrers: list[ReferrerStat] = Field(
        default_factory=list,
        description="Traffic sources ranked by clicks (max 5).",
    )
    device_breakdown: list[DeviceStat] = Field(
        default_factory=list,
        description="All-time device mix for this link, ranked by clicks.",
    )
    unique_clicks: int = Field(
        default=0,
        description="Distinct visitors (unique ip_hash) across all clicks.",
    )
    daily_14d: list[int] = Field(
        default_factory=list,
        description="Clicks per day for the last 14 days, oldest → newest, zero-filled.",
    )


class LinkPageOut(BaseModel):
    """Paginated envelope for GET /api/links."""

    items: list[LinkOut]
    total: int = Field(description="Total matching links owned by the user (all pages).")
    limit: int
    offset: int
    status: str = Field(
        default="active",
        description="Status filter applied: active | archived | all.",
    )


class SparklineItem(BaseModel):
    code: str
    total_clicks: int
    points: list[int] = Field(
        description="Click counts per day, oldest → newest, zero-filled.",
    )


class SparklinesOut(BaseModel):
    window_days: int
    items: list[SparklineItem]


class HourCell(BaseModel):
    dow: int = Field(ge=0, le=6, description="Day of week, 0=Sunday … 6=Saturday (UTC).")
    hour: int = Field(ge=0, le=23, description="Hour of day 0–23 (UTC).")
    clicks: int


class HoursOut(BaseModel):
    """Envelope for GET /api/stats/{code}/hours — zero-filled 7×24 grid."""

    code: str
    window_days: int
    total: int = Field(description="Clicks recorded in the window (sum of all cells).")
    peak: int = Field(description="Highest single (dow, hour) cell in the window.")
    cells: list[HourCell] = Field(
        description="Exactly 168 cells (7 days × 24 hours), Sunday 00:00 first.",
    )


class ActivityItem(BaseModel):
    """One recent click in the global activity feed."""

    code: str
    clicked_at: datetime
    device: str = Field(description="desktop | mobile | tablet | bot | other")
    referrer_host: str | None = Field(
        default=None,
        description="Host of the referer (privacy-safe); None means direct.",
    )
    ip_hash: str | None = Field(
        default=None, description="Truncated (12 chars) hashed visitor IP."
    )


class ActivityOut(BaseModel):
    """Envelope for GET /api/stats/activity."""

    items: list[ActivityItem]
    limit: int


class TagRollupItem(BaseModel):
    """One tag's aggregated performance."""

    tag: str
    links: int = Field(description="Owner's links carrying this tag (all-time).")
    clicks: int = Field(description="Clicks on those links within the window.")
    unique_visitors: int = Field(
        description="Distinct visitors (unique ip_hash) within the window."
    )


class TagRollupOut(BaseModel):
    """Envelope for GET /api/stats/tags."""

    window_days: int
    total_clicks: int = Field(description="Sum of clicks across returned tags.")
    items: list[TagRollupItem]


class CompareItem(BaseModel):
    """One side of a two-code comparison."""

    code: str
    original_url: str
    total_clicks: int
    unique_clicks: int
    points: list[int] = Field(
        description="Zero-filled daily clicks, oldest → newest, window_days long."
    )


class CompareOut(BaseModel):
    """Envelope for GET /api/stats/compare."""

    window_days: int
    items: list[CompareItem] = Field(description="Exactly two entries, request order.")


class TagRenameRequest(BaseModel):
    """Body for POST /api/tags/rename."""

    model_config = ConfigDict(populate_by_name=True)

    source: str = Field(
        alias="from",
        min_length=1,
        max_length=64,
        description="Current tag name (normalised like link tags: spaces become '-').",
    )
    target: str = Field(
        alias="to",
        min_length=1,
        max_length=64,
        description="New tag name. If a link already carries the target, the two are merged.",
    )

    @model_validator(mode="after")
    def _validate(self) -> "TagRenameRequest":
        from app.core.tags import normalize_tags

        try:
            source = normalize_tags([self.source])
            target = normalize_tags([self.target])
        except ValueError as exc:
            raise ValueError(str(exc)) from None
        if not source or not target:
            raise ValueError("provide both 'from' and 'to' tag names")
        if source[0] == target[0]:
            raise ValueError("'from' and 'to' must be different tags")
        self.source = source[0]
        self.target = target[0]
        return self


class TagActionOut(BaseModel):
    """Response for tag rename / delete operations."""

    tag: str = Field(description="The tag the action targeted (normalised).")
    links_updated: int = Field(
        description="Links whose tag rows were added or rewritten."
    )
    links_merged: int = Field(
        default=0,
        description="Rename only: links that already had the target tag and were deduped.",
    )
    links_removed: int = Field(
        default=0,
        description="Delete only: links the tag was stripped from.",
    )
