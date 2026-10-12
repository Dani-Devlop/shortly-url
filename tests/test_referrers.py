"""Referrer (traffic source) analytics — capture on redirect, detail aggregation,
CSV export column."""

from tests.conftest import AUTH_HEADERS
from tests.helpers import shorten


async def test_redirect_captures_referrer(client):
    data = await shorten(client, url="https://ref.example/capture")
    code = data["code"]
    await client.get(f"/{code}", headers={"Referer": "https://news.ycombinator.com/item?id=1"})
    await client.get(f"/{code}")  # direct — no Referer header

    detail = await client.get(f"/api/links/{code}", headers=AUTH_HEADERS)
    assert detail.status_code == 200
    body = detail.json()

    referrers = {r["source"]: r["clicks"] for r in body["top_referrers"]}
    assert referrers == {"https://news.ycombinator.com/item?id=1": 1, "direct": 1}
    # Per-click rows also carry the raw referrer (None for direct).
    raw = {c["referrer"] for c in body["recent_clicks"]}
    assert raw == {"https://news.ycombinator.com/item?id=1", None}


async def test_top_referrers_ranked_by_clicks(client):
    data = await shorten(client, url="https://ref.example/rank")
    code = data["code"]
    for _ in range(4):
        await client.get(f"/{code}", headers={"Referer": "https://a.example/page"})
    for _ in range(2):
        await client.get(f"/{code}", headers={"Referer": "https://b.example/page"})
    await client.get(f"/{code}")

    body = (await client.get(f"/api/links/{code}", headers=AUTH_HEADERS)).json()
    top = body["top_referrers"]
    assert [r["source"] for r in top][:3] == [
        "https://a.example/page",
        "https://b.example/page",
        "direct",
    ]
    assert [r["clicks"] for r in top][:3] == [4, 2, 1]


async def test_top_referrers_capped_at_five(client):
    data = await shorten(client, url="https://ref.example/cap")
    code = data["code"]
    for i in range(7):
        await client.get(f"/{code}", headers={"Referer": f"https://s{i}.example/"})

    body = (await client.get(f"/api/links/{code}", headers=AUTH_HEADERS)).json()
    assert len(body["top_referrers"]) == 5


async def test_top_referrers_tie_breaks_alphabetically(client):
    data = await shorten(client, url="https://ref.example/tie")
    code = data["code"]
    await client.get(f"/{code}", headers={"Referer": "https://zeta.example/"})
    await client.get(f"/{code}", headers={"Referer": "https://alpha.example/"})

    body = (await client.get(f"/api/links/{code}", headers=AUTH_HEADERS)).json()
    sources = [r["source"] for r in body["top_referrers"]]
    assert sources == ["https://alpha.example/", "https://zeta.example/"]


async def test_no_clicks_means_empty_referrers(client):
    data = await shorten(client, url="https://ref.example/empty")
    body = (await client.get(f"/api/links/{data['code']}", headers=AUTH_HEADERS)).json()
    assert body["top_referrers"] == []
    assert body["recent_clicks"] == []


async def test_referrer_truncated_to_512_chars(client, db_engine):
    from sqlalchemy import select

    from app.db.session import get_session_factory
    from app.models import Click

    data = await shorten(client, url="https://ref.example/long")
    code = data["code"]
    long_referrer = "https://long.example/" + "x" * 1000
    await client.get(f"/{code}", headers={"Referer": long_referrer})

    async with get_session_factory()() as session:
        row = (await session.execute(
            select(Click).where(Click.link_id == int(data["id"]))
        )).scalars().one()
    assert row.referrer is not None and len(row.referrer) <= 512


async def test_clicks_csv_includes_referrer_column(client):
    data = await shorten(client, url="https://ref.example/csv")
    code = data["code"]
    await client.get(f"/{code}", headers={"Referer": "https://csv.example/from"})
    await client.get(f"/{code}")

    response = await client.get(f"/api/stats/{code}/export", headers=AUTH_HEADERS)
    assert response.status_code == 200
    lines = response.text.strip().splitlines()
    assert lines[0] == "clicked_at,ip_hash,user_agent,referrer"
    assert any("https://csv.example/from" in line for line in lines[1:])
    assert any(",direct" in line for line in lines[1:])
