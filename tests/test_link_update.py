"""PATCH /api/links/{code} — update destination (with cache invalidation)."""

from tests.conftest import AUTH_HEADERS, SECOND_API_KEY
from tests.helpers import shorten


async def test_patch_updates_destination(client):
    data = await shorten(client, url="https://old.example/one")
    code = data["code"]

    response = await client.patch(
        f"/api/links/{code}",
        json={"url": "https://new.example/two"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["original_url"] == "https://new.example/two"

    redirect = await client.get(f"/{code}", follow_redirects=False)
    assert redirect.status_code == 302
    assert redirect.headers["location"] == "https://new.example/two"


async def test_patch_invalidates_warm_cache(client, fake_redis):
    """A warm Redis entry must not serve the old destination after PATCH."""
    data = await shorten(client, url="https://warm.example/before")
    code = data["code"]

    first = await client.get(f"/{code}", follow_redirects=False)
    assert first.headers["x-cache"] == "HIT"  # creation warms the cache
    assert first.headers["location"] == "https://warm.example/before"

    patched = await client.patch(
        f"/api/links/{code}",
        json={"url": "https://warm.example/after"},
        headers=AUTH_HEADERS,
    )
    assert patched.status_code == 200

    after = await client.get(f"/{code}", follow_redirects=False)
    # Without invalidation this would be a HIT serving the stale destination.
    assert after.headers["x-cache"] == "MISS"
    assert after.headers["location"] == "https://warm.example/after"


async def test_patch_rejects_invalid_url(client):
    data = await shorten(client)
    response = await client.patch(
        f"/api/links/{data['code']}", json={"url": "not-a-url"}, headers=AUTH_HEADERS
    )
    assert response.status_code == 422


async def test_patch_rejects_self_referencing_url(client):
    data = await shorten(client)
    response = await client.patch(
        f"/api/links/{data['code']}", json={"url": "http://testserver/x"}, headers=AUTH_HEADERS
    )
    assert response.status_code == 409


async def test_patch_unknown_code_404(client):
    response = await client.patch(
        "/api/links/zzzzzzz", json={"url": "https://x.example"}, headers=AUTH_HEADERS
    )
    assert response.status_code == 404


async def test_patch_owner_only(client):
    data = await shorten(client)
    response = await client.patch(
        f"/api/links/{data['code']}",
        json={"url": "https://hijack.example"},
        headers={"X-API-Key": SECOND_API_KEY},
    )
    assert response.status_code == 404


async def test_patch_requires_auth(client):
    data = await shorten(client)
    response = await client.patch(f"/api/links/{data['code']}", json={"url": "https://x.example"})
    assert response.status_code == 401
