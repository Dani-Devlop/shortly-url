"""GET /api/links and DELETE /api/links/{code} — listing, ownership, cascade."""

from sqlalchemy import func, select

from tests.conftest import AUTH_HEADERS, SECOND_API_KEY
from tests.helpers import shorten


async def test_list_links_returns_own_only(client):
    await shorten(client, url="https://mine.example/1")
    other = await client.post(
        "/api/shorten",
        json={"url": "https://theirs.example/1"},
        headers={"X-API-Key": SECOND_API_KEY},
    )
    assert other.status_code == 201

    mine = (await client.get("/api/links", headers=AUTH_HEADERS)).json()
    theirs = (await client.get("/api/links", headers={"X-API-Key": SECOND_API_KEY})).json()

    assert mine["total"] == 1 and theirs["total"] == 1
    assert mine["items"][0]["original_url"] == "https://mine.example/1"
    assert theirs["items"][0]["original_url"] == "https://theirs.example/1"


async def test_list_links_includes_click_counts(client):
    data = await shorten(client)
    for _ in range(2):
        await client.get(f"/{data['code']}")
    links = (await client.get("/api/links", headers=AUTH_HEADERS)).json()
    assert links["items"][0]["total_clicks"] == 2
    assert links["items"][0]["short_url"].endswith(links["items"][0]["code"])


async def test_list_links_requires_auth(client):
    response = await client.get("/api/links")
    assert response.status_code == 401


async def test_delete_link_then_allEndpoints_404(client):
    data = await shorten(client)
    code = data["code"]
    response = await client.delete(f"/api/links/{code}", headers=AUTH_HEADERS)
    assert response.status_code == 204

    assert (await client.get(f"/{code}")).status_code == 404
    assert (await client.get(f"/api/stats/{code}", headers=AUTH_HEADERS)).status_code == 404
    links = (await client.get("/api/links", headers=AUTH_HEADERS)).json()
    assert links["items"] == [] and links["total"] == 0


async def test_delete_cascades_click_rows(client, db_engine):
    from app.db.session import get_session_factory
    from app.models import Click

    data = await shorten(client)
    await client.get(f"/{data['code']}")
    await client.delete(f"/api/links/{data['code']}", headers=AUTH_HEADERS)

    async with get_session_factory()() as session:
        remaining = (await session.scalar(select(func.count()).select_from(Click))) or 0
    assert remaining == 0


async def test_cannot_delete_other_users_link(client):
    data = await shorten(client)
    response = await client.delete(
        f"/api/links/{data['code']}", headers={"X-API-Key": SECOND_API_KEY}
    )
    assert response.status_code == 404
    # Link still intact for its real owner.
    stats = await client.get(f"/api/stats/{data['code']}", headers=AUTH_HEADERS)
    assert stats.status_code == 200


async def test_delete_unknown_code_404(client):
    response = await client.delete("/api/links/nope123", headers=AUTH_HEADERS)
    assert response.status_code == 404


async def test_delete_requires_auth(client):
    data = await shorten(client)
    response = await client.delete(f"/api/links/{data['code']}")
    assert response.status_code == 401
