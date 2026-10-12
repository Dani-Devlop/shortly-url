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
    assert "<dialog" in response.text  # edit/confirm/detail/QR modals
    assert "Bulk create" in response.text
    assert "aria-label" in response.text


async def test_dashboard_v4_markup(client):
    """Round-4 additions: table filter, per-page select, API reference, QR dialog."""
    response = await client.get("/")
    assert response.status_code == 200
    body = response.text
    assert 'id="tableFilter"' in body          # client-side filter
    assert 'id="filterCount"' in body
    assert "Per page" in body                  # server-side per-page select
    assert "Quick API reference" in body       # left-column panel
    assert "format=svg|png" in body
    assert 'id="qrDlg"' in body                # QR modal (replaces new-tab link)
    assert "Traffic sources · all time" in body  # referrer chips section
    assert 'class="foot-inner"' in body        # structured footer with version pill


async def test_dashboard_pagination_controls(client):
    """With > per_page links the pager nav appears; page 2 shows the remainder."""
    for i in range(12):
        await shorten(client, url=f"https://example.com/page-check-{i}")

    page1 = await client.get("/", params={"per_page": 10})
    assert "Table pagination" in page1.text
    assert "Showing 1–10 of 12 links" in page1.text
    assert 'aria-current="page"' in page1.text
    assert "&page=2" in page1.text

    page2 = await client.get("/", params={"per_page": 10, "page": 2})
    assert "Showing 11–12 of 12 links" in page2.text
    # both page-2 rows are present, page-1 rows are not
    assert page2.text.count('data-code=') == 2

    # page number beyond the last page clamps to the last page
    clamped = await client.get("/", params={"per_page": 10, "page": 99})
    assert "Showing 11–12 of 12 links" in clamped.text

    # single page → no pager markup at all
    small = await client.get("/", params={"per_page": 50})
    assert "Table pagination" not in small.text


async def test_dashboard_avg_clicks_one_decimal(client):
    data = await shorten(client, url="https://example.com/avg")
    for _ in range(3):
        await client.get(f"/{data['code']}")
    response = await client.get("/")
    assert response.status_code == 200
    assert "Avg clicks / link" in response.text
    assert ">3.0<" in response.text  # 3 clicks / 1 link with one decimal


async def test_dashboard_per_page_invalid_falls_back(client):
    await shorten(client, url="https://example.com/fallback")
    response = await client.get("/", params={"per_page": 37})
    assert response.status_code == 200
    assert 'value="25" selected' in response.text  # clamped to a valid choice


async def test_dashboard_devices_panel(client):
    """Devices panel renders the stacked bar + legend from real click data."""
    data = await shorten(client, url="https://example.com/dev-panel")
    desktop_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36"
    mobile_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) Mobile/15E148 Safari/604.1"
    await client.get(f"/{data['code']}", headers={"User-Agent": desktop_ua})
    await client.get(f"/{data['code']}", headers={"User-Agent": desktop_ua})
    await client.get(f"/{data['code']}", headers={"User-Agent": mobile_ua})

    response = await client.get("/")
    assert response.status_code == 200
    assert "Devices" in response.text
    assert "dev-bar" in response.text
    assert 'dev-seg dev-desktop' in response.text
    assert 'dev-seg dev-mobile' in response.text
    # desktop has 2/3 of the clicks → width 67%
    assert 'style="width: 67%"' in response.text


async def test_dashboard_devices_panel_empty_state(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "No clicks in the last" in response.text


async def test_dashboard_auto_refresh_toggle_present(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert 'id="autorefBtn"' in response.text
    assert "shortlyAutoRefresh" in response.text  # persistence wiring
    assert "dialog[open]" in response.text  # pause guard while modals are open


async def test_dashboard_shows_campaign_chip_and_share_action(client):
    """v1.6.0: UTM template chip on rows + public-stats share action."""
    data = await shorten(
        client,
        url="https://example.com/campaigned",
        utm_template="utm_source=newsletter&utm_campaign=launch",
    )
    plain = await shorten(client, url="https://example.com/no-campaign")
    response = await client.get("/")
    assert response.status_code == 200
    body = response.text
    # campaign chip rendered for the link with a template (title carries the full value)
    assert 'utm-chip' in body
    assert 'utm_source=newsletter&amp;utm_campaign=launch' in body
    # no chip on the plain link row
    plain_row = body.split(f'data-code="{plain["code"]}"')[1].split("</tr>")[0]
    assert "utm-chip" not in plain_row
    # public stats action links at /s/{code}
    assert f'href="/s/{data["code"]}"' in body


async def test_dashboard_bots_toggle_link(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "bots-toggle" in response.text
    assert "bots on" in response.text
    hidden = await client.get("/", params={"bots": False})
    assert hidden.status_code == 200
    assert "bots hidden" in hidden.text


async def test_dashboard_qr_size_selector_wired(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert 'id="qrSize"' in response.text
    assert "applyQrSize" in response.text


async def test_dashboard_utm_create_field_present(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert 'id="newUtm"' in response.text
    assert 'id="editUtm"' in response.text


async def test_public_stats_page_linked_from_api_reference(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "/s/{code}" in response.text
    assert "public stats page" in response.text
