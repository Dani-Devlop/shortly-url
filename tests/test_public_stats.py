"""Public stats page at /s/{code}: shareable, no API key, privacy-safe."""

from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from httpx import AsyncClient

from app.models import Click, Link
from tests.conftest import AUTH_HEADERS
from tests.helpers import shorten


async def _seed_click(client: AsyncClient, link_id: int, session_factory, **overrides):
    """Insert a click row directly (bypasses background-task timing)."""
    async with session_factory() as session:
        from sqlalchemy import select

        link = await session.scalar(select(Link).where(Link.id == link_id))
        click = Click(
            link_id=link.id,
            clicked_at=overrides.get("clicked_at", datetime.now(UTC) - timedelta(hours=1)),
            ip_hash=overrides.get("ip_hash", "aabbccddeeff"),
            user_agent=overrides.get("user_agent", "Mozilla/5.0"),
            referrer=overrides.get("referrer", None),
            device=overrides.get("device", "desktop"),
        )
        session.add(click)
        await session.commit()


async def test_public_stats_page_renders_without_auth(client: AsyncClient, db_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    data = await shorten(client, url="https://example.com/public-stats")
    await _seed_click(client, data["id"], factory, referrer="https://news.ycombinator.com/item?id=1")
    await _seed_click(client, data["id"], factory, device="mobile", ip_hash="112233445566")

    response = await client.get(f"/s/{data['code']}")
    assert response.status_code == 200
    html = response.text
    assert data["code"] in html
    assert "example.com" in html  # destination host shown
    assert "2" in html  # click counts present (rendered anywhere)
    # Privacy: no IP hashes anywhere on the public page.
    assert "aabbccddeeff" not in html
    assert "112233445566" not in html
    # Referrer is reduced to its host.
    assert "news.ycombinator.com" in html
    # QR image + short URL are advertised.
    assert f"/{data['code']}/qr" in html
    assert f"/s/{data['code']}" in html


async def test_public_stats_page_counts_and_chart(client: AsyncClient, db_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    data = await shorten(client, url="https://example.com/chart-page")
    await _seed_click(client, data["id"], factory)
    await _seed_click(client, data["id"], factory)
    await _seed_click(client, data["id"], factory)

    response = await client.get(f"/s/{data['code']}")
    assert response.status_code == 200
    assert ">3<" in response.text  # total clicks
    # 14 chart bars (zero-filled window) rendered server-side — every bar
    # carries a class starting with "pbar" (non-zero: "pbar", zero: "pbar pbar-zero").
    assert response.text.count('class="pbar') == 14


async def test_public_stats_page_unknown_code_is_404(client: AsyncClient):
    response = await client.get("/s/does-not-exist")
    assert response.status_code == 404
    assert "not found" in response.text.lower()


async def test_public_stats_page_malformed_code_is_404(client: AsyncClient):
    response = await client.get(f"/s/{quote('../etc/passwd', safe='')}")
    assert response.status_code == 404


async def test_public_stats_page_deleted_code_is_404(client: AsyncClient):
    data = await shorten(client, url="https://example.com/doomed-public")
    delete = await client.delete(f"/api/links/{data['code']}", headers=AUTH_HEADERS)
    assert delete.status_code == 204
    response = await client.get(f"/s/{data['code']}")
    assert response.status_code == 404


async def test_public_stats_page_expired_link_shows_banner(client: AsyncClient, db_engine):
    from sqlalchemy import update as sa_update
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    data = await shorten(client, url="https://example.com/expired-public")
    async with factory() as session:
        await session.execute(
            sa_update(Link).where(Link.id == data["id"]).values(
                expires_at=datetime.now(UTC) - timedelta(days=1)
            )
        )
        await session.commit()
    # The redirect itself 410s…
    redirect = await client.get(f"/{data['code']}")
    assert redirect.status_code == 410
    # …but the stats page stays viewable with an expired marker.
    page = await client.get(f"/s/{data['code']}")
    assert page.status_code == 200
    assert "expired" in page.text.lower()


async def test_stats_page_route_does_not_shadow_redirects(client: AsyncClient):
    data = await shorten(client, url="https://example.com/no-shadow")
    response = await client.get(f"/{data['code']}")
    assert response.status_code == 302
