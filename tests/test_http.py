"""Tests for the request_with_retry helper in bitcast/http.py.

Mock httpx responses: success on first try, retry on 429, retry on 5xx,
honor Retry-After, and exhaustion after max retries. Also covers network
errors (ConnectError) and non-retryable statuses (404) returned immediately.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from bitcast.http import request_with_retry


def _response(status_code: int, headers: dict[str, str] | None = None) -> httpx.Response:
    """Build a minimal httpx.Response for the given status."""
    return httpx.Response(status_code=status_code, headers=headers or {}, request=httpx.Request("GET", "http://x"))


def _client(responses):
    """Build a fake client whose .request returns ``responses`` in order."""
    client = MagicMock(spec=httpx.AsyncClient)
    client.request = AsyncMock(side_effect=list(responses))
    return client


class TestSuccess:
    async def test_success_on_first_try(self):
        client = _client([_response(200)])
        resp = await request_with_retry(client, "GET", "http://x", label="t", retry_delay=0)
        assert resp.status_code == 200
        assert client.request.await_count == 1

    async def test_non_retryable_returned_immediately(self):
        """404 is deterministic — no retry, returned right away."""
        client = _client([_response(404)])
        resp = await request_with_retry(client, "GET", "http://x", label="t", retry_delay=0)
        assert resp.status_code == 404
        assert client.request.await_count == 1


class TestRetryOnStatus:
    async def test_retry_on_429_then_success(self):
        client = _client([_response(429), _response(200)])
        resp = await request_with_retry(client, "GET", "http://x", attempts=3, retry_delay=0, label="t")
        assert resp.status_code == 200
        assert client.request.await_count == 2

    async def test_retry_on_5xx_then_success(self):
        client = _client([_response(503), _response(500), _response(200)])
        resp = await request_with_retry(client, "GET", "http://x", attempts=3, retry_delay=0, label="t")
        assert resp.status_code == 200
        assert client.request.await_count == 3

    async def test_max_retries_exceeded_returns_last(self):
        """Exhausting attempts returns the final (still-error) response."""
        client = _client([_response(503), _response(503), _response(503)])
        resp = await request_with_retry(client, "GET", "http://x", attempts=3, retry_delay=0, label="t")
        assert resp.status_code == 503
        assert client.request.await_count == 3


class TestRetryAfter:
    async def test_honor_retry_after_header(self, monkeypatch):
        """A numeric Retry-After header is used as the sleep delay on 429."""
        sleeps: list[float] = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr("bitcast.http.asyncio.sleep", fake_sleep)
        client = _client([_response(429, {"Retry-After": "7"}), _response(200)])
        await request_with_retry(
            client, "GET", "http://x", attempts=3, retry_delay=2.0, honor_retry_after=True, label="t"
        )
        # The Retry-After value (7.0) overrides the default retry_delay (2.0).
        assert sleeps == [7.0]

    async def test_default_delay_without_header(self, monkeypatch):
        sleeps: list[float] = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr("bitcast.http.asyncio.sleep", fake_sleep)
        client = _client([_response(429), _response(200)])
        await request_with_retry(client, "GET", "http://x", attempts=3, retry_delay=2.0, label="t")
        assert sleeps == [2.0]


class TestNetworkErrors:
    async def test_network_error_retry_then_success(self):
        client = _client([httpx.ConnectError("boom"), _response(200)])
        resp = await request_with_retry(client, "GET", "http://x", attempts=3, retry_delay=0, label="t")
        assert resp.status_code == 200
        assert client.request.await_count == 2

    async def test_network_error_exhausted_raises(self):
        client = _client([httpx.ConnectError("boom"), httpx.ConnectError("boom"), httpx.ConnectError("boom")])
        with pytest.raises(httpx.ConnectError):
            await request_with_retry(client, "GET", "http://x", attempts=3, retry_delay=0, label="t")
        assert client.request.await_count == 3


class TestBackoff:
    async def test_exponential_backoff(self, monkeypatch):
        """Exponential mode multiplies the delay by 2**attempt each retry."""
        sleeps: list[float] = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr("bitcast.http.asyncio.sleep", fake_sleep)
        client = _client([_response(503), _response(503), _response(200)])
        await request_with_retry(
            client, "GET", "http://x", attempts=3, retry_delay=1.0, backoff="exponential", label="t"
        )
        # attempt 0 → 1*2^0 = 1.0; attempt 1 → 1*2^1 = 2.0
        assert sleeps == [1.0, 2.0]
