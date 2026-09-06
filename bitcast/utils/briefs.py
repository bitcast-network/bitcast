"""Fetch active briefs from the Bitcast briefs server.

A successful fetch is mirrored to ``cache_path`` (when provided) so a subsequent
cold start can fall back to the on-disk copy if the briefs server is unreachable.
This matches v1's behaviour and prevents the validator from refusing to start
during a briefs-server outage.
"""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import bittensor as bt
import httpx

from bitcast.config import YT_REWARD_DELAY, YT_SCORING_WINDOW, get_settings
from bitcast.http import request_with_retry

_REQUEST_TIMEOUT = 30.0

# Last successful response, used as an in-process fallback and as the source of
# truth for the on-disk cache. Survives across calls within a single run.
_last_good_briefs: list[dict] | None = None


async def get_briefs(include_all: bool = False, cache_path: Path | None = None) -> list[dict]:
    """Fetch briefs, filtered to those currently inside their scoring window.

    A brief is active from ``start_date + reward delay`` until
    ``end_date + scoring window + reward delay``, because analytics lag
    realtime and videos keep scoring after the brief closes.

    Falls back to (in order): in-process cache, on-disk cache at ``cache_path``.

    Raises:
        ConnectionError: If the server is unreachable and no cached briefs exist
            in memory or on disk.
    """
    global _last_good_briefs
    endpoint = get_settings().briefs_endpoint
    try:
        async with httpx.AsyncClient() as client:
            response = await request_with_retry(client, "GET", endpoint, timeout=_REQUEST_TIMEOUT, label="briefs")
            response.raise_for_status()
            data = response.json()
            briefs = data.get("items") or []
            _last_good_briefs = briefs
            if cache_path is not None:
                _persist_briefs(cache_path, briefs)
    except (httpx.HTTPError, TimeoutError) as err:
        briefs = _fall_back_briefs(cache_path, err)

    if include_all:
        return briefs
    return [brief for brief in briefs if _is_active(brief)]


def _fall_back_briefs(cache_path: Path | None, err: Exception) -> list[dict]:
    """Use in-memory cache, then on-disk cache, then raise."""
    global _last_good_briefs
    if _last_good_briefs is not None:
        bt.logging.warning(f"Briefs server unreachable ({err}); using in-memory cached briefs.")
        return _last_good_briefs
    if cache_path is not None and cache_path.exists():
        try:
            with cache_path.open() as handle:
                briefs = json.load(handle)
            if isinstance(briefs, list):
                _last_good_briefs = briefs
                bt.logging.warning(f"Briefs server unreachable ({err}); using on-disk cached briefs.")
                return briefs
        except (OSError, json.JSONDecodeError) as load_err:
            bt.logging.warning(f"On-disk briefs cache unreadable: {load_err}")
    raise ConnectionError(f"Briefs server unreachable and no cached briefs: {err}") from err


def _persist_briefs(cache_path: Path, briefs: list[dict]) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
        with tmp.open("w") as handle:
            json.dump(briefs, handle)
        tmp.replace(cache_path)
    except OSError as err:
        bt.logging.warning(f"Could not persist briefs to {cache_path}: {err}")


def _is_active(brief: dict, today: date | None = None) -> bool:
    today = today or datetime.now(UTC).date()
    try:
        start = date.fromisoformat(brief["start_date"])
        end = date.fromisoformat(brief["end_date"])
    except (KeyError, ValueError):
        bt.logging.warning(f"Brief {brief.get('id')} has invalid dates; skipping.")
        return False
    window_start = start + timedelta(days=YT_REWARD_DELAY)
    window_end = end + timedelta(days=YT_SCORING_WINDOW + YT_REWARD_DELAY)
    return window_start <= today <= window_end
