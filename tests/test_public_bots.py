"""Public stats page bot filter: ``GET /s/{code}?bots=0`` switches the
click-derived panels (devices, when-heatmap, sources, recent) to human
traffic only, while the hero totals stay truthful all-click numbers."""

from tests.helpers import shorten

UA_DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
UA_BOT = "Googlebot/2.1 (+http://www.google.com/bot.html)"


async def _seed_link_with_bot_and_human(client):
    """One link; 2 human desktop clicks + 1 bot click, all with referrers."""
    link = await shorten(client)
    code = link["code"]
    await client.get(
        f"/{code}",
        headers={"User-Agent": UA_DESKTOP, "Referer": "https://news.ycombinator.com/x"},
        follow_redirects=False,
    )
    await client.get(
        f"/{code}",
        headers={"User-Agent": UA_DESKTOP, "Referer": "https://t.co/human"},
        follow_redirects=False,
    )
    await client.get(
        f"/{code}",
        headers={"User-Agent": UA_BOT, "Referer": "https://bot-source.example/crawl"},
        follow_redirects=False,
    )
    return link


class TestPublicBotsToggle:
    async def test_default_page_includes_bots(self, client):
        link = await _seed_link_with_bot_and_human(client)
        res = await client.get(f"/s/{link['code']}")
        assert res.status_code == 200
        html = res.text
        assert "🤖 incl. bots · hide" in html
        assert 'href="/s/' + link["code"] + '?bots=0"' in html
        assert "bot: 1" in html  # device segment title

    async def test_bots_hidden_excludes_bot_segments(self, client):
        link = await _seed_link_with_bot_and_human(client)
        res = await client.get(f"/s/{link['code']}?bots=0")
        html = res.text
        assert "🙈 bots hidden · show all" in html
        assert 'href="/s/' + link["code"] + '?bots=1"' in html
        assert "bot: 1" not in html  # bot segment gone from the device bar
        assert "desktop: 2" in html
        assert "human only" in html  # panel hints updated

    async def test_hero_totals_stay_all_clicks(self, client):
        link = await _seed_link_with_bot_and_human(client)
        html = (await client.get(f"/s/{link['code']}?bots=0")).text
        # Total clicks card keeps counting crawler clicks.
        assert '<div class="value">3</div><div class="label">Total clicks</div>' in html
        assert '<div class="value">1</div><div class="label">Unique visitors</div>' in html

    async def test_recent_clicks_excludes_bot_rows(self, client):
        link = await _seed_link_with_bot_and_human(client)
        default_html = (await client.get(f"/s/{link['code']}")).text
        hidden_html = (await client.get(f"/s/{link['code']}?bots=0")).text
        assert "newest 3" in default_html
        assert "newest 2" in hidden_html
        # The bot's referrer never shows in the human-only list.
        assert "bot-source.example" not in hidden_html
        assert "bot-source.example" in default_html

    async def test_top_sources_exclude_bots(self, client):
        link = await _seed_link_with_bot_and_human(client)
        default_html = (await client.get(f"/s/{link['code']}")).text
        hidden_html = (await client.get(f"/s/{link['code']}?bots=0")).text
        assert "bot-source.example" in default_html
        assert "bot-source.example" not in hidden_html
        assert "t.co" in hidden_html

    async def test_heatmap_excludes_bots(self, client):
        link = await shorten(client)
        code = link["code"]
        await client.get(
            f"/{code}", headers={"User-Agent": UA_BOT}, follow_redirects=False
        )
        default_html = (await client.get(f"/s/{code}")).text
        hidden_html = (await client.get(f"/s/{code}?bots=0")).text
        assert "1 clicks in window · peak 1" in default_html
        assert "No clicks in the last 30 days yet." in hidden_html
        assert "human clicks" in hidden_html  # header hint

    async def test_toggle_round_trip_preserves_privacy(self, client):
        """?bots=1 explicitly is identical to the default; no ip_hash anywhere."""
        link = await _seed_link_with_bot_and_human(client)
        html = (await client.get(f"/s/{link['code']}?bots=1")).text
        assert "🤖 incl. bots · hide" in html
        assert "ip_hash" not in html

    async def test_bots_param_404_page_unaffected(self, client):
        res = await client.get("/s/nosuchcode?bots=0")
        assert res.status_code == 404

    async def test_dashboard_unaffected_by_public_toggle(self, client):
        """The owner dashboard keeps its own bots toggle (?bots=0 semantics)."""
        link = await _seed_link_with_bot_and_human(client)
        html = (await client.get("/?bots=0")).text
        assert "bots hidden" in html  # dashboard devices panel toggle state
        # Public page URL form stays /s/{code}?bots=0
        assert f'/s/{link["code"]}?bots=0' not in html
