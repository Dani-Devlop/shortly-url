"""Test helpers shared across test modules."""

from httpx import AsyncClient

from tests.conftest import AUTH_HEADERS


async def shorten(client: AsyncClient, url="https://example.com", headers=None, **payload_extra):
    """Create a link, assert 201, return the response JSON."""
    response = await client.post(
        "/api/shorten",
        json={"url": url, **payload_extra},
        headers=headers if headers is not None else AUTH_HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()
