"""GET /api/stats/compare — side-by-side comparison of exactly two codes."""

from datetime import UTC, datetime, timedelta

from tests.conftest import AUTH_HEADERS, SECOND_API_KEY
from tests.helpers import shorten


async def _click(client, code: str, n: int = 1):
    for _ in range(n):
        resp = await client.get(f"/{code}")
        assert resp.status_code in (301, 302, 410), resp.status_code


async def test_compare_requires_auth(client):
    await shorten(client)
    await shorten(client)
    response = await client.get("/api/stats/compare", params={"codes": "a,b"})
    assert response.status_code == 401


async def test_compare_happy_path(client):
    a = await shorten(client, url="https://example.com/cmp-a-src", custom_code="cmp-a")
    b = await shorten(client, url="https://example.com/cmp-b-src", custom_code="cmp-b")
    await _click(client, a["code"], 3)
    await _click(client, b["code"], 1)

    response = await client.get(
        "/api/stats/compare", params={"codes": "cmp-a,cmp-b", "days": 14}, headers=AUTH_HEADERS
    )
    assert response.status_code == 200
    body = response.json()
    assert body["window_days"] == 14
    assert len(body["items"]) == 2
    first, second = body["items"]
    assert first["code"] == "cmp-a"  # request order preserved
    assert second["code"] == "cmp-b"
    assert first["total_clicks"] == 3
    assert second["total_clicks"] == 1
    assert first["points"][-1] == 3 and sum(first["points"]) == 3
    assert len(first["points"]) == 14 and len(second["points"]) == 14
    assert first["original_url"] == a["original_url"]


async def test_compare_backdated_clicks_in_window(client, db_engine):
    from sqlalchemy import select, update

    from app.db.session import get_session_factory
    from app.models import Click, Link
    from app.services.stats_service import get_daily_clicks_for_links

    data = await shorten(client, custom_code="backcmp")
    await _click(client, data["code"], 2)
    # one click stays today, one moves 3 days back (inside the 14d window)
    factory = get_session_factory()
    async with factory() as session:
        rows = list((await session.execute(select(Click.id))).scalars().all())
        assert len(rows) == 2
        await session.execute(
            update(Click).where(Click.id == rows[0]).values(
                clicked_at=datetime.now(UTC) - timedelta(days=3)
            )
        )
        await session.commit()
        link_id = (await session.execute(
            select(Link.id).where(Link.code == "backcmp")
        )).scalar_one()
        series = await get_daily_clicks_for_links(session, [link_id], days=14)

    points = series[link_id]
    assert points[-1] == 1 and points[-4] == 1 and sum(points) == 2


async def test_compare_owner_scoped_404(client):
    await shorten(client, custom_code="my-cmp")
    await shorten(
        client, custom_code="their-cmp", headers={"X-API-Key": SECOND_API_KEY}
    )
    response = await client.get(
        "/api/stats/compare", params={"codes": "my-cmp,their-cmp"}, headers=AUTH_HEADERS
    )
    assert response.status_code == 404
    assert "their-cmp" in response.json()["error"]["message"]


async def test_compare_unknown_code_404(client):
    await shorten(client)
    response = await client.get(
        "/api/stats/compare", params={"codes": "ghost,missing"}, headers=AUTH_HEADERS
    )
    assert response.status_code == 404


async def test_compare_param_validation(client):
    await shorten(client, custom_code="one-1")
    await shorten(client, custom_code="two-2")
    headers = AUTH_HEADERS
    # a single code
    response = await client.get("/api/stats/compare", params={"codes": "one-1"}, headers=headers)
    assert response.status_code == 422
    # three codes
    response = await client.get(
        "/api/stats/compare", params={"codes": "one-1,two-2,one-1"}, headers=headers
    )
    assert response.status_code == 422
    # identical codes
    response = await client.get("/api/stats/compare", params={"codes": "one-1,one-1"}, headers=headers)
    assert response.status_code == 422
    # invalid code characters
    response = await client.get("/api/stats/compare", params={"codes": "one-1,ba:d!"}, headers=headers)
    assert response.status_code == 422
    # days out of range
    for bad in (0, 91):
        response = await client.get(
            "/api/stats/compare", params={"codes": "one-1,two-2", "days": bad}, headers=headers
        )
        assert response.status_code == 422


async def test_compare_route_not_shadowed_by_code_lookup(client):
    await shorten(client)
    await shorten(client)
    response = await client.get(
        "/api/stats/compare", params={"codes": "nope1,nope2"}, headers=AUTH_HEADERS
    )
    # 404 comes from the compare handler (not_found), proving routing hit
    # /api/stats/compare rather than a code lookup of "compare"
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
