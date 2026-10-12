"""Bots filter on the device-mix endpoint (exclude_bots=true drops crawlers)
and the dashboard's Devices-panel bots toggle (?bots=0)."""

from httpx import AsyncClient

from tests.conftest import AUTH_HEADERS
from tests.helpers import shorten

BOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
HUMAN_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "Chrome/126.0 Safari/537.36"
)


async def _click(client: AsyncClient, code: str, user_agent: str) -> None:
    response = await client.get(f"/{code}", headers={"user-agent": user_agent})
    assert response.status_code == 302


async def test_devices_include_bots_by_default(client: AsyncClient):
    data = await shorten(client, url="https://example.com/bots-default")
    await _click(client, data["code"], HUMAN_UA)
    await _click(client, data["code"], BOT_UA)

    response = await client.get("/api/stats/devices?days=7", headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    by_device = {item["device"]: item["clicks"] for item in body["items"]}
    assert by_device.get("desktop") == 1
    assert by_device.get("bot") == 1
    assert body["total"] == 2


async def test_devices_exclude_bots(client: AsyncClient):
    data = await shorten(client, url="https://example.com/bots-exclude")
    await _click(client, data["code"], HUMAN_UA)
    await _click(client, data["code"], HUMAN_UA)
    await _click(client, data["code"], BOT_UA)

    response = await client.get(
        "/api/stats/devices?days=7&exclude_bots=true", headers=AUTH_HEADERS
    )
    assert response.status_code == 200
    body = response.json()
    by_device = {item["device"]: item["clicks"] for item in body["items"]}
    assert "bot" not in by_device
    assert by_device.get("desktop") == 2
    assert body["total"] == 2  # total covers exactly the returned items


async def test_dashboard_bots_toggle_filters_panel(client: AsyncClient):
    data = await shorten(client, url="https://example.com/bots-panel")
    await _click(client, data["code"], HUMAN_UA)
    await _click(client, data["code"], BOT_UA)

    default = await client.get("/", follow_redirects=False)
    assert default.status_code == 200
    assert 'class="dev-seg dev-bot"' in default.text  # bot segment rendered

    hidden = await client.get("/?bots=0", follow_redirects=False)
    assert hidden.status_code == 200
    assert 'class="dev-seg dev-bot"' not in hidden.text
    assert 'class="dev-seg dev-desktop"' in hidden.text  # human classes remain
