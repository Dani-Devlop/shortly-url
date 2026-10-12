"""Device-class analytics: UA classification, click capture, aggregation,
detail breakdown, global /api/stats/devices endpoint, CSV column."""

import csv
import io

import pytest

from app.core.user_agent import classify_user_agent
from tests.conftest import AUTH_HEADERS, SECOND_API_KEY
from tests.helpers import shorten

UAS = {
    "desktop": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "Chrome/126.0 Safari/537.36"
    ),
    "mobile": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/17.5 Mobile/15E148 Safari/604.1"
    ),
    "android": (
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
        "Chrome/126.0 Mobile Safari/537.36"
    ),
    "tablet": (
        "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
        "Version/17.5 Mobile/15E148 Safari/604.1"
    ),
    "bot": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "curl": "curl/8.4.0",
}


class TestClassify:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("desktop", "desktop"),
            ("mobile", "mobile"),
            ("android", "mobile"),
            ("tablet", "tablet"),
            ("bot", "bot"),
            ("curl", "bot"),
        ],
    )
    def test_known_classes(self, name, expected):
        assert classify_user_agent(UAS[name]) == expected

    def test_none_and_empty_and_garbage(self):
        assert classify_user_agent(None) == "other"
        assert classify_user_agent("") == "other"
        assert classify_user_agent("   ") == "other"
        assert classify_user_agent("Mystery/1.0") == "other"

    def test_bot_wins_over_browser_tokens(self):
        # Bots often fake browser tokens — bot detection must take priority.
        ua = "Mozilla/5.0 (compatible; BingPreview/1.0b; MSIE 9.0; Windows NT 6.1)"
        assert classify_user_agent(ua) == "bot"

    def test_tablet_wins_over_mobile_tokens(self):
        # iOS 13+ iPads also request the mobile site ("Mobile" in UA).
        ua = (
            "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) "
            "AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
        )
        assert classify_user_agent(ua) == "tablet"


async def _click(client, code, ua):
    """Follow a short link with a given UA (background click runs inline)."""
    return await client.get(f"/{code}", headers={"User-Agent": ua}, follow_redirects=False)


class TestDeviceCaptureAndApi:
    async def test_click_captures_device(self, client):
        link = await shorten(client)
        await _click(client, link["code"], UAS["mobile"])
        detail = (await client.get(f"/api/links/{link['code']}", headers=AUTH_HEADERS)).json()
        assert detail["recent_clicks"][0]["device"] == "mobile"

    async def test_no_ua_classifies_as_other(self, client):
        # httpx's default UA (python-httpx/x) matches no desktop/mobile pattern.
        link = await shorten(client)
        await client.get(f"/{link['code']}", follow_redirects=False)
        detail = (await client.get(f"/api/links/{link['code']}", headers=AUTH_HEADERS)).json()
        assert detail["recent_clicks"][0]["device"] == "other"
        assert detail["recent_clicks"][0]["user_agent"] == "python-httpx/0.28.1"

    async def test_detail_breakdown_ranked(self, client):
        link = await shorten(client)
        for ua in (UAS["desktop"], UAS["desktop"], UAS["mobile"], UAS["bot"]):
            await _click(client, link["code"], ua)
        detail = (await client.get(f"/api/links/{link['code']}", headers=AUTH_HEADERS)).json()
        devices = {d["device"]: d["clicks"] for d in detail["device_breakdown"]}
        assert devices == {"desktop": 2, "mobile": 1, "bot": 1}
        assert detail["device_breakdown"][0]["device"] == "desktop"  # ranked by clicks

    async def test_global_devices_endpoint(self, client):
        link = await shorten(client)
        for ua in (UAS["desktop"], UAS["mobile"], UAS["mobile"], UAS["tablet"]):
            await _click(client, link["code"], ua)
        res = await client.get("/api/stats/devices", headers=AUTH_HEADERS)
        assert res.status_code == 200
        body = res.json()
        assert body["window_days"] == 7
        assert body["total"] == 4
        assert {d["device"] for d in body["items"]} >= {"desktop", "mobile", "tablet"}
        mobile = next(d for d in body["items"] if d["device"] == "mobile")
        assert mobile["clicks"] == 2

    async def test_global_devices_scoped_to_owner(self, client):
        link = await shorten(client)
        await _click(client, link["code"], UAS["desktop"])
        other = await shorten(client, "https://example.com/other", headers={"X-API-Key": SECOND_API_KEY})
        await _click(client, other["code"], UAS["mobile"])
        body = (await client.get("/api/stats/devices", headers=AUTH_HEADERS)).json()
        assert body["total"] == 1
        assert body["items"][0]["device"] == "desktop"

    async def test_devices_endpoint_empty(self, client):
        body = (await client.get("/api/stats/devices", headers=AUTH_HEADERS)).json()
        assert body == {"window_days": 7, "total": 0, "items": []}

    async def test_devices_requires_auth_and_route_not_shadowed(self, client):
        assert (await client.get("/api/stats/devices")).status_code == 401
        # "devices" must never be treated as a short code by /{code}
        res = await client.get("/api/stats/devices", headers=AUTH_HEADERS)
        assert res.status_code == 200

    async def test_window_filter_excludes_old_clicks(self, client):
        link = await shorten(client)
        await _click(client, link["code"], UAS["desktop"])
        # Backdate the only click 30 days, then ask for a 7-day window.
        from datetime import UTC, datetime, timedelta

        from sqlalchemy import update

        from app.db import session as session_module
        from app.models import Click

        async with session_module.SessionFactory() as session:
            await session.execute(
                update(Click).values(clicked_at=datetime.now(UTC) - timedelta(days=30))
            )
            await session.commit()
        body = (await client.get("/api/stats/devices?days=7", headers=AUTH_HEADERS)).json()
        assert body["total"] == 0
        # 90-day window still sees it
        body = (await client.get("/api/stats/devices?days=90", headers=AUTH_HEADERS)).json()
        assert body["total"] == 1

    async def test_clicks_csv_has_device_column(self, client):
        link = await shorten(client)
        await _click(client, link["code"], UAS["desktop"])
        res = await client.get(f"/api/stats/{link['code']}/export", headers=AUTH_HEADERS)
        assert res.status_code == 200
        rows = list(csv.reader(io.StringIO(res.text)))
        assert rows[0] == ["clicked_at", "ip_hash", "user_agent", "referrer", "device"]
        assert rows[1][4] == "desktop"

    async def test_validation_error_on_bad_window(self, client):
        res = await client.get("/api/stats/devices?days=0", headers=AUTH_HEADERS)
        assert res.status_code == 422
        res = await client.get("/api/stats/devices?days=91", headers=AUTH_HEADERS)
        assert res.status_code == 422
