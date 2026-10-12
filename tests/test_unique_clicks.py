"""Unique-visitor metric: COUNT(DISTINCT ip_hash) — total clicks vs unique
visitors on the stats endpoint, the detail endpoint and the dashboard card."""

from httpx import AsyncClient

from tests.conftest import AUTH_HEADERS
from tests.helpers import shorten


async def _hit(client: AsyncClient, code: str, ip: str | None = None, ua: str | None = None):
    headers = {}
    if ip:
        headers["X-Forwarded-For"] = ip
    if ua:
        headers["User-Agent"] = ua
    response = await client.get(f"/{code}", headers=headers or None)
    assert response.status_code == 302


async def test_same_ip_counts_once_as_unique(client: AsyncClient):
    data = await shorten(client, url="https://example.com/a")
    for _ in range(3):
        await _hit(client, data["code"], ip="10.0.0.1")
    stats = await client.get(f"/api/stats/{data['code']}", headers=AUTH_HEADERS)
    body = stats.json()
    assert body["total_clicks"] == 3
    assert body["unique_clicks"] == 1


async def test_distinct_ips_count_distinct(client: AsyncClient):
    data = await shorten(client, url="https://example.com/b")
    await _hit(client, data["code"], ip="10.0.0.1")
    await _hit(client, data["code"], ip="10.0.0.2")
    await _hit(client, data["code"], ip="10.0.0.3")
    await _hit(client, data["code"], ip="10.0.0.1")  # repeat visitor
    stats = await client.get(f"/api/stats/{data['code']}", headers=AUTH_HEADERS)
    body = stats.json()
    assert body["total_clicks"] == 4
    assert body["unique_clicks"] == 3


async def test_zero_clicks_zero_unique(client: AsyncClient):
    data = await shorten(client, url="https://example.com/c")
    stats = await client.get(f"/api/stats/{data['code']}", headers=AUTH_HEADERS)
    body = stats.json()
    assert body["total_clicks"] == 0
    assert body["unique_clicks"] == 0


async def test_unique_clicks_in_link_detail(client: AsyncClient):
    data = await shorten(client, url="https://example.com/d")
    await _hit(client, data["code"], ip="10.0.0.1", ua="Mozilla/5.0 Chrome")
    await _hit(client, data["code"], ip="10.0.0.2", ua="Mozilla/5.0 Chrome")
    detail = await client.get(f"/api/links/{data['code']}", headers=AUTH_HEADERS)
    body = detail.json()
    assert body["total_clicks"] == 2
    assert body["unique_clicks"] == 2
    # 14-day daily series for the insights modal: 14 buckets, last one is today's 2
    assert len(body["daily_14d"]) == 14
    assert body["daily_14d"][-1] == 2
    assert sum(body["daily_14d"]) == 2


async def test_unique_visitors_card_on_dashboard(client: AsyncClient):
    data = await shorten(client, url="https://example.com/e")
    await _hit(client, data["code"], ip="10.0.0.1")
    await _hit(client, data["code"], ip="10.0.0.2")
    html = (await client.get("/")).text
    assert "Unique visitors" in html
