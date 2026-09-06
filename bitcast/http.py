"""The ONE async HTTP retry helper (replaces bespoke aiohttp implementations).

Retries on network errors and transient statuses {429, 5xx}. Deterministic
error statuses (401/403/404) are returned to the caller — retrying them wastes
time and each client has its own policy for them (fail open, raise, fallback).
The final response is always returned, even if it still carries a retryable
status after all attempts, so callers can decide.
"""

import asyncio
from typing import Any, Literal

import bittensor as bt
import httpx

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


def _retry_after_seconds(response: httpx.Response, default: float) -> float:
    """Honor a numeric Retry-After header (seconds); fall back to ``default``."""
    raw = response.headers.get("Retry-After")
    if raw:
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            pass
    return default


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json: Any | None = None,
    data: Any | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    attempts: int = 3,
    retry_delay: float = 2.0,
    backoff: Literal["fixed", "exponential"] = "fixed",
    honor_retry_after: bool = False,
    label: str = "request",
) -> httpx.Response:
    """Issue ``method url`` with bounded retries on network errors and {429, 5xx}.

    Args:
        client: An ``httpx.AsyncClient`` owned by the caller (lifecycle managed
            at the call site so a session can be reused across requests).
        method: HTTP method (``"GET"``, ``"POST"``, …).
        url: Target URL.
        params: Optional query parameters.
        json: Optional JSON body.
        data: Optional form-encoded body.
        headers: Optional request headers.
        timeout: Per-request timeout in seconds.
        attempts: Total attempts (first try included).
        retry_delay: Base delay between attempts.
        backoff: ``fixed`` sleeps ``retry_delay`` each time; ``exponential``
            sleeps ``retry_delay * 2**attempt_index``.
        honor_retry_after: On 429, prefer a numeric Retry-After header.
        label: Human-readable tag for log lines.

    Returns:
        The final response — possibly still an error status once attempts are
        exhausted; callers decide whether that raises, falls back, or fails open.

    Raises:
        httpx.HTTPError: Only if the final attempt fails at the network level.
    """
    for attempt in range(attempts):
        is_last = attempt + 1 >= attempts
        delay = retry_delay * (2**attempt) if backoff == "exponential" else retry_delay
        try:
            response = await client.request(
                method, url, params=params, json=json, data=data, headers=headers, timeout=timeout
            )
        except httpx.HTTPError as e:
            if is_last:
                raise
            bt.logging.warning(
                f"{label} network error (attempt {attempt + 1}/{attempts}), retrying in {delay:.1f}s: {e}"
            )
            await asyncio.sleep(delay)
            continue

        if response.status_code in RETRYABLE_STATUSES and not is_last:
            if response.status_code == 429 and honor_retry_after:
                delay = _retry_after_seconds(response, delay)
            bt.logging.warning(
                f"{label} {response.status_code} (attempt {attempt + 1}/{attempts}), retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)
            continue

        return response

    raise AssertionError("unreachable: the final attempt either returns or raises")  # pragma: no cover
