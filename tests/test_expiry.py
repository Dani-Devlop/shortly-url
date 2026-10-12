"""Link expiry — expires_at creation, 410 Gone redirects, PATCH expiry management."""

import asyncio
from datetime import UTC, datetime, timedelta

from tests.conftest import AUTH_HEADERS, SECOND_API_KEY
from tests.helpers import shorten


def _iso(seconds_ahead: float) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds_ahead)).isoformat()


async def test_create_with_expiry_echoes_field(client):
    data = await shorten(client, url="https://expiry.example/one", expires_at=_iso(3600))
    assert data["expires_at"] is not None
    assert data["code"]


async def test_create_without_expiry_has_null_expires_at(client):
    data = await shorten(client)
    assert data["expires_at"] is None


async def test_create_rejects_past_expiry(client):
    response = await client.post(
        "/api/shorten",
        json={"url": "https://expiry.example/past", "expires_at": "2020-01-01T00:00:00Z"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 422


async def test_redirect_before_expiry_is_302(client):
    data = await shorten(client, url="https://expiry.example/live", expires_at=_iso(3600))
    response = await client.get(f"/{data['code']}", follow_redirects=False)
    assert response.status_code == 302


async def test_redirect_after_expiry_is_410_gone(client, fake_redis):
    """Cache path: the warm entry carries the expiry and must 410 once passed."""
    data = await shorten(client, url="https://expiry.example/doomed", expires_at=_iso(1.2))
    code = data["code"]
    early = await client.get(f"/{code}", follow_redirects=False)
    assert early.status_code == 302  # still live right now

    await asyncio.sleep(1.4)
    gone = await client.get(f"/{code}")
    assert gone.status_code == 410
    body = gone.json()
    assert body["error"]["code"] == "link_expired"


async def test_expired_link_does_not_record_clicks(client):
    data = await shorten(client, url="https://expiry.example/noclick", expires_at=_iso(1.2))
    code = data["code"]
    await asyncio.sleep(1.4)
    await client.get(f"/{code}")
    await client.get(f"/{code}")
    stats = await client.get(f"/api/stats/{code}", headers=AUTH_HEADERS)
    assert stats.json()["total_clicks"] == 0


async def test_expired_link_db_path_also_410(client):
    """No Redis at all → the DB lookup path must enforce the expiry too."""
    data = await shorten(client, url="https://expiry.example/dbpath", expires_at=_iso(1.2))
    await asyncio.sleep(1.4)
    gone = await client.get(f"/{data['code']}")
    assert gone.status_code == 410


async def test_patch_sets_future_expiry(client, fake_redis):
    data = await shorten(client, url="https://expiry.example/patched")
    code = data["code"]
    response = await client.patch(
        f"/api/links/{code}",
        json={"expires_at": _iso(3600)},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["expires_at"] is not None

    # The redirect must still work right after setting a future expiry.
    live = await client.get(f"/{code}", follow_redirects=False)
    assert live.status_code == 302


async def test_patch_clears_expiry_with_null(client):
    data = await shorten(client, url="https://expiry.example/clearable", expires_at=_iso(3600))
    code = data["code"]
    response = await client.patch(
        f"/api/links/{code}",
        json={"expires_at": None},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["expires_at"] is None
    live = await client.get(f"/{code}", follow_redirects=False)
    assert live.status_code == 302


async def test_patch_rejects_past_expiry(client):
    data = await shorten(client)
    response = await client.patch(
        f"/api/links/{data['code']}",
        json={"expires_at": "2020-01-01T00:00:00Z"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 422


async def test_patch_with_empty_body_is_422(client):
    data = await shorten(client)
    response = await client.patch(f"/api/links/{data['code']}", json={}, headers=AUTH_HEADERS)
    assert response.status_code == 422


async def test_patch_expiry_invalidates_warm_cache(client, fake_redis):
    """A warm cache entry must not outlive an expiry set via PATCH."""
    data = await shorten(client, url="https://expiry.example/cache")
    code = data["code"]
    first = await client.get(f"/{code}", follow_redirects=False)
    assert first.headers["x-cache"] == "HIT"  # warmed, no expiry

    patched = await client.patch(
        f"/api/links/{code}",
        json={"expires_at": _iso(1.1)},
        headers=AUTH_HEADERS,
    )
    assert patched.status_code == 200
    await asyncio.sleep(1.3)

    gone = await client.get(f"/{code}")
    assert gone.status_code == 410


async def test_expired_link_still_manageable_and_listed(client):
    """Expiry only affects the redirect — stats/list/detail keep working."""
    data = await shorten(client, url="https://expiry.example/manage", expires_at=_iso(1.2))
    code = data["code"]
    await asyncio.sleep(1.4)

    links = await client.get("/api/links", headers=AUTH_HEADERS)
    assert any(item["code"] == code for item in links.json()["items"])

    detail = await client.get(f"/api/links/{code}", headers=AUTH_HEADERS)
    assert detail.status_code == 200

    stats = await client.get(f"/api/stats/{code}", headers=AUTH_HEADERS)
    assert stats.status_code == 200


async def test_expiry_ownership_still_enforced(client):
    data = await shorten(client, url="https://expiry.example/owned", expires_at=_iso(3600))
    response = await client.patch(
        f"/api/links/{data['code']}",
        json={"expires_at": _iso(7200)},
        headers={"X-API-Key": SECOND_API_KEY},
    )
    assert response.status_code == 404
