"""Pydantic v2 request/response schemas."""

from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


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

    @model_validator(mode="after")
    def _validate_expiry(self) -> "ShortenRequest":
        self.expires_at = _ensure_future(self.expires_at)
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
    total_clicks: int = 0


class StatsOut(BaseModel):
    code: str
    original_url: str
    total_clicks: int
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

    @model_validator(mode="after")
    def _validate(self) -> "LinkUpdate":
        provided = self.model_fields_set
        if "url" in provided and self.url is None:
            raise ValueError("url cannot be null")
        if not provided & {"url", "expires_at"}:
            raise ValueError("provide at least one of 'url' or 'expires_at'")
        if "expires_at" in provided:
            self.expires_at = _ensure_future(self.expires_at)
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


class LinkPageOut(BaseModel):
    """Paginated envelope for GET /api/links."""

    items: list[LinkOut]
    total: int = Field(description="Total links owned by the user (all pages).")
    limit: int
    offset: int


class SparklineItem(BaseModel):
    code: str
    total_clicks: int
    points: list[int] = Field(
        description="Click counts per day, oldest → newest, zero-filled.",
    )


class SparklinesOut(BaseModel):
    window_days: int
    items: list[SparklineItem]
