"""GET /api/stats/{code}[/daily] — totals, daily aggregation, ownership."""

from datetime import UTC, datetime

from sqlalchemy import update

from tests.conftest import AUTH_HEADERS, SECOND_API_KEY
from tests.helpers import shorten


async def test_stats_requires_auth(client):
    data = await shorten(client)
    response = await client.get(f"/api/stats/{data['code']}")
    assert response.status_code == 401


async def test_stats_total_clicks(client):
    data = await shorten(client)
    for _ in range(3):
        await client.get(f"/{data['code']}")
    response = await client.get(f"/api/stats/{data['code']}", headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == data["code"]
    assert body["total_clicks"] == 3
    assert body["original_url"] == "https://example.com/"  # HttpUrl normalizes trailing slash


async def test_stats_unknown_code_404(client):
    response = await client.get("/api/stats/zzzzzzz", headers=AUTH_HEADERS)
    assert response.status_code == 404


async def test_stats_owner_only(client):
    data = await shorten(client)
    response = await client.get(
        f"/api/stats/{data['code']}", headers={"X-API-Key": SECOND_API_KEY}
    )
    assert response.status_code == 404  # not 403 — don't leak existence


async def test_stats_daily_aggregation(client, db_engine):
    from datetime import timedelta

    from app.db.session import get_session_factory
    from app.models import Click

    data = await shorten(client)
    code = data["code"]
    for _ in range(2):
        await client.get(f"/{code}")

    # Backdate ALL existing click rows of this link to 89 days ago
    # (within the max 90-day window), then add one fresh click for today.
    backdated = datetime.now(UTC) - timedelta(days=89)
    async with get_session_factory()() as session:
        await session.execute(
            update(Click)
            .values(clicked_at=backdated)
            .where(Click.link_id == int(data["id"]))
        )
        await session.commit()
    await client.get(f"/{code}")

    response = await client.get(
        f"/api/stats/{code}/daily", params={"days": 90}, headers=AUTH_HEADERS
    )
    assert response.status_code == 200
    body = response.json()
    assert body["window_days"] == 90
    assert body["total"] == 3
    days = {item["date"]: item["clicks"] for item in body["items"]}
    assert days.get(backdated.date().isoformat()) == 2
    assert len(days) == 2
    assert sum(days.values()) == 3


async def test_stats_daily_window_is_respected(client):
    data = await shorten(client)
    await client.get(f"/{data['code']}")
    response = await client.get(
        f"/api/stats/{data['code']}/daily", params={"days": 1}, headers=AUTH_HEADERS
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_stats_daily_rejects_out_of_range_window(client):
    data = await shorten(client)
    for days in (0, 91):
        response = await client.get(
            f"/api/stats/{data['code']}/daily", params={"days": days}, headers=AUTH_HEADERS
        )
        assert response.status_code == 422
