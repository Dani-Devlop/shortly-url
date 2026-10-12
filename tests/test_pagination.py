"""GET /api/links pagination — {items, total, limit, offset} envelope."""

from tests.conftest import AUTH_HEADERS
from tests.helpers import shorten


async def test_list_links_envelope_shape(client):
    await shorten(client, url="https://page.example/1")
    body = (await client.get("/api/links", headers=AUTH_HEADERS)).json()
    assert set(body.keys()) == {"items", "total", "limit", "offset"}
    assert body["total"] == 1 and len(body["items"]) == 1
    assert body["limit"] == 20 and body["offset"] == 0  # defaults


async def test_pagination_slices_and_total_stays_global(client):
    for i in range(5):
        await shorten(client, url=f"https://page.example/{i}")

    page1 = (await client.get("/api/links", headers=AUTH_HEADERS, params={"limit": 2, "offset": 0})).json()
    page2 = (await client.get("/api/links", headers=AUTH_HEADERS, params={"limit": 2, "offset": 2})).json()
    page3 = (await client.get("/api/links", headers=AUTH_HEADERS, params={"limit": 2, "offset": 4})).json()

    assert page1["total"] == page2["total"] == page3["total"] == 5
    assert len(page1["items"]) == len(page2["items"]) == 2
    assert len(page3["items"]) == 1  # remainder

    codes = [item["code"] for page in (page1, page2, page3) for item in page["items"]]
    assert len(codes) == 5 and len(set(codes)) == 5  # disjoint pages, no gaps


async def test_pagination_offset_beyond_total_returns_empty(client):
    await shorten(client)
    body = (await client.get("/api/links", headers=AUTH_HEADERS, params={"offset": 50})).json()
    assert body["items"] == [] and body["total"] == 1


async def test_pagination_rejects_out_of_range_limit(client):
    for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
        response = await client.get("/api/links", headers=AUTH_HEADERS, params=params)
        assert response.status_code == 422


async def test_pagination_is_owner_scoped(client):
    from tests.conftest import SECOND_API_KEY

    await shorten(client, url="https://page.example/mine")
    await shorten(client, url="https://page.example/theirs", headers={"X-API-Key": SECOND_API_KEY})
    body = (await client.get("/api/links", headers=AUTH_HEADERS)).json()
    assert body["total"] == 1
    assert body["items"][0]["original_url"] == "https://page.example/mine"
