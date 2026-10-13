"""POST /api/tags/rename + DELETE /api/tags/{tag} — tag management."""

from tests.conftest import AUTH_HEADERS, SECOND_API_KEY
from tests.helpers import shorten


async def test_rename_requires_auth(client):
    await shorten(client, tags=["docs"])
    response = await client.post(
        "/api/tags/rename", json={"from": "docs", "to": "reference"}
    )
    assert response.status_code == 401


async def test_rename_updates_all_links(client):
    a = await shorten(client, url="https://example.com/ren-a", custom_code="ren-a", tags=["docs"])
    b = await shorten(client, url="https://example.com/ren-b", custom_code="ren-b", tags=["docs", "python"])
    response = await client.post(
        "/api/tags/rename",
        json={"from": "docs", "to": "reference"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tag"] == "reference"
    assert body["links_updated"] == 2
    assert body["links_merged"] == 0

    for data in (a, b):
        detail = (await client.get(f"/api/links/{data['code']}", headers=AUTH_HEADERS)).json()
        assert "docs" not in detail["tags"]
        assert "reference" in detail["tags"]
    detail_b = (await client.get("/api/links/ren-b", headers=AUTH_HEADERS)).json()
    assert detail_b["tags"] == ["python", "reference"]  # untouched tag kept


async def test_rename_normalises_names(client):
    await shorten(client, tags=["dev ops"])
    response = await client.post(
        "/api/tags/rename",
        json={"from": "Dev Ops", "to": "  DevTools  "},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["tag"] == "devtools"  # " DevTools " → "devtools"


async def test_rename_merges_into_existing_target(client):
    await shorten(client, url="https://example.com/mrg-a", custom_code="mrg-a", tags=["old"])
    await shorten(client, url="https://example.com/mrg-b", custom_code="mrg-b", tags=["old", "new"])
    response = await client.post(
        "/api/tags/rename", json={"from": "old", "to": "new"}, headers=AUTH_HEADERS
    )
    assert response.status_code == 200
    body = response.json()
    assert body["links_merged"] == 1  # mrg-b already had "new" → deduped
    assert body["links_updated"] == 1  # mrg-a was rewritten

    detail_a = (await client.get("/api/links/mrg-a", headers=AUTH_HEADERS)).json()
    assert detail_a["tags"] == ["new"]
    detail_b = (await client.get("/api/links/mrg-b", headers=AUTH_HEADERS)).json()
    assert detail_b["tags"] == ["new"]  # "old" dropped, "new" kept once


async def test_rename_same_names_rejected(client):
    await shorten(client, tags=["same"])
    response = await client.post(
        "/api/tags/rename", json={"from": "same", "to": "same"}, headers=AUTH_HEADERS
    )
    assert response.status_code == 422


async def test_rename_invalid_target_rejected(client):
    await shorten(client, tags=["good"])
    response = await client.post(
        "/api/tags/rename", json={"from": "good", "to": "bad tag!"}, headers=AUTH_HEADERS
    )
    assert response.status_code == 422  # "!" fails the tag charset


async def test_rename_unknown_tag_404(client):
    response = await client.post(
        "/api/tags/rename", json={"from": "ghost", "to": "real"}, headers=AUTH_HEADERS
    )
    assert response.status_code == 404
    assert "ghost" in response.json()["error"]["message"]


async def test_rename_is_owner_scoped(client):
    await shorten(client, custom_code="mine-1", tags=["team"])
    await shorten(
        client, custom_code="their-1", tags=["team"], headers={"X-API-Key": SECOND_API_KEY}
    )
    response = await client.post(
        "/api/tags/rename", json={"from": "team", "to": "squad"}, headers=AUTH_HEADERS
    )
    assert response.status_code == 200
    assert response.json()["links_updated"] == 1  # only my link

    my_detail = (await client.get("/api/links/mine-1", headers=AUTH_HEADERS)).json()
    assert my_detail["tags"] == ["squad"]
    their_detail = (
        await client.get("/api/links/their-1", headers={"X-API-Key": SECOND_API_KEY})
    ).json()
    assert their_detail["tags"] == ["team"]  # untouched


async def test_delete_tag_strips_from_all_links(client):
    a = await shorten(client, url="https://example.com/del-a", custom_code="del-a", tags=["gone", "stay"])
    b = await shorten(client, url="https://example.com/del-b", custom_code="del-b", tags=["gone"])
    response = await client.delete("/api/tags/gone", headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["tag"] == "gone"
    assert body["links_removed"] == 2

    for data in (a, b):
        detail = (await client.get(f"/api/links/{data['code']}", headers=AUTH_HEADERS)).json()
        assert "gone" not in detail["tags"]
    detail_a = (await client.get("/api/links/del-a", headers=AUTH_HEADERS)).json()
    assert detail_a["tags"] == ["stay"]  # links themselves are kept


async def test_delete_unknown_tag_404(client):
    response = await client.delete("/api/tags/ghost", headers=AUTH_HEADERS)
    assert response.status_code == 404


async def test_delete_invalid_tag_422(client):
    response = await client.delete("/api/tags/BAD%20TAG", headers=AUTH_HEADERS)
    assert response.status_code == 422


async def test_delete_is_owner_scoped(client):
    await shorten(client, tags=["mine-tag"])
    await shorten(client, tags=["mine-tag"], headers={"X-API-Key": SECOND_API_KEY})
    response = await client.delete("/api/tags/mine-tag", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json()["links_removed"] == 1  # only my link row

    # second user still has their tag
    response = await client.delete(
        "/api/tags/mine-tag", headers={"X-API-Key": SECOND_API_KEY}
    )
    assert response.status_code == 200
    assert response.json()["links_removed"] == 1


async def test_tag_actions_reflected_in_tag_filter(client):
    data = await shorten(client, tags=["before"])
    await client.post(
        "/api/tags/rename", json={"from": "before", "to": "after"}, headers=AUTH_HEADERS
    )
    response = await client.get(
        "/api/links", params={"tag": "after"}, headers=AUTH_HEADERS
    )
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["code"] == data["code"]
    response = await client.get("/api/links", params={"tag": "before"}, headers=AUTH_HEADERS)
    assert response.json()["total"] == 0
