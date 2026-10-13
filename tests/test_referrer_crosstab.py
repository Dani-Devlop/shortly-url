"""Referrer × device cross-tab: GET /api/stats/{code}/referrers carries a
per-source ``devices`` map (one grouped query), and the link-detail endpoint's
``top_referrers`` gains the same cross-tab all-time."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.db import session as session_module
from app.models import Click
from tests.conftest import AUTH_HEADERS, SECOND_API_KEY
from tests.helpers import shorten

UA_DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
UA_MOBILE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/605"
UA_TABLET = "Mozilla/5.0 (iPad; CPU OS 16_0) AppleWebKit/605"
UA_BOT = "Googlebot/2.1 (+http://www.google.com/bot.html)"


async def _click(client, code, referrer=None, ua=UA_DESKTOP):
    headers = {"User-Agent": ua} if ua else {}
    if referrer:
        headers["Referer"] = referrer
    await client.get(f"/{code}", headers=headers, follow_redirects=False)


class TestReferrerCrossTab:
    async def test_devices_per_source_sum_to_clicks(self, client):
        link = await shorten(client)
        code = link["code"]
        ref = "https://news.ycombinator.com/item"
        await _click(client, code, ref, ua=UA_DESKTOP)
        await _click(client, code, ref, ua=UA_MOBILE)
        await _click(client, code, ref, ua=UA_DESKTOP)
        res = await client.get(f"/api/stats/{code}/referrers", headers=AUTH_HEADERS)
        assert res.status_code == 200
        items = res.json()["items"]
        assert len(items) == 1
        assert items[0]["source"] == ref
        assert items[0]["clicks"] == 3
        assert items[0]["devices"] == {"desktop": 2, "mobile": 1}
        assert sum(items[0]["devices"].values()) == items[0]["clicks"]

    async def test_direct_source_cross_tab(self, client):
        link = await shorten(client)
        await _click(client, link["code"], None, ua=UA_MOBILE)
        res = await client.get(
            f"/api/stats/{link['code']}/referrers", headers=AUTH_HEADERS
        )
        items = res.json()["items"]
        assert items[0]["source"] == "direct"
        assert items[0]["devices"] == {"mobile": 1}

    async def test_bot_clicks_appear_in_cross_tab(self, client):
        link = await shorten(client)
        ref = "https://www.google.com/search"
        await _click(client, link["code"], ref, ua=UA_BOT)
        await _click(client, link["code"], ref, ua=UA_DESKTOP)
        items = (
            await client.get(
                f"/api/stats/{link['code']}/referrers", headers=AUTH_HEADERS
            )
        ).json()["items"]
        assert items[0]["devices"] == {"desktop": 1, "bot": 1}

    async def test_tablet_classified(self, client):
        link = await shorten(client)
        await _click(client, link["code"], "https://t.co/abc", ua=UA_TABLET)
        items = (
            await client.get(
                f"/api/stats/{link['code']}/referrers", headers=AUTH_HEADERS
            )
        ).json()["items"]
        assert items[0]["devices"] == {"tablet": 1}

    async def test_detail_top_referrers_carry_devices(self, client):
        link = await shorten(client)
        ref = "https://x.com/dani"
        await _click(client, link["code"], ref, ua=UA_DESKTOP)
        await _click(client, link["code"], ref, ua=UA_BOT)
        detail = await client.get(f"/api/links/{link['code']}", headers=AUTH_HEADERS)
        assert detail.status_code == 200
        top = detail.json()["top_referrers"]
        assert len(top) == 1
        assert top[0]["source"] == ref
        assert top[0]["devices"] == {"desktop": 1, "bot": 1}

    async def test_ordering_clicks_desc_then_direct_first(self, client):
        link = await shorten(client)
        code = link["code"]
        await _click(client, code, "https://a.com/x")  # 1 click
        await _click(client, code, None, ua=UA_MOBILE)  # 1 click, direct
        await _click(client, code, "https://b.com/y")
        await _click(client, code, "https://b.com/y")
        items = (
            await client.get(f"/api/stats/{code}/referrers", headers=AUTH_HEADERS)
        ).json()["items"]
        assert [item["source"] for item in items] == [
            "https://b.com/y",  # 2 clicks
            "direct",  # tie between 1-click sources: direct (None) sorts first
            "https://a.com/x",
        ]

    async def test_days_window_scopes_the_cross_tab(self, client):
        link = await shorten(client)
        code = link["code"]
        ref = "https://example-ref.com/old"
        await _click(client, code, ref, ua=UA_MOBILE)
        async with session_module.SessionFactory() as session:
            await session.execute(
                update(Click).values(clicked_at=datetime.now(UTC) - timedelta(days=14))
            )
            await session.commit()
        recent = (
            await client.get(
                f"/api/stats/{code}/referrers?days=7", headers=AUTH_HEADERS
            )
        ).json()
        assert recent["total"] == 0 and recent["items"] == []
        wide = (
            await client.get(
                f"/api/stats/{code}/referrers?days=30", headers=AUTH_HEADERS
            )
        ).json()
        assert wide["total"] == 1
        assert wide["items"][0]["devices"] == {"mobile": 1}

    async def test_limit_caps_items_but_total_counts_all(self, client):
        link = await shorten(client)
        code = link["code"]
        for host in ("https://one.com/a", "https://two.com/b", "https://three.com/c"):
            await _click(client, code, host)
        body = (
            await client.get(
                f"/api/stats/{code}/referrers?limit=1", headers=AUTH_HEADERS
            )
        ).json()
        assert len(body["items"]) == 1
        assert body["total"] == 3

    async def test_auth_required(self, client):
        link = await shorten(client)
        res = await client.get(f"/api/stats/{link['code']}/referrers")
        assert res.status_code == 401

    async def test_unknown_and_foreign_codes_404(self, client):
        link = await shorten(client)
        assert (
            await client.get(
                "/api/stats/doesnotexist/referrers", headers=AUTH_HEADERS
            )
        ).status_code == 404
        # A different owner's link must not leak its existence either.
        foreign = (
            await client.get(
                f"/api/stats/{link['code']}/referrers",
                headers={"X-API-Key": SECOND_API_KEY},
            )
        )
        assert foreign.status_code == 404
