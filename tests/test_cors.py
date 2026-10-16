"""CORS behaviour for the bundled SPA front-end.

The static front-end (GitHub Pages) calls the API cross-origin and
authenticates with the ``X-API-Key`` header, so preflights carrying that
header must succeed and responses must echo a permissive origin.
"""


from tests.conftest import AUTH_HEADERS


async def test_preflight_allows_api_key_header(client):
    response = await client.options(
        "/api/links",
        headers={
            "Origin": "https://dani-devlop.github.io",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-api-key",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "x-api-key" in response.headers["access-control-allow-headers"].lower()


async def test_simple_get_echoes_cors_origin(client):
    response = await client.get(
        "/health", headers={"Origin": "https://example.github.io"}
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


async def test_authenticated_request_still_works_cross_origin(client):
    response = await client.get(
        "/api/links?limit=1",
        headers={**AUTH_HEADERS, "Origin": "https://dani-devlop.github.io"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.json()["items"] == []
