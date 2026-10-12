"""Cross-cutting behaviour: rate limiting, fail-open mode, health, error shape."""

from tests.conftest import AUTH_HEADERS
from tests.helpers import shorten


async def test_rate_limit_returns_429_with_retry_after(client, fake_redis, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_requests", 2)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)

    codes = []
    for _ in range(2):
        data = await shorten(client, url=f"https://limit.example/{len(codes)}")
        codes.append(data["code"])

    blocked = await client.post(
        "/api/shorten", json={"url": "https://limit.example/over"}, headers=AUTH_HEADERS
    )
    assert blocked.status_code == 429
    body = blocked.json()
    assert body["error"]["code"] == "rate_limited"
    assert "Retry-After" in blocked.headers


async def test_rate_limit_fail_open_without_redis(client, monkeypatch):
    """No Redis client at all → limiter fails open, requests keep succeeding."""
    import app.core.redis as redis_module

    monkeypatch.setattr(redis_module, "_client", None)
    for i in range(15):
        response = await client.post(
            "/api/shorten", json={"url": f"https://open.example/{i}"}, headers=AUTH_HEADERS
        )
        assert response.status_code == 201, (i, response.text)


async def test_health_reports_database_and_redis(client):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["redis"] is None  # disabled in this test stack


async def test_error_envelope_is_uniform(client):
    response = await client.get("/zzzzzzz")
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message"}


async def test_unknown_api_route_returns_json_error(client):
    response = await client.get("/api/does-not-exist", headers=AUTH_HEADERS)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"


async def test_master_user_can_authenticate(client):
    response = await client.get("/api/links", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
