"""GET / — HTML dashboard panel."""

from tests.conftest import AUTH_HEADERS
from tests.helpers import shorten


async def test_dashboard_renders_html(client):
    await shorten(client, url="https://example.com/visible")
    response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "shortly" in body
    assert "https://example.com/visible" in body


async def test_dashboard_lookup_found_and_missing(client):
    data = await shorten(client, url="https://example.com/lookup")
    await client.get(f"/{data['code']}")  # one click

    found = await client.get("/", params={"code": data["code"]})
    assert found.status_code == 200
    assert "Total clicks" in found.text
    assert "https://example.com/lookup" in found.text

    missing = await client.get("/", params={"code": "nope9999"})
    assert missing.status_code == 200
    assert "No link found" in missing.text


async def test_dashboard_does_not_leak_auth_headers(client):
    response = await client.get("/", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert AUTH_HEADERS["X-API-Key"] not in response.text
