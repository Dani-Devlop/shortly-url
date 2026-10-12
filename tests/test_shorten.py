"""POST /api/shorten — happy paths, auth, validation, dedupe, boundaries."""

from tests.conftest import AUTH_HEADERS
from tests.helpers import shorten

INVALID_ALIAS_BODIES = [
    {"url": "https://example.com", "custom_code": "bad code!"},
    {"url": "https://example.com", "custom_code": "<script>"},
    {"url": "https://example.com", "custom_code": "abc"},  # too short
    {"url": "https://example.com", "custom_code": "x" * 17},  # too long
    {"url": "https://example.com", "custom_code": "' OR 1=1--"},  # injection attempt
    {"url": "https://example.com", "custom_code": ""},  # empty
]


async def test_shorten_success(client):
    data = await shorten(client, url="https://example.com/some/very/long/path")
    assert len(data["code"]) == 7
    assert data["code"].isalnum()
    assert data["short_url"].endswith(data["code"])
    assert data["original_url"] == "https://example.com/some/very/long/path"
    assert data["total_clicks"] == 0
    assert data["created_at"]


async def test_shorten_without_api_key(client):
    response = await client.post("/api/shorten", json={"url": "https://example.com"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_shorten_with_invalid_api_key(client):
    response = await client.post(
        "/api/shorten", json={"url": "https://example.com"}, headers={"X-API-Key": "wrong"}
    )
    assert response.status_code == 401


async def test_shorten_rejects_invalid_url(client):
    response = await client.post(
        "/api/shorten", json={"url": "not-a-url"}, headers=AUTH_HEADERS
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_shorten_rejects_non_http_scheme(client):
    for url in ["javascript:alert(1)", "ftp://files.example.com/x", "data:text/html,x"]:
        response = await client.post("/api/shorten", json={"url": url}, headers=AUTH_HEADERS)
        assert response.status_code == 422, url


async def test_shorten_rejects_self_referencing_url(client):
    response = await client.post(
        "/api/shorten", json={"url": "http://testserver/abcd"}, headers=AUTH_HEADERS
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_shorten_with_custom_code(client):
    data = await shorten(client, url="https://example.com/docs", custom_code="my-link")
    assert data["code"] == "my-link"


async def test_shorten_rejects_invalid_custom_codes(client):
    for body in INVALID_ALIAS_BODIES:
        response = await client.post("/api/shorten", json=body, headers=AUTH_HEADERS)
        assert response.status_code == 422, body


async def test_shorten_rejects_reserved_custom_code(client):
    response = await client.post(
        "/api/shorten",
        json={"url": "https://example.com", "custom_code": "docs"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 409


async def test_shorten_custom_code_conflict(client):
    await shorten(client, url="https://first.example", custom_code="taken-code")
    response = await client.post(
        "/api/shorten",
        json={"url": "https://second.example", "custom_code": "taken-code"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 409
    assert "already in use" in response.json()["error"]["message"]


async def test_shorten_duplicate_url_returns_existing_link(client):
    first = await shorten(client, url="https://example.com/dup")
    second = await shorten(client, url="https://example.com/dup")
    assert first["code"] == second["code"]
    links = (await client.get("/api/links", headers=AUTH_HEADERS)).json()
    assert len(links) == 1


async def test_shorten_accepts_unicode_url(client):
    data = await shorten(client, url="https://例え.jp/パス?x=日本語")
    assert data["code"]
    assert data["original_url"].startswith("https://")


async def test_shorten_url_max_length_boundary(client):
    long_path_ok = "https://example.com/" + "a" * 2000
    data = await shorten(client, url=long_path_ok)
    assert data["code"]

    too_long = "https://example.com/" + "b" * 2100
    response = await client.post(
        "/api/shorten", json={"url": too_long}, headers=AUTH_HEADERS
    )
    assert response.status_code == 422


async def test_shorten_empty_body_and_missing_fields(client):
    empty = await client.post("/api/shorten", headers=AUTH_HEADERS)
    assert empty.status_code == 422
    missing_url = await client.post(
        "/api/shorten", json={"custom_code": "abcde"}, headers=AUTH_HEADERS
    )
    assert missing_url.status_code == 422
