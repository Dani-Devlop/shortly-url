"""Global activity feed: GET /api/stats/activity — the owner's most recent
clicks across all links (code, device, referrer host, truncated ip_hash)."""

from httpx import AsyncClient

from tests.conftest import API_KEY, SECOND_API_KEY
from tests.helpers import shorten

DESKTOP_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0"


async def test_activity_requires_auth(client: AsyncClient):
    response = await client.get("/api/stats/activity")
    assert response.status_code == 401


async def test_activity_empty(client: AsyncClient):
    response = await client.get("/api/stats/activity")
    assert response.status_code == 401  # no key at all
    response = await client.get("/api/stats/activity", headers={"X-API-Key": SECOND_API_KEY})
    assert response.status_code == 200
    assert response.json() == {"items": [], "limit": 20}


async def test_activity_lists_recent_clicks(client: AsyncClient):
    link_a = await shorten(client, url="https://example.com/a")
    link_b = await shorten(client, url="https://example.com/b")
    await client.get(f"/{link_a['code']}", headers={"User-Agent": DESKTOP_UA})
    await client.get(
        f"/{link_b['code']}",
        headers={
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
            "Referer": "https://news.ycombinator.com/item?id=1",
        },
    )
    response = await client.get("/api/stats/activity", headers={"X-API-Key": API_KEY})
    body = response.json()
    assert response.status_code == 200
    assert [item["code"] for item in body["items"]] == [link_b["code"], link_a["code"]]
    newest, oldest = body["items"]
    # referrer reduced to its host, ip_hash truncated to 12 chars
    assert newest["referrer_host"] == "news.ycombinator.com"
    assert newest["device"] == "mobile"
    assert len(newest["ip_hash"]) == 12
    assert oldest["referrer_host"] is None  # direct
    assert oldest["device"] == "desktop"


async def test_activity_limit_bounds(client: AsyncClient):
    link = await shorten(client, url="https://example.com/l")
    for _ in range(3):
        await client.get(f"/{link['code']}")
    one = await client.get("/api/stats/activity?limit=1", headers={"X-API-Key": API_KEY})
    assert one.status_code == 200
    assert len(one.json()["items"]) == 1
    assert one.json()["limit"] == 1
    zero = await client.get("/api/stats/activity?limit=0", headers={"X-API-Key": API_KEY})
    assert zero.status_code == 422
    hundred_one = await client.get(
        "/api/stats/activity?limit=101", headers={"X-API-Key": API_KEY}
    )
    assert hundred_one.status_code == 422


async def test_activity_is_owner_scoped(client: AsyncClient):
    link = await shorten(client, url="https://example.com/mine")
    await client.get(f"/{link['code']}")
    other = await client.get("/api/stats/activity", headers={"X-API-Key": SECOND_API_KEY})
    assert other.json()["items"] == []
    mine = await client.get("/api/stats/activity", headers={"X-API-Key": API_KEY})
    assert [item["code"] for item in mine.json()["items"]] == [link["code"]]


async def test_activity_panel_on_dashboard(client: AsyncClient):
    link = await shorten(client, url="https://example.com/panel")
    await client.get(f"/{link['code']}", headers={"User-Agent": DESKTOP_UA})
    html = (await client.get("/")).text
    assert "Live activity" in html
    assert link["code"] in html
