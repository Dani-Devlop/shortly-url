"""GET / — HTML dashboard panel."""

from tests.conftest import AUTH_HEADERS
from tests.helpers import shorten


async def test_dashboard_renders_html(client):
    await shorten(client, url="https://example.com/visible")
    response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "shortly" in body
    assert "https://example.com/visible" in body


async def test_dashboard_lookup_found_and_missing(client):
    data = await shorten(client, url="https://example.com/lookup")
    await client.get(f"/{data['code']}")  # one click

    found = await client.get("/", params={"code": data["code"]})
    assert found.status_code == 200
    assert "Total clicks" in found.text
    assert "https://example.com/lookup" in found.text

    missing = await client.get("/", params={"code": "nope9999"})
    assert missing.status_code == 200
    assert "No link found" in missing.text


async def test_dashboard_does_not_leak_auth_headers(client):
    response = await client.get("/", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert AUTH_HEADERS["X-API-Key"] not in response.text


async def test_dashboard_renders_sparklines(client):
    data = await shorten(client, url="https://example.com/sparked")
    await client.get(f"/{data['code']}")
    response = await client.get("/")
    assert response.status_code == 200
    assert 'class="spark"' in response.text  # server-rendered SVG sparkline
    assert "spark-line" in response.text
    assert "Clicks · last 7d" in response.text  # summary card


async def test_dashboard_shows_expiry_badges(client, db_engine):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from app.db.session import get_session_factory
    from app.models import Link

    data = await shorten(client, url="https://example.com/expires")
    future = datetime.now(UTC) + timedelta(days=3, hours=1)  # safely inside "in 3d"
    async with get_session_factory()() as session:
        await session.execute(
            update(Link).values(expires_at=future).where(Link.code == data["code"])
        )
        await session.commit()

    response = await client.get("/")
    assert 'expiry-badge live' in response.text
    assert "in 3d" in response.text


async def test_dashboard_theme_toggle_and_a11y(client):
    response = await client.get("/")
    assert 'id="themeToggle"' in response.text
    assert "data-countup" in response.text
    assert "<dialog" in response.text  # edit/confirm/detail modals
    assert "Bulk create" in response.text
    assert "aria-label" in response.text
