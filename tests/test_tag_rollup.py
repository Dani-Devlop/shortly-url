"""GET /api/stats/tags (+ CSV export) — clicks aggregated per tag."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from tests.conftest import AUTH_HEADERS, SECOND_API_KEY
from tests.helpers import shorten


async def _click(client, code: str, n: int = 1):
    for _ in range(n):
        resp = await client.get(f"/{code}")
        assert resp.status_code in (301, 302, 410), resp.status_code


async def test_tags_requires_auth(client):
    await shorten(client, tags=["docs"])
    response = await client.get("/api/stats/tags")
    assert response.status_code == 401


async def test_tags_rollup_counts_clicks_and_links(client):
    alpha = await shorten(
        client, url="https://example.com/roll-alpha", custom_code="alpha",
        tags=["docs", "python"],
    )
    beta = await shorten(client, url="https://example.com/roll-beta", custom_code="beta", tags=["docs"])
    await _click(client, alpha["code"], 3)
    await _click(client, beta["code"], 1)

    response = await client.get("/api/stats/tags", headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["window_days"] == 30
    # clicks are counted once per (tag, click) pair: alpha's 3 clicks land in
    # BOTH docs and python, beta's single click lands in docs → 4 + 3 = 7
    assert body["total_clicks"] == 7
    items = {item["tag"]: item for item in body["items"]}
    assert set(items) == {"docs", "python"}
    assert items["docs"]["clicks"] == 4
    assert items["docs"]["links"] == 2
    assert items["python"]["clicks"] == 3
    assert items["python"]["links"] == 1
    # ranked by clicks desc → docs (4) first
    assert [item["tag"] for item in body["items"]][0] == "docs"


async def test_tags_includes_zero_click_tags(client):
    await shorten(client, tags=["quiet"])
    response = await client.get("/api/stats/tags", headers=AUTH_HEADERS)
    items = {item["tag"]: item for item in response.json()["items"]}
    assert items["quiet"]["clicks"] == 0
    assert items["quiet"]["links"] == 1


async def test_tags_window_excludes_old_clicks(client, db_engine):
    from app.db.session import get_session_factory
    from app.models import Click

    data = await shorten(client, tags=["old"])
    await _click(client, data["code"], 2)
    factory = get_session_factory()
    async with factory() as session:
        backdated = datetime.now(UTC) - timedelta(days=45)
        await session.execute(update(Click).values(clicked_at=backdated))
        await session.commit()

    response = await client.get("/api/stats/tags", params={"days": 30}, headers=AUTH_HEADERS)
    items = {item["tag"]: item for item in response.json()["items"]}
    assert items["old"]["clicks"] == 0  # window excludes the 45-day-old clicks
    assert items["old"]["links"] == 1  # but the link count is all-time

    response = await client.get("/api/stats/tags", params={"days": 90}, headers=AUTH_HEADERS)
    items = {item["tag"]: item for item in response.json()["items"]}
    assert items["old"]["clicks"] == 2


async def test_tags_unique_visitors(client):
    data = await shorten(client, tags=["uniq"])
    await _click(client, data["code"], 5)
    response = await client.get("/api/stats/tags", headers=AUTH_HEADERS)
    items = {item["tag"]: item for item in response.json()["items"]}
    # same test client ip → all 5 clicks collapse to one unique visitor
    assert items["uniq"]["clicks"] == 5
    assert items["uniq"]["unique_visitors"] == 1


async def test_tags_owner_scoping(client):
    await shorten(client, custom_code="mine", tags=["shared"])
    foreign = await shorten(
        client, custom_code="theirs", tags=["shared"], headers={"X-API-Key": SECOND_API_KEY}
    )
    await _click(client, foreign["code"], 2)

    response = await client.get("/api/stats/tags", headers=AUTH_HEADERS)
    items = {item["tag"]: item for item in response.json()["items"]}
    assert items["shared"]["clicks"] == 0  # the second user's clicks don't leak
    assert items["shared"]["links"] == 1

    response = await client.get("/api/stats/tags", headers={"X-API-Key": SECOND_API_KEY})
    items = {item["tag"]: item for item in response.json()["items"]}
    assert items["shared"]["clicks"] == 2
    assert items["shared"]["links"] == 1


async def test_tags_days_validation(client):
    for bad in (0, 91):
        response = await client.get(
            "/api/stats/tags", params={"days": bad}, headers=AUTH_HEADERS
        )
        assert response.status_code == 422


async def test_tags_route_not_shadowed_by_code_lookup(client):
    """GET /api/stats/tags must answer the rollup, never a code lookup 404."""
    await shorten(client, url="https://example.com/shadow-probe", tags=["xx"])
    response = await client.get("/api/stats/tags", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert "items" in response.json()


async def test_tags_csv_export(client):
    alpha = await shorten(client, custom_code="alpha", tags=["csvtag"])
    await _click(client, alpha["code"], 2)
    response = await client.get("/api/stats/tags/export", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    lines = response.text.strip().splitlines()
    assert lines[0] == "tag,links,clicks,unique_visitors"
    assert lines[1] == "csvtag,1,2,1"
