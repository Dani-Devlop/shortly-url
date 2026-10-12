"""GET /api/stats/sparklines — zero-filled daily series per link."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from tests.conftest import AUTH_HEADERS, SECOND_API_KEY
from tests.helpers import shorten


async def test_sparklines_requires_auth(client):
    await shorten(client)
    response = await client.get("/api/stats/sparklines")
    assert response.status_code == 401


async def test_sparklines_zero_filled_series(client):
    data = await shorten(client)
    code = data["code"]
    for _ in range(2):
        await client.get(f"/{code}")

    response = await client.get(
        "/api/stats/sparklines", params={"days": 7}, headers=AUTH_HEADERS
    )
    assert response.status_code == 200
    body = response.json()
    assert body["window_days"] == 7
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["code"] == code
    assert len(item["points"]) == 7
    assert item["points"][-1] == 2  # today's clicks, newest bucket last
    assert item["total_clicks"] == 2
    assert sum(item["points"]) == 2


async def test_sparklines_backdated_clicks_land_in_correct_bucket(client, db_engine):
    from app.db.session import get_session_factory
    from app.models import Click

    data = await shorten(client)
    code = data["code"]
    for _ in range(2):
        await client.get(f"/{code}")

    # Backdate both clicks to 2 days ago (inside a 3-day window).
    backdated = datetime.now(UTC) - timedelta(days=2)
    async with get_session_factory()() as session:
        await session.execute(
            update(Click)
            .values(clicked_at=backdated)
            .where(Click.link_id == int(data["id"]))
        )
        await session.commit()

    response = await client.get(
        "/api/stats/sparklines", params={"days": 3}, headers=AUTH_HEADERS
    )
    assert response.status_code == 200
    points = response.json()["items"][0]["points"]
    assert len(points) == 3
    assert points[0] == 2  # oldest bucket = 2 days ago
    assert points[-1] == 0  # today is empty


async def test_sparklines_owner_scope(client):
    await shorten(client, url="https://mine.example/1")
    other = await shorten(
        client, url="https://theirs.example/1", headers={"X-API-Key": SECOND_API_KEY}
    )
    response = await client.get("/api/stats/sparklines", headers=AUTH_HEADERS)
    codes = {item["code"] for item in response.json()["items"]}
    assert other["code"] not in codes
    assert len(codes) == 1


async def test_sparklines_window_bounds(client):
    await shorten(client)
    for days, expected in ((0, 422), (31, 422), (1, 200), (30, 200)):
        response = await client.get(
            "/api/stats/sparklines", params={"days": days}, headers=AUTH_HEADERS
        )
        assert response.status_code == expected, days


async def test_sparklines_empty_account(client):
    response = await client.get("/api/stats/sparklines", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json()["items"] == []
