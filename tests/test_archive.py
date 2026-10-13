"""Link archival (soft delete / restore) — API, redirect behaviour, filters."""

from tests.conftest import AUTH_HEADERS, SECOND_API_KEY
from tests.helpers import shorten


async def test_archive_sets_flag_and_timestamp(client):
    link = await shorten(client, url="https://archive.example/1", custom_code="arch1")
    response = await client.post(
        "/api/links/arch1/archive", headers=AUTH_HEADERS
    )
    assert response.status_code == 200
    body = response.json()
    assert body["archived"] is True
    assert body["archived_at"] is not None
    assert body["code"] == link["code"]


async def test_restore_clears_flag(client):
    await shorten(client, url="https://archive.example/2", custom_code="arch2")
    await client.post("/api/links/arch2/archive", headers=AUTH_HEADERS)
    response = await client.post("/api/links/arch2/restore", headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["archived"] is False
    assert body["archived_at"] is None


async def test_archived_link_redirect_returns_410(client):
    await shorten(client, url="https://archive.example/3", custom_code="arch3")
    assert (await client.get("/arch3", follow_redirects=False)).status_code == 302
    await client.post("/api/links/arch3/archive", headers=AUTH_HEADERS)
    response = await client.get("/arch3", follow_redirects=False)
    assert response.status_code == 410
    error = response.json()["error"]
    assert error["code"] == "link_archived"
    assert "archived" in error["message"].lower()


async def test_restored_link_redirects_again(client):
    await shorten(client, url="https://archive.example/4", custom_code="arch4")
    await client.post("/api/links/arch4/archive", headers=AUTH_HEADERS)
    await client.post("/api/links/arch4/restore", headers=AUTH_HEADERS)
    response = await client.get("/arch4", follow_redirects=False)
    assert response.status_code == 302


async def test_list_default_excludes_archived(client):
    await shorten(client, url="https://archive.example/on", custom_code="lst-on")
    await shorten(client, url="https://archive.example/off", custom_code="lst-off")
    await client.post("/api/links/lst-off/archive", headers=AUTH_HEADERS)

    active = (await client.get("/api/links", headers=AUTH_HEADERS)).json()
    assert [i["code"] for i in active["items"]] == ["lst-on"]
    assert active["status"] == "active"

    archived = (
        await client.get("/api/links?status=archived", headers=AUTH_HEADERS)
    ).json()
    assert [i["code"] for i in archived["items"]] == ["lst-off"]

    every = (
        await client.get("/api/links?status=all", headers=AUTH_HEADERS)
    ).json()
    assert {i["code"] for i in every["items"]} == {"lst-on", "lst-off"}
    assert every["total"] == 2


async def test_list_rejects_unknown_status(client):
    response = await client.get("/api/links?status=bogus", headers=AUTH_HEADERS)
    assert response.status_code == 422


async def test_archive_unknown_and_foreign_codes_404(client):
    await shorten(client, url="https://archive.example/mine", custom_code="mine1")
    theirs = await shorten(
        client,
        url="https://archive.example/theirs",
        custom_code="their1",
        headers={"X-API-Key": SECOND_API_KEY},
    )
    assert (await client.post("/api/links/nope-x/archive", headers=AUTH_HEADERS)).status_code == 404
    assert (await client.post("/api/links/their1/archive", headers=AUTH_HEADERS)).status_code == 404
    assert (await client.post("/api/links/theirs/restore", headers=AUTH_HEADERS)).status_code == 404
    assert theirs["archived"] is False


async def test_archive_requires_auth(client):
    await shorten(client, url="https://archive.example/noauth", custom_code="noauth")
    assert (await client.post("/api/links/noauth/archive")).status_code == 401
    assert (await client.post("/api/links/noauth/restore")).status_code == 401


async def test_stats_still_work_while_archived(client):
    """Archive hides the redirect, not the analytics."""
    await shorten(client, url="https://archive.example/stats", custom_code="stats1")
    await client.get("/stats1", follow_redirects=False)
    await client.post("/api/links/stats1/archive", headers=AUTH_HEADERS)
    response = await client.get("/api/stats/stats1", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json()["total_clicks"] == 1
    daily = await client.get("/api/stats/stats1/daily", headers=AUTH_HEADERS)
    assert daily.status_code == 200


async def test_archived_link_still_410_when_cached(client, fake_redis):
    """The Redis payload carries the archived flag — 410 even on a cache hit."""
    await shorten(client, url="https://archive.example/cache", custom_code="cache1")
    assert (await client.get("/cache1", follow_redirects=False)).status_code == 302
    await client.post("/api/links/cache1/archive", headers=AUTH_HEADERS)
    response = await client.get("/cache1", follow_redirects=False)
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "link_archived"


async def test_archive_is_idempotent(client):
    await shorten(client, url="https://archive.example/idem", custom_code="idem1")
    first = await client.post("/api/links/idem1/archive", headers=AUTH_HEADERS)
    second = await client.post("/api/links/idem1/archive", headers=AUTH_HEADERS)
    assert first.status_code == second.status_code == 200
    assert second.json()["archived_at"] == first.json()["archived_at"]
    await client.post("/api/links/idem1/restore", headers=AUTH_HEADERS)
    again = await client.post("/api/links/idem1/restore", headers=AUTH_HEADERS)
    assert again.status_code == 200
    assert again.json()["archived"] is False


async def test_shorten_duplicate_returns_existing_archived_link(client):
    """Dedupe is untouched: re-submitting the URL surfaces the archived link."""
    await shorten(client, url="https://archive.example/dup", custom_code="dup-a1")
    await client.post("/api/links/dup-a1/archive", headers=AUTH_HEADERS)
    again = await client.post(
        "/api/shorten",
        json={"url": "https://archive.example/dup"},
        headers=AUTH_HEADERS,
    )
    assert again.status_code == 201
    assert again.json()["code"] == "dup-a1"
    assert again.json()["archived"] is True


async def test_dashboard_status_filter_renders(client):
    """The dashboard honours ?status= (active default, archived opt-in)."""
    await shorten(client, url="https://archive.example/ui", custom_code="dash-a1")
    await client.post("/api/links/dash-a1/archive", headers=AUTH_HEADERS)

    active_html = (await client.get("/")).text
    assert 'data-code="dash-a1"' not in active_html  # not in the links table

    archived_html = (await client.get("/?status=archived")).text
    assert 'data-code="dash-a1"' in archived_html
    assert "archived-row" in archived_html
    assert "📦 archived" in archived_html

    all_html = (await client.get("/?status=all")).text
    assert 'data-code="dash-a1"' in all_html


async def test_archived_link_public_stats_page_shows_badge(client):
    await shorten(client, url="https://archive.example/pub", custom_code="pub-a1")
    await client.post("/api/links/pub-a1/archive", headers=AUTH_HEADERS)
    response = await client.get("/s/pub-a1")
    assert response.status_code == 200
    assert "📦 archived" in response.text
