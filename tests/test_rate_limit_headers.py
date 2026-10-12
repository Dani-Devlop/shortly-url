"""Rate-limit observability headers: X-RateLimit-* on success and 429,
absent when the limiter fails open (no Redis)."""

from tests.conftest import AUTH_HEADERS
from tests.helpers import shorten


def _rl_headers(res):
    return {
        name: res.headers[name]
        for name in ("X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset")
        if name in res.headers
    }


class TestRateLimitHeaders:
    async def test_headers_on_success(self, client, fake_redis):
        res = await client.post(
            "/api/shorten", json={"url": "https://example.com/rl-1"}, headers=AUTH_HEADERS
        )
        assert res.status_code == 201
        h = _rl_headers(res)
        assert int(h["X-RateLimit-Limit"]) == 10
        assert int(h["X-RateLimit-Remaining"]) == 9  # 10 - 1 consumed
        reset = int(h["X-RateLimit-Reset"])
        assert reset > 0  # unix epoch of window rollover

    async def test_remaining_decrements(self, client, fake_redis):
        for i in range(3):
            res = await client.post(
                "/api/shorten",
                json={"url": f"https://example.com/rl-dec-{i}"},
                headers=AUTH_HEADERS,
            )
            assert res.status_code == 201
        h = _rl_headers(res)
        assert int(h["X-RateLimit-Remaining"]) == 7

    async def test_headers_on_429_with_retry_after(self, client, fake_redis):
        for i in range(10):
            await client.post(
                "/api/shorten",
                json={"url": f"https://example.com/rl-429-{i}"},
                headers=AUTH_HEADERS,
            )
        res = await client.post(
            "/api/shorten", json={"url": "https://example.com/rl-over"}, headers=AUTH_HEADERS
        )
        assert res.status_code == 429
        assert "Retry-After" in res.headers
        h = _rl_headers(res)
        assert int(h["X-RateLimit-Limit"]) == 10
        assert int(h["X-RateLimit-Remaining"]) == 0  # nothing left
        assert int(h["X-RateLimit-Reset"]) > 0
        assert res.json()["error"]["code"] == "rate_limited"

    async def test_bulk_consumes_cost(self, client, fake_redis):
        urls = [f"https://example.com/bulk-rl-{i}" for i in range(4)]
        res = await client.post(
            "/api/shorten/bulk", json={"urls": urls}, headers=AUTH_HEADERS
        )
        assert res.status_code == 201
        # Bulk is a cost-4 hit in one window; no useful remaining → headers may be absent,
        # but the budget must have consumed 4 units. Next call reflects it.
        res2 = await client.post(
            "/api/shorten", json={"url": "https://example.com/after-bulk"}, headers=AUTH_HEADERS
        )
        assert res2.status_code == 201
        assert int(res2.headers["X-RateLimit-Remaining"]) == 10 - 4 - 1

    async def test_no_headers_when_failing_open(self, client):
        # No fake_redis fixture → Redis disabled → fail open, no headers advertised.
        res = await client.post(
            "/api/shorten", json={"url": "https://example.com/fail-open"}, headers=AUTH_HEADERS
        )
        assert res.status_code == 201
        assert _rl_headers(res) == {}

    async def test_no_headers_on_unrelated_endpoints(self, client, fake_redis):
        await shorten(client)
        res = await client.get("/api/links", headers=AUTH_HEADERS)
        assert res.status_code == 200
        assert "X-RateLimit-Limit" not in res.headers
