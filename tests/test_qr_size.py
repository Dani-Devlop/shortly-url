"""QR size variants: ?size= scales PNG pixels exactly and SVG width/height."""

import io

from httpx import AsyncClient
from PIL import Image

from tests.helpers import shorten


async def test_png_respects_size(client: AsyncClient):
    data = await shorten(client, url="https://example.com/qr-size")
    response = await client.get(f"/{data['code']}/qr?format=png&size=128")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    image = Image.open(io.BytesIO(response.content))
    assert image.size == (128, 128)


async def test_svg_respects_size(client: AsyncClient):
    data = await shorten(client, url="https://example.com/qr-svg-size")
    response = await client.get(f"/{data['code']}/qr?format=svg&size=512")
    assert response.status_code == 200
    body = response.text
    assert 'width="512"' in body and 'height="512"' in body
    # viewBox (module geometry) is untouched by the presentation size.
    assert "viewBox" in body


async def test_size_bounds_enforced(client: AsyncClient):
    data = await shorten(client, url="https://example.com/qr-bounds")
    for bad_size in ("0", "63", "1025", "abc"):
        response = await client.get(f"/{data['code']}/qr?format=png&size={bad_size}")
        assert response.status_code == 422, bad_size
    # Defaults still work without the parameter.
    ok = await client.get(f"/{data['code']}/qr?format=png")
    assert ok.status_code == 200
    assert Image.open(io.BytesIO(ok.content)).size == (256, 256)
