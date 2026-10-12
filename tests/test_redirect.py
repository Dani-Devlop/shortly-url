"""GET /{code} — redirects, 404s, click recording (incl. concurrent correctness)."""

import asyncio

from tests.conftest import AUTH_HEADERS
from tests.helpers import shorten


async def get_stats(client, code):
    return await client.get(f"/api/stats/{code}", headers=AUTH_HEADERS)


async def test_redirect_returns_302_with_location(client):
    data = await shorten(client, url="https://example.com/target")
    response = await client.get(f"/{data['code']}")
    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/target"
    assert response.headers["cache-control"] == "no-store"


async def test_redirect_unknown_code_404(client):
    response = await client.get("/zzzzzzz")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_redirect_rejects_malformed_codes(client):
    for bad in ["%27%20OR%201%3D1--", "abc def", "<script>", "..%2fetc"]:
        response = await client.get(f"/{bad}")
        assert response.status_code == 404, bad


async def test_deleted_code_redirects_404(client):
    data = await shorten(client, url="https://example.com/doomed")
    code = data["code"]
    delete = await client.delete(f"/api/links/{code}", headers=AUTH_HEADERS)
    assert delete.status_code == 204
    response = await client.get(f"/{code}")
    assert response.status_code == 404


async def test_redirect_counts_click(client):
    data = await shorten(client, url="https://example.com/counted")
    await client.get(f"/{data['code']}")
    stats = await get_stats(client, data["code"])
    assert stats.status_code == 200
    assert stats.json()["total_clicks"] == 1


async def test_concurrent_redirects_counted_correctly(client):
    data = await shorten(client, url="https://example.com/parallel")
    code = data["code"]
    responses = await asyncio.gather(
        *(client.get(f"/{code}") for _ in range(10)),
        return_exceptions=True,
    )
    assert all(not isinstance(r, Exception) and r.status_code == 302 for r in responses)
    stats = await get_stats(client, code)
    assert stats.json()["total_clicks"] == 10


async def test_clicks_recorded_with_hashed_ip_and_user_agent(client, db_engine):
    from sqlalchemy import select

    from app.models import Click

    data = await shorten(client, url="https://example.com/meta")
    await client.get(
        f"/{data['code']}", headers={"User-Agent": "pytest-agent/1.0", **AUTH_HEADERS}
    )
    from app.db.session import get_session_factory

    async with get_session_factory()() as session:
        click = (await session.execute(select(Click))).scalars().one()
    assert click.link_id == int(data["id"]) if "id" in data else True
    assert click.user_agent == "pytest-agent/1.0"
    assert click.ip_hash is not None
    assert click.ip_hash != "127.0.0.1"  # never the raw IP
    assert len(click.ip_hash) == 64  # sha256 hex digest
