"""YouTube API transport behaviour: retries, error classification, caching.

Every request is served by a stub transport — no network.
"""

from datetime import date

import httpx
import pytest

from bitcast.validator.youtube.api import (
    YouTubeApiError,
    YouTubeClient,
    YouTubeTransientError,
)
from bitcast.validator.youtube.cache import SearchCache


class StubTransport(httpx.AsyncBaseTransport):
    """Replays a scripted sequence of responses/exceptions, recording requests."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def json_response(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload)


def error_response(status: int) -> httpx.Response:
    return httpx.Response(status, text="boom")


def make_client(transport: StubTransport, search_cache: SearchCache | None = None) -> YouTubeClient:
    return YouTubeClient("token", httpx.AsyncClient(transport=transport), search_cache)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Collapse retry backoff so retry tests stay fast."""

    async def instant(_seconds):
        return None

    monkeypatch.setattr("bitcast.http.asyncio.sleep", instant)


class TestTransientRetries:
    async def test_retries_500_then_succeeds(self):
        transport = StubTransport(error_response(500), json_response({"ok": True}))
        client = make_client(transport)
        assert await client._get("https://api.test/x", {}) == {"ok": True}
        assert len(transport.requests) == 2

    async def test_retries_429_then_succeeds(self):
        transport = StubTransport(error_response(429), json_response({"ok": True}))
        client = make_client(transport)
        assert await client._get("https://api.test/x", {}) == {"ok": True}
        assert len(transport.requests) == 2

    async def test_retries_network_error_then_succeeds(self):
        transport = StubTransport(httpx.ConnectError("reset"), json_response({"ok": True}))
        client = make_client(transport)
        assert await client._get("https://api.test/x", {}) == {"ok": True}
        assert len(transport.requests) == 2

    async def test_exhausted_transient_status_raises_transient_error(self):
        transport = StubTransport(error_response(503))
        client = make_client(transport)
        with pytest.raises(YouTubeTransientError):
            await client._get("https://api.test/x", {})
        assert len(transport.requests) == 3

    async def test_exhausted_network_error_raises_transient_error(self):
        transport = StubTransport(httpx.ConnectError("reset"))
        client = make_client(transport)
        with pytest.raises(YouTubeTransientError):
            await client._get("https://api.test/x", {})
        assert len(transport.requests) == 3


class TestDefinitiveErrors:
    @pytest.mark.parametrize("status", [400, 401, 403, 404])
    async def test_definitive_status_is_not_retried(self, status):
        transport = StubTransport(error_response(status))
        client = make_client(transport)
        with pytest.raises(YouTubeApiError) as excinfo:
            await client._get("https://api.test/x", {})
        assert not isinstance(excinfo.value, YouTubeTransientError)
        assert len(transport.requests) == 1


class TestYppClassification:
    """A channel is only non-YPP when YouTube definitively refuses revenue metrics."""

    @staticmethod
    def _analytics_payload() -> dict:
        return {"columnHeaders": [{"name": "averageViewPercentage"}], "rows": [[42.0]]}

    async def test_permission_denied_classifies_non_ypp(self):
        transport = StubTransport(error_response(403), json_response(self._analytics_payload()))
        client = make_client(transport)
        analytics = await client.get_channel_analytics(date(2026, 1, 1), date(2026, 1, 8))
        assert analytics["ypp"] is False
        assert analytics["cpm"] == 0
        assert analytics["estimatedRedPartnerRevenue"] == {}

    async def test_transient_failure_does_not_classify_non_ypp(self):
        transport = StubTransport(error_response(503))
        client = make_client(transport)
        with pytest.raises(YouTubeTransientError):
            await client.get_channel_analytics(date(2026, 1, 1), date(2026, 1, 8))


class TestSearchCaching:
    async def test_empty_search_result_is_not_cached(self):
        transport = StubTransport(json_response({"items": []}))
        cache = SearchCache()
        client = make_client(transport, cache)
        assert await client._search_uploads("UC123", _cutoff()) == []
        assert cache.get("UC123") is None

    async def test_non_empty_search_result_is_cached(self):
        payload = {"items": [{"id": {"videoId": "vid1"}}]}
        transport = StubTransport(json_response(payload))
        cache = SearchCache()
        client = make_client(transport, cache)
        assert await client._search_uploads("UC123", _cutoff()) == ["vid1"]
        assert cache.get("UC123") == ["vid1"]

    async def test_failed_search_is_not_cached(self):
        transport = StubTransport(error_response(503))
        cache = SearchCache()
        client = make_client(transport, cache)
        with pytest.raises(YouTubeTransientError):
            await client._search_uploads("UC123", _cutoff())
        assert cache.get("UC123") is None


def _cutoff():
    from datetime import UTC, datetime

    return datetime(2026, 1, 1, tzinfo=UTC)


