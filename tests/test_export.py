"""CSV export endpoints — /api/links/export and /api/stats/{code}/export."""

import csv
import io

from tests.conftest import AUTH_HEADERS, SECOND_API_KEY
from tests.helpers import shorten


def _parse_csv(content: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(content)))


async def test_links_export_requires_auth(client):
    await shorten(client)
    response = await client.get("/api/links/export")
    assert response.status_code == 401


async def test_links_export_csv_shape(client):
    data = await shorten(client, url="https://export.example/one")
    for _ in range(2):
        await client.get(f"/{data['code']}")

    response = await client.get("/api/links/export", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers.get("content-disposition", "")

    rows = _parse_csv(response.text)
    assert rows[0] == [
        "code", "short_url", "original_url", "total_clicks", "created_at",
        "expires_at", "tags",
    ]
    assert len(rows) == 2  # header + one link
    assert rows[1][0] == data["code"]
    assert rows[1][3] == "2"
    assert rows[1][6] == ""  # no tags on this link


async def test_links_export_owner_scope(client):
    await shorten(client, url="https://export.example/mine")
    await shorten(client, url="https://export.example/theirs", headers={"X-API-Key": SECOND_API_KEY})

    mine = await client.get("/api/links/export", headers=AUTH_HEADERS)
    theirs = await client.get(
        "/api/links/export", headers={"X-API-Key": SECOND_API_KEY}
    )
    assert len(_parse_csv(mine.text)) == 2
    assert len(_parse_csv(theirs.text)) == 2
    assert "export.example/mine" in mine.text
    assert "export.example/mine" not in theirs.text


async def test_clicks_export_csv_shape(client):
    data = await shorten(client, url="https://export.example/clicks")
    code = data["code"]
    await client.get(f"/{code}", headers={"User-Agent": "pytest-agent/1.0"})
    await client.get(f"/{code}")

    response = await client.get(f"/api/stats/{code}/export", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert f"{code}-clicks.csv" in response.headers.get("content-disposition", "")

    rows = _parse_csv(response.text)
    assert rows[0] == ["clicked_at", "ip_hash", "user_agent", "referrer", "device"]
    assert len(rows) == 3  # header + 2 clicks
    for row in rows[1:]:
        assert len(row[1]) <= 12  # ip_hash is truncated for privacy
    assert any(row[2] == "pytest-agent/1.0" for row in rows[1:])
    assert any(row[3] == "direct" for row in rows[1:])  # no Referer header sent


async def test_clicks_export_unknown_code_404(client):
    response = await client.get("/api/stats/zzzzzzz/export", headers=AUTH_HEADERS)
    assert response.status_code == 404


async def test_clicks_export_owner_only(client):
    data = await shorten(client, url="https://export.example/owned")
    response = await client.get(
        f"/api/stats/{data['code']}/export", headers={"X-API-Key": SECOND_API_KEY}
    )
    assert response.status_code == 404  # not 403 — don't leak existence


async def test_clicks_export_requires_auth(client):
    data = await shorten(client, url="https://export.example/auth")
    response = await client.get(f"/api/stats/{data['code']}/export")
    assert response.status_code == 401
