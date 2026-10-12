"""GET /{code}/qr — public SVG QR codes — and X-Cache header behaviour."""

from tests.helpers import shorten


async def test_qr_returns_svg(client):
    data = await shorten(client, url="https://example.com/qr")
    response = await client.get(f"/{data['code']}/qr")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.headers["cache-control"].startswith("public")
    body = response.text
    assert body.lstrip().startswith("<?xml") or "<svg" in body


async def test_qr_is_public(client):
    data = await shorten(client)
    response = await client.get(f"/{data['code']}/qr")  # no auth header
    assert response.status_code == 200


async def test_qr_unknown_code_404(client):
    response = await client.get("/zzzzzzz/qr")
    assert response.status_code == 404


async def test_qr_rejects_malformed_code(client):
    response = await client.get("/%27%20OR%201%3D1--/qr")
    assert response.status_code == 404


async def test_redirect_x_cache_header_without_redis(client):
    """Redis disabled → every redirect is a MISS but the header is still present."""
    data = await shorten(client)
    response = await client.get(f"/{data['code']}", follow_redirects=False)
    assert response.headers["x-cache"] == "MISS"