class TestReportingSeries:
    """Reporting analytics must never disturb the scoring inputs."""

    async def test_daily_reporting_nests_breakdowns_by_day(self):
        scalar = json_response(
            {
                "columnHeaders": [{"name": "day"}, {"name": "views"}, {"name": "videosAddedToPlaylists"}],
                "rows": [["2026-08-01", 100, 2], ["2026-08-02", 150, 1]],
            }
        )
        breakdown = json_response(
            {
                "columnHeaders": [
                    {"name": "deviceType"},
                    {"name": "day"},
                    {"name": "estimatedMinutesWatched"},
                ],
                "rows": [
                    ["DESKTOP", "2026-08-01", 40],
                    ["MOBILE", "2026-08-01", 60],
                    ["MOBILE", "2026-08-02", 90],
                ],
            }
        )
        empty = json_response({"columnHeaders": [], "rows": []})
        transport = StubTransport(scalar, breakdown, empty, empty, empty)
        client = make_client(transport)

        series = await client.get_video_daily_reporting(
            "vid1", is_ypp=False, start=date(2026, 8, 1), end=date(2026, 8, 2)
        )

        assert [entry["day"] for entry in series] == ["2026-08-01", "2026-08-02"]
        assert series[0]["views"] == 100
        assert series[0]["deviceTypeMinutes"] == {"DESKTOP": 40, "MOBILE": 60}
        assert series[1]["deviceTypeMinutes"] == {"MOBILE": 90}

    async def test_a_failed_breakdown_keeps_the_rest(self):
        scalar = json_response({"columnHeaders": [{"name": "day"}, {"name": "views"}], "rows": [["2026-08-01", 10]]})
        transport = StubTransport(scalar, error_response(403))
        client = make_client(transport)

        series = await client.get_video_daily_reporting(
            "vid1", is_ypp=False, start=date(2026, 8, 1), end=date(2026, 8, 1)
        )
        assert series[0]["views"] == 10
        assert "deviceTypeMinutes" not in series[0]

    async def test_channel_reporting_failure_leaves_scoring_metrics_intact(self):
        core = json_response(
            {"columnHeaders": [{"name": "cpm"}, {"name": "averageViewPercentage"}], "rows": [[2.0, 55.0]]}
        )
        daily = json_response(
            {
                "columnHeaders": [
                    {"name": "day"},
                    {"name": "views"},
                    {"name": "estimatedMinutesWatched"},
                    {"name": "estimatedRedPartnerRevenue"},
                ],
                "rows": [["2026-08-01", 10, 20, 0.5]],
            }
        )
        transport = StubTransport(core, daily, error_response(403))
        client = make_client(transport)

        analytics = await client.get_channel_analytics(date(2026, 8, 1), date(2026, 8, 1))

        assert analytics["ypp"] is True
        assert analytics["averageViewPercentage"] == 55.0
        assert analytics["estimatedRedPartnerRevenue"] == {"2026-08-01": 0.5}


class TestAnalyticsThrottle:
    async def test_analytics_requests_are_capped_per_client(self, monkeypatch):
        """Google's limit is per OAuth user, so the ceiling lives on the client."""
        import asyncio

        from bitcast.validator.youtube import api as api_module

        live = 0
        peak = 0

        class SlowTransport(StubTransport):
            async def handle_async_request(self, request):
                nonlocal live, peak
                live += 1
                peak = max(peak, live)
                await asyncio.sleep(0.01)
                live -= 1
                return json_response({"columnHeaders": [{"name": "views"}], "rows": [[1]]})

        client = make_client(SlowTransport(json_response({})))
        await asyncio.gather(
            *(client._analytics_query(date(2026, 8, 1), date(2026, 8, 1), ["views"]) for _ in range(20))
        )
        assert peak <= api_module.YT_MAX_CONCURRENT_ANALYTICS
        assert client.analytics_api_calls == 20


class TestAnalyticsRateLimit:
    """Google meters per project, so the pace is process-wide, not per client."""

    async def test_slots_are_spaced_and_shared_between_clients(self, monkeypatch):
        import asyncio

        from bitcast.validator.youtube import api as api_module

        # 600/min => one slot every 100ms. Asserting on the schedule rather than
        # the clock: the autouse no_sleep fixture patches asyncio.sleep away.
        limiter = api_module._RateLimiter(per_minute=600)
        monkeypatch.setattr(api_module, "_ANALYTICS_RATE_LIMITER", limiter)

        transport = StubTransport(json_response({"columnHeaders": [{"name": "views"}], "rows": [[1]]}))
        clients = [make_client(transport), make_client(transport)]
        started = asyncio.get_running_loop().time()
        await asyncio.gather(
            *(clients[i % 2]._analytics_query(date(2026, 8, 1), date(2026, 8, 1), ["views"]) for i in range(10))
        )
        # Ten queries across two clients must consume ten slots from one budget.
        assert limiter._next_slot >= started + 10 * 0.1 - 0.05

    async def test_zero_per_minute_disables_pacing(self):
        from bitcast.validator.youtube import api as api_module

        limiter = api_module._RateLimiter(per_minute=0)
        await limiter.acquire()  # must not hang or divide by zero
