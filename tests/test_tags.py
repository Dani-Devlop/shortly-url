"""Tags: normalisation rules, create/patch/list-filter round-trips, cascade."""

import pytest

from tests.conftest import AUTH_HEADERS, SECOND_API_KEY
from tests.helpers import shorten

# ---- pure normalisation -------------------------------------------------


def test_normalize_tags_trims_lowercases_and_dedupes():
    from app.core.tags import normalize_tags

    assert normalize_tags(None) == []
    assert normalize_tags([]) == []
    assert normalize_tags(["Docs", "DOCS", "  docs "]) == ["docs"]
    assert normalize_tags(["a-b", "A B"]) == ["a-b"]
    assert normalize_tags(["x_y", "x_y "]) == ["x_y"]
    assert "x-y" in normalize_tags(["x y"])  # whitespace becomes '-'


def test_normalize_tags_rejects_bad_input():
    from app.core.tags import normalize_tags

    with pytest.raises(ValueError):
        normalize_tags(["a"])  # too short
    with pytest.raises(ValueError):
        normalize_tags(["x" * 25])  # too long
    with pytest.raises(ValueError):
        normalize_tags(["bad tag!"])  # invalid char
    with pytest.raises(ValueError):
        normalize_tags(["ok", "ok", "ok", "ok", "ok", "ok", "ok"])  # > 6
    with pytest.raises(ValueError):
        normalize_tags("not-a-list")  # wrong type


# ---- API behaviour -------------------------------------------------------

async def test_shorten_with_tags_roundtrip(client):
    data = await shorten(
        client, url="https://tags.example/one", tags=["Docs", "Launch Week"]
    )
    assert data["tags"] == ["docs", "launch-week"]
    detail = await client.get(f"/api/links/{data['code']}", headers=AUTH_HEADERS)
    assert detail.status_code == 200
    assert detail.json()["tags"] == ["docs", "launch-week"]


async def test_shorten_tags_invalid_returns_422(client):
    response = await client.post(
        "/api/shorten",
        json={"url": "https://tags.example/bad", "tags": ["no!"]},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 422


async def test_shorten_too_many_tags_returns_422(client):
    response = await client.post(
        "/api/shorten",
        json={
            "url": "https://tags.example/many",
            "tags": ["t1", "t2", "t3", "t4", "t5", "t6", "t7"],
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 422


async def test_duplicate_url_keeps_existing_tags(client):
    first = await shorten(
        client, url="https://tags.example/same", tags=["original"]
    )
    second = await shorten(
        client, url="https://tags.example/same", tags=["ignored"]
    )
    assert second["code"] == first["code"]
    assert second["tags"] == ["original"]


async def test_patch_replaces_and_clears_tags(client):
    data = await shorten(
        client, url="https://tags.example/patch", tags=["aa", "bb"]
    )
    replaced = await client.patch(
        f"/api/links/{data['code']}", json={"tags": ["cc", "dd", "ee"]}, headers=AUTH_HEADERS
    )
    assert replaced.status_code == 200
    assert replaced.json()["tags"] == ["cc", "dd", "ee"]

    cleared = await client.patch(
        f"/api/links/{data['code']}", json={"tags": []}, headers=AUTH_HEADERS
    )
    assert cleared.status_code == 200
    assert cleared.json()["tags"] == []


async def test_patch_without_tags_leaves_them_untouched(client):
    data = await shorten(
        client, url="https://tags.example/keep", tags=["keep-me"]
    )
    response = await client.patch(
        f"/api/links/{data['code']}",
        json={"url": "https://tags.example/kept"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["tags"] == ["keep-me"]


async def test_list_links_tag_filter(client):
    a = await shorten(client, url="https://tags.example/a", tags=["news"])
    await shorten(client, url="https://tags.example/b", tags=["docs"])
    c = await shorten(client, url="https://tags.example/c", tags=["news", "docs"])

    filtered = await client.get("/api/links?tag=news", headers=AUTH_HEADERS)
    assert filtered.status_code == 200
    body = filtered.json()
    codes = {item["code"] for item in body["items"]}
    assert codes == {a["code"], c["code"]}
    assert body["total"] == 2

    casefolded = await client.get("/api/links?tag=NEWS", headers=AUTH_HEADERS)
    assert casefolded.json()["total"] == 2

    empty = await client.get("/api/links?tag=missing", headers=AUTH_HEADERS)
    assert empty.json()["total"] == 0
    assert empty.json()["items"] == []


async def test_tag_filter_is_owner_scoped(client):
    await shorten(client, url="https://tags.example/mine", tags=["shared"])
    other = await client.post(
        "/api/shorten",
        json={"url": "https://tags.example/theirs", "tags": ["shared"]},
        headers={"X-API-Key": SECOND_API_KEY},
    )
    assert other.status_code == 201
    mine = await client.get("/api/links?tag=shared", headers=AUTH_HEADERS)
    assert mine.json()["total"] == 1


async def test_delete_link_cascades_tag_rows(client, db_engine):
    from sqlalchemy import func, select

    from app.models import LinkTag

    data = await shorten(client, url="https://tags.example/gone", tags=["doomed"])
    deleted = await client.delete(
        f"/api/links/{data['code']}", headers=AUTH_HEADERS
    )
    assert deleted.status_code == 204

    from app.db.session import SessionFactory

    async with SessionFactory() as session:
        count = await session.scalar(select(func.count()).select_from(LinkTag))
    assert count == 0


async def test_links_export_csv_includes_tags(client):
    data = await shorten(
        client, url="https://tags.example/csv", tags=["x1", "x2"]
    )
    response = await client.get("/api/links/export", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert f"{data['code']}," in response.text
    assert "x1;x2" in response.text
