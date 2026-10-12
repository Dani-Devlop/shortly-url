"""Per-link UTM campaign templates: creation, redirect merging (incoming >
destination > template), PATCH set/clear, cache integration, validation."""

from urllib.parse import parse_qsl, urlparse

import pytest
from httpx import AsyncClient

from app.core.utm import normalize_utm_template
from tests.conftest import AUTH_HEADERS, SECOND_API_KEY
from tests.helpers import shorten


def _query_of(location: str) -> dict[str, str]:
    return dict(parse_qsl(urlparse(location).query, keep_blank_values=True))


async def test_create_with_template_echoes_it(client: AsyncClient):
    data = await shorten(
        client,
        url="https://example.com/landing",
        utm_template="utm_source=newsletter&utm_campaign=launch",
    )
    assert data["utm_template"] == "utm_source=newsletter&utm_campaign=launch"


async def test_create_without_template_returns_none(client: AsyncClient):
    data = await shorten(client, url="https://example.com/plain")
    assert data["utm_template"] is None


async def test_template_params_applied_on_redirect(client: AsyncClient):
    data = await shorten(
        client,
        url="https://example.com/landing",
        utm_template="utm_source=newsletter&utm_campaign=launch",
    )
    response = await client.get(f"/{data['code']}")
    assert response.status_code == 302
    query = _query_of(response.headers["location"])
    assert query == {"utm_source": "newsletter", "utm_campaign": "launch"}


async def test_incoming_param_wins_over_template(client: AsyncClient):
    data = await shorten(
        client,
        url="https://example.com/landing",
        utm_template="utm_source=newsletter&utm_medium=email",
    )
    response = await client.get(f"/{data['code']}?utm_source=story")
    query = _query_of(response.headers["location"])
    assert query == {"utm_source": "story", "utm_medium": "email"}


async def test_destination_param_wins_over_template_but_incoming_wins_over_both(client: AsyncClient):
    data = await shorten(
        client,
        url="https://example.com/landing?utm_campaign=page-default&sku=9",
        utm_template="utm_campaign=campaign-default&utm_source=newsletter",
    )
    # No incoming params: destination beats the template for utm_campaign.
    plain = await client.get(f"/{data['code']}")
    assert _query_of(plain.headers["location"]) == {
        "utm_campaign": "page-default",
        "utm_source": "newsletter",
        "sku": "9",
    }
    # Incoming beats both.
    incoming = await client.get(f"/{data['code']}?utm_campaign=per-click")
    assert _query_of(incoming.headers["location"]) == {
        "utm_campaign": "per-click",
        "utm_source": "newsletter",
        "sku": "9",
    }


async def test_template_keeps_working_from_warm_cache(client: AsyncClient, fake_redis):
    data = await shorten(
        client,
        url="https://example.com/warm",
        utm_template="utm_source=cache-check",
    )
    # Creation warms the cache, so this redirect is served from Redis — the
    # template must be carried in the cache payload.
    response = await client.get(f"/{data['code']}")
    assert response.status_code == 302
    assert response.headers["x-cache"] == "HIT"
    assert _query_of(response.headers["location"]) == {"utm_source": "cache-check"}


async def test_patch_set_and_clear_template(client: AsyncClient):
    data = await shorten(client, url="https://example.com/edit-me")
    code = data["code"]
    response = await client.patch(
        f"/api/links/{code}", json={"utm_template": "utm_source=patched"}, headers=AUTH_HEADERS
    )
    assert response.status_code == 200
    assert response.json()["utm_template"] == "utm_source=patched"
    redirect = await client.get(f"/{code}")
    assert _query_of(redirect.headers["location"]) == {"utm_source": "patched"}

    clear = await client.patch(f"/api/links/{code}", json={"utm_template": None}, headers=AUTH_HEADERS)
    assert clear.status_code == 200
    assert clear.json()["utm_template"] is None
    redirect = await client.get(f"/{code}")
    assert urlparse(redirect.headers["location"]).query == ""


async def test_patch_rejects_invalid_template(client: AsyncClient):
    data = await shorten(client, url="https://example.com/invalid-utm")
    response = await client.patch(
        f"/api/links/{data['code']}",
        json={"utm_template": "utm_source=has space"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 422


async def test_create_rejects_template_url_and_fragment(client: AsyncClient):
    for bad in ("https://evil.example/?x=1", "utm_source=a#fragment", "=novalue", "has space=1"):
        response = await client.post(
            "/api/shorten",
            json={"url": "https://example.com/bad-template", "utm_template": bad},
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 422, bad
    assert response.json()["error"]["code"] == "validation_error"


async def test_template_hidden_from_other_owners_listed_for_owner(client: AsyncClient):
    data = await shorten(
        client,
        url="https://example.com/owned",
        utm_template="utm_source=mine",
    )
    other = await client.get("/api/links", headers={"X-API-Key": SECOND_API_KEY})
    assert other.status_code == 200
    assert all(item["code"] != data["code"] for item in other.json()["items"])


def test_normalize_rejects_overlong_template():
    with pytest.raises(ValueError, match="too long"):
        normalize_utm_template("k=" + "v" * 300)
    with pytest.raises(ValueError):
        normalize_utm_template("bad key=1")
    assert normalize_utm_template("") is None
    assert normalize_utm_template(None) is None
    assert normalize_utm_template("?utm_source=x") == "utm_source=x"


async def test_detail_endpoint_exposes_utm_template(client: AsyncClient):
    """Regression: /api/links/{code} detail must carry utm_template (edit-dialog prefill)."""
    data = await shorten(
        client, url="https://example.com/detail-utm", utm_template="utm_source=detail"
    )
    response = await client.get(f"/api/links/{data['code']}", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json()["utm_template"] == "utm_source=detail"
