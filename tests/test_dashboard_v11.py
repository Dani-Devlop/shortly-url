"""Dashboard v11 chrome: segmented status pills (with param-preserving
hrefs), removed status <select>, toast undo button, kbd shortcut hints."""

from tests.conftest import AUTH_HEADERS
from tests.helpers import shorten


class TestStatusPills:
    async def test_pills_render_with_param_preserving_hrefs(self, client):
        html = (await client.get("/?sort=clicks&per_page=50")).text
        assert 'class="seg"' in html
        assert '<a class="seg-item on" href="/?sort=clicks&amp;per_page=50&amp;status=clicks">' not in html
        # each pill keeps sort + per_page, only status varies
        assert 'href="/?sort=clicks&amp;per_page=50&amp;status=active"' in html
        assert 'href="/?sort=clicks&amp;per_page=50&amp;status=archived"' in html
        assert 'href="/?sort=clicks&amp;per_page=50&amp;status=all"' in html

    async def test_active_pill_is_current(self, client):
        html = (await client.get("/?status=active")).text
        assert 'aria-current="true"' in html
        assert 'aria-current="false"' in html

    async def test_archived_pill_shows_count(self, client):
        link = await shorten(client)
        res = await client.post(
            f"/api/links/{link['code']}/archive", headers=AUTH_HEADERS
        )
        assert res.status_code == 200
        html = (await client.get("/?status=archived")).text
        assert '<span class="n">1</span>' in html

    async def test_tag_filter_preserved_in_pill_hrefs(self, client):
        await shorten(client, url="https://example.com/t1", tags=["docs"])
        html = (await client.get("/?tag=docs")).text
        assert 'href="/?sort=recent&amp;per_page=25&amp;tag=docs&amp;status=archived"' in html

    async def test_status_select_removed(self, client):
        html = (await client.get("/")).text
        assert '<select name="status"' not in html

    async def test_all_pill_click_through_works(self, client):
        """The href of the 'All' pill actually renders the archived rows."""
        link = await shorten(client)
        await client.post(f"/api/links/{link['code']}/archive", headers=AUTH_HEADERS)
        html = (await client.get("/?status=all")).text
        assert f'data-code="{link["code"]}"' in html
        assert "archived" in html


class TestDashboardV11Chrome:
    async def test_undo_toast_button_present(self, client):
        html = (await client.get("/")).text
        assert 'id="toastAct"' in html
        assert ">Undo</button>" in html

    async def test_undo_queue_script_present(self, client):
        html = (await client.get("/")).text
        assert "shortlyUndo" in html  # sessionStorage undo queue
        assert "flushUndo" in html

    async def test_kbd_shortcut_hints(self, client):
        html = (await client.get("/")).text
        assert "<kbd>/</kbd> filter" in html
        assert "<kbd>n</kbd> new link" in html

    async def test_shortcut_handler_registered(self, client):
        html = (await client.get("/")).text
        assert "addEventListener('keydown'" in html
        assert "tableFilter" in html

    async def test_stacked_referrer_legend_present(self, client):
        html = (await client.get("/")).text
        assert "src-legend" in html
        assert "bar segments = device mix" in html
