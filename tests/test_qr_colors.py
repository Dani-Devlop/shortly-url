"""QR colour variants — GET /{code}/qr?fg=&bg= (hex, 3 or 6 digits, '#' optional)."""

import io

from PIL import Image

from tests.helpers import shorten


def _png_colors(png_bytes: bytes) -> set[tuple[int, int, int]]:
    image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    return {color for _, color in image.getcolors(maxcolors=1_000_000)}


async def _code(client) -> str:
    return (await shorten(client, url="https://qr-color.example/x", custom_code="qrc1"))["code"]


async def test_qr_default_colors_unchanged(client):
    code = await _code(client)
    response = await client.get(f"/{code}/qr?format=png")
    assert response.status_code == 200
    colors = _png_colors(response.content)
    assert (17, 24, 39) in colors  # default ink #111827
    assert (255, 255, 255) in colors  # default background #ffffff


async def test_qr_png_custom_colors(client):
    code = await _code(client)
    response = await client.get(f"/{code}/qr?format=png&fg=34d399&bg=0f172a")
    assert response.status_code == 200
    colors = _png_colors(response.content)
    assert (52, 211, 153) in colors  # #34d399
    assert (15, 23, 42) in colors  # #0f172a


async def test_qr_svg_contains_fill_colors(client):
    code = await _code(client)
    response = await client.get(f"/{code}/qr?format=svg&fg=10b981&bg=0b1220")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    svg = response.text
    assert 'fill="#10b981"' in svg  # module path ink
    assert 'fill="#0b1220"' in svg  # background rect


async def test_qr_accepts_hash_prefix_and_3_digit_hex(client):
    code = await _code(client)
    response = await client.get(f"/{code}/qr?format=svg&fg=%2300aa00&bg=f00")
    assert response.status_code == 200
    svg = response.text
    assert 'fill="#00aa00"' in svg  # '#' stripped, lowercased
    assert 'fill="#ff0000"' in svg  # 3-digit expanded


async def test_qr_rejects_invalid_colors(client):
    code = await _code(client)
    for bad in ("green", "#12345", "#1234567", "1234", "ff00zz"):
        response = await client.get(f"/{code}/qr?fg={bad}")
        assert response.status_code == 422, bad
    response = await client.get(f"/{code}/qr?bg=zzz")
    assert response.status_code == 422
