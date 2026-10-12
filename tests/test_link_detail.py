"""GET /api/links/{code} — link detail with recent clicks (owner-only)."""

from tests.conftest import AUTH_HEADERS, SECOND_API_KEY
from tests.helpers import shorten


async def test_link_detail_returns_recent_clicks(client):
    data = await shorten(client, url="https://example.com/detail")
    code = data["code"]
    for _ in range(2):
        await client.get(f"/{code}", headers={"User-Agent": "detail-agent/2.0"})

    response = await client.get(f"/api/links/{code}", headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == code
    assert body["total_clicks"] == 2
    assert body["short_url"].endswith(code)
    assert len(body["recent_clicks"]) == 2
    newest = body["recent_clicks"][0]
    assert newest["user_agent"] == "detail-agent/2.0"
    assert newest["ip_hash"] is not None and len(newest["ip_hash"]) == 12


async def test_link_detail_owner_only(client):
    data = await shorten(client)
    response = await client.get(
        f"/api/links/{data['code']}", headers={"X-API-Key": SECOND_API_KEY}
    )
    assert response.status_code == 404


async def test_link_detail_unknown_code_404(client):
    response = await client.get("/api/links/zzzzzzz", headers=AUTH_HEADERS)
    assert response.status_code == 404


async def test_link_detail_requires_auth(client):
    data = await shorten(client)
    response = await client.get(f"/api/links/{data['code']}")
    assert response.status_code == 401
