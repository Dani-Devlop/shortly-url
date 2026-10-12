"""Windowed per-link referrer endpoint: GET /api/stats/{code}/referrers."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.db import session as session_module
from app.models import Click
from tests.conftest import AUTH_HEADERS, SECOND_API_KEY
from tests.helpers import shorten


async def _click(client, code, referrer):
    await client.get(
        f"/{code}", headers={"Referer": referrer} if referrer else {}, follow_redirects=False
    )


class TestReferrerWindow:
    async def test_window_and_ranking(self, client):
        link = await shorten(client)
        await _click(client, link["code"], "https://news.ycombinator.com/item?id=1")
        await _click(client, link["code"], "https://news.ycombinator.com/item?id=2")
        await _click(client, link["code"], "https://x.com/status/1")
        await _click(client, link["code"], None)  # direct
        res = await client.get(f"/api/stats/{link['code']}/referrers", headers=AUTH_HEADERS)
        assert res.status_code == 200
        body = res.json()
        assert body["code"] == link["code"]
        assert body["window_days"] == 7
        assert body["total"] == 4  # every click in the window, not just listed ones
        sources = {item["source"]: item["clicks"] for item in body["items"]}
        assert sources["direct"] == 1
        assert sources["https://news.ycombinator.com/item?id=1"] == 1

    async def test_days_window_excludes_old_clicks(self, client):
        link = await shorten(client)
        await _click(client, link["code"], "https://example-ref.com/old")
        async with session_module.SessionFactory() as session:
            await session.execute(
                update(Click).values(clicked_at=datetime.now(UTC) - timedelta(days=14))
            )
            await session.commit()
        recent = (
            await client.get(
                f"/api/stats/{link['code']}/referrers?days=7", headers=AUTH_HEADERS
            )
        ).json()
        assert recent["total"] == 0 and recent["items"] == []
        wide = (
            await client.get(
                f"/api/stats/{link['code']}/referrers?days=30", headers=AUTH_HEADERS
            )
        ).json()
        assert wide["total"] == 1
        assert wide["items"][0]["source"] == "https://example-ref.com/old"

    async def test_limit_caps_items_but_not_total(self, client):
        link = await shorten(client)
        for i in range(5):
            await _click(client, link["code"], f"https://src{i}.example.com/")
        body = (
            await client.get(f"/api/stats/{link['code']}/referrers?limit=2", headers=AUTH_HEADERS)
        ).json()
        assert len(body["items"]) == 2
        assert body["total"] == 5

    async def test_owner_scoping(self, client):
        link = await shorten(client)
        await _click(client, link["code"], "https://ref.example.com/")
        res = await client.get(
            f"/api/stats/{link['code']}/referrers", headers={"X-API-Key": SECOND_API_KEY}
        )
        assert res.status_code == 404  # existence not leaked cross-owner

    async def test_requires_auth(self, client):
        link = await shorten(client)
        assert (
            await client.get(f"/api/stats/{link['code']}/referrers")
        ).status_code == 401

    async def test_unknown_code_404(self, client):
        res = await client.get("/api/stats/nope123/referrers", headers=AUTH_HEADERS)
        assert res.status_code == 404

    async def test_param_validation(self, client):
        link = await shorten(client)
        assert (
            await client.get(f"/api/stats/{link['code']}/referrers?days=0", headers=AUTH_HEADERS)
        ).status_code == 422
        assert (
            await client.get(f"/api/stats/{link['code']}/referrers?limit=99", headers=AUTH_HEADERS)
        ).status_code == 422
