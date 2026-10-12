"""POST /api/shorten/bulk — per-item results, dedupe, validation, rate-limit cost."""

from tests.conftest import AUTH_HEADERS
from tests.helpers import shorten


async def test_bulk_creates_all(client):
    urls = [f"https://bulk.example/{i}" for i in range(3)]
    response = await client.post(
        "/api/shorten/bulk", json={"urls": urls}, headers=AUTH_HEADERS
    )
    assert response.status_code == 201
    body = response.json()
    assert body["created"] == 3
    assert body["duplicate"] == 0
    assert body["errors"] == 0
    codes = {item["code"] for item in body["results"]}
    assert len(codes) == 3


async def test_bulk_reports_duplicates_per_item(client):
    first = await shorten(client, url="https://bulk.example/dup")
    response = await client.post(
        "/api/shorten/bulk",
        json={"urls": ["https://bulk.example/dup", "https://bulk.example/fresh"]},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["created"] == 1
    assert body["duplicate"] == 1
    dup_item = next(i for i in body["results"] if i["status"] == "duplicate")
    assert dup_item["code"] == first["code"]


async def test_bulk_rejects_more_than_25(client):
    urls = [f"https://bulk.example/over/{i}" for i in range(26)]
    response = await client.post(
        "/api/shorten/bulk", json={"urls": urls}, headers=AUTH_HEADERS
    )
    assert response.status_code == 422


async def test_bulk_rejects_empty_list(client):
    response = await client.post(
        "/api/shorten/bulk", json={"urls": []}, headers=AUTH_HEADERS
    )
    assert response.status_code == 422


async def test_bulk_rejects_invalid_url_in_list(client):
    response = await client.post(
        "/api/shorten/bulk",
        json={"urls": ["https://ok.example/1", "not-a-url"]},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 422


async def test_bulk_isolates_per_item_errors(client):
    """A self-referencing URL fails alone; the other items must still be created."""
    response = await client.post(
        "/api/shorten/bulk",
        json={"urls": ["https://ok.example/1", "http://testserver/loop"]},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["created"] == 1
    assert body["errors"] == 1
    err_item = next(i for i in body["results"] if i["status"] == "error")
    assert err_item["error"]


async def test_bulk_requires_auth(client):
    response = await client.post(
        "/api/shorten/bulk", json={"urls": ["https://bulk.example/x"]}
    )
    assert response.status_code == 401


async def test_bulk_consumes_rate_limit_budget(client, fake_redis, monkeypatch):
    """A bulk call costs one unit per URL against the shorten budget."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_requests", 5)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)

    urls = [f"https://bulk.example/rl/{i}" for i in range(8)]
    response = await client.post(
        "/api/shorten/bulk", json={"urls": urls}, headers=AUTH_HEADERS
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"

    # Budget is spent — a following single shorten is blocked in the same window.
    after = await client.post(
        "/api/shorten", json={"url": "https://bulk.example/after"}, headers=AUTH_HEADERS
    )
    assert after.status_code == 429
