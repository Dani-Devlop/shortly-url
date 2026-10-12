"""Pydantic v2 request/response schemas."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


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


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    short_url: str
    original_url: str
    created_at: datetime
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
