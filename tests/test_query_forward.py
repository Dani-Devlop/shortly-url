"""Query-param forwarding on redirect: /abc?x=1 must carry x=1 onto the
destination URL (merged with any query the destination already had)."""

from urllib.parse import parse_qsl, urlparse

from httpx import AsyncClient

from app.services.redirect_service import merge_query
from tests.conftest import AUTH_HEADERS
from tests.helpers import shorten


def _query_of(location: str) -> dict[str, list[str]]:
    parsed = urlparse(location)
    out: dict[str, list[str]] = {}
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        out.setdefault(key, []).append(value)
    return out


async def test_redirect_without_query_is_unchanged(client: AsyncClient):
    data = await shorten(client, url="https://example.com/plain")
    response = await client.get(f"/{data['code']}")
    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/plain"


async def test_redirect_forwards_query_params(client: AsyncClient):
    data = await shorten(client, url="https://example.com/landing")
    response = await client.get(f"/{data['code']}?utm_source=twitter&id=7")
    assert response.status_code == 302
    query = _query_of(response.headers["location"])
    assert query == {"utm_source": ["twitter"], "id": ["7"]}
    assert response.headers["location"].startswith("https://example.com/landing")


async def test_incoming_params_merge_and_win(client: AsyncClient):
    data = await shorten(client, url="https://example.com/p?a=1&keep=yes")
    response = await client.get(f"/{data['code']}?a=2&extra=1")
    query = _query_of(response.headers["location"])
    # incoming value overrides the destination's value for the same key
    assert query == {"a": ["2"], "keep": ["yes"], "extra": ["1"]}


async def test_query_inserted_before_fragment(client: AsyncClient):
    data = await shorten(client, url="https://example.com/page#section")
    response = await client.get(f"/{data['code']}?x=1")
    location = response.headers["location"]
    assert location.startswith("https://example.com/page?x=1#")
    assert location.endswith("#section")


async def test_blank_and_multi_value_params_preserved(client: AsyncClient):
    data = await shorten(client, url="https://example.com/multi")
    response = await client.get(f"/{data['code']}?tag=a&tag=b&empty=")
    query = _query_of(response.headers["location"])
    assert query == {"tag": ["a", "b"], "empty": [""]}


async def test_encoded_values_roundtrip(client: AsyncClient):
    data = await shorten(client, url="https://example.com/search")
    response = await client.get(f"/{data['code']}?q=hello%20world")
    query = _query_of(response.headers["location"])
    assert query == {"q": ["hello world"]}


async def test_click_still_recorded_with_forwarded_query(client: AsyncClient):
    data = await shorten(client, url="https://example.com/counted")
    await client.get(f"/{data['code']}?utm_source=newsletter")
    stats = await client.get(f"/api/stats/{data['code']}", headers=AUTH_HEADERS)
    assert stats.status_code == 200
    assert stats.json()["total_clicks"] == 1


def test_merge_query_oversized_falls_back_to_destination():
    huge = "&".join(f"k{i}=v{i}" for i in range(300))
    merged = merge_query("https://example.com/p", huge, max_length=2048)
    assert merged == "https://example.com/p"


def test_merge_query_no_incoming_is_noop():
    assert merge_query("https://example.com/p?a=1", "") == "https://example.com/p?a=1"
    assert merge_query("https://example.com/p?a=1", "&=&&") == "https://example.com/p?a=1"
