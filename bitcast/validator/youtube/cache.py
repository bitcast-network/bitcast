"""Caching and per-cycle state for YouTube evaluation."""

import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import bittensor as bt

from bitcast.config import YOUTUBE_SEARCH_CACHE_TTL, YT_LOOKBACK
from bitcast.utils.cache import JsonlCache, TTLCache


class SearchCache(TTLCache):
    """Caches fallback search results per channel — search costs 100 API credits.

    Pass ``cache_path`` to persist across restarts to a JSONL file (avoids
    burning 100 YouTube credits per channel on every validator cold start).
    """

    def __init__(self, cache_path: Path | None = None) -> None:
        self._disk_cache: JsonlCache | None = (
            JsonlCache(cache_path, ttl=YOUTUBE_SEARCH_CACHE_TTL) if cache_path is not None else None
        )
        super().__init__(ttl=YOUTUBE_SEARCH_CACHE_TTL)

    def get(self, key, default=None):
        hot = super().get(key, default)
        if hot is not default:
            return hot
        if self._disk_cache is not None:
            return self._disk_cache.get(key, default)
        return default

    def set(self, key, value) -> None:
        super().set(key, value)
        if self._disk_cache is not None:
            self._disk_cache.set(key, value)

    def compact(self) -> int:
        """Dedupe the on-disk JSONL (no-op when no disk cache is configured)."""
        if self._disk_cache is None:
            return 0
        return self._disk_cache.compact()


class CycleState:
    """Per-reward-cycle state: prevents the same video scoring under multiple accounts."""

    def __init__(self) -> None:
        self._scored_video_ids: set[str] = set()

    def is_video_scored(self, video_id: str) -> bool:
        return video_id in self._scored_video_ids

    def mark_video_scored(self, video_id: str) -> None:
        self._scored_video_ids.add(video_id)

    def reset(self) -> None:
        self._scored_video_ids.clear()


class HistoricalVideoRegistry:
    """JSONL registry of previously matched videos so they stay scoreable.

    Only consulted outside eco mode, where older matched videos are re-added
    to the processing list for up to ``YT_LOOKBACK`` days.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._recorded: set[tuple[str, str]] = set()

    def record_match(self, video_id: str, channel_id: str, brief_id: str) -> None:
        """Append a matched video, deduplicated per (video, channel) in-process."""
        key = (video_id, channel_id)
        if key in self._recorded:
            return
        self._recorded.add(key)
        entry = {
            "video_id": video_id,
            "channel_id": channel_id,
            "brief_id": brief_id,
            "date_first_matched": datetime.now(UTC).strftime("%Y-%m-%d"),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as handle:
                handle.write(json.dumps(entry) + "\n")
        except OSError as err:
            bt.logging.warning(f"Could not record historical video {video_id}: {err}")

    def videos_for_channel(self, channel_id: str, max_age_days: int = YT_LOOKBACK) -> list[str]:
        """Video ids matched for this channel within the age window, deduplicated."""
        if not self.path.exists():
            return []
        cutoff = datetime.now(UTC).date() - timedelta(days=max_age_days)
        video_ids: list[str] = []
        try:
            with self.path.open() as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    if entry.get("channel_id") != channel_id:
                        continue
                    matched = datetime.strptime(entry["date_first_matched"], "%Y-%m-%d").date()
                    if matched >= cutoff and entry["video_id"] not in video_ids:
                        video_ids.append(entry["video_id"])
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as err:
            bt.logging.warning(f"Could not read historical videos: {err}")
        return video_ids

    def compact(self, max_age_days: int = YT_LOOKBACK) -> int:
        """Rewrite the JSONL keeping one entry per ``(video_id, channel_id)``.

        Without this the file grows unbounded: every validator restart loses
        the in-process dedup set, so a video that matches again gets a new
        line. Older-than-``max_age_days`` entries are dropped entirely.
        Returns the number of entries written. Safe to call on a running
        validator — atomic tmp+rename, no in-memory state required.
        """
        if not self.path.exists():
            return 0
        cutoff = datetime.now(UTC).date() - timedelta(days=max_age_days)
        latest: dict[tuple[str, str], dict] = {}
        try:
            with self.path.open() as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    key = (entry.get("video_id"), entry.get("channel_id"))
                    if key[0] is None or key[1] is None:
                        continue
                    try:
                        matched = datetime.strptime(entry["date_first_matched"], "%Y-%m-%d").date()
                    except (KeyError, ValueError):
                        continue
                    if matched < cutoff:
                        continue
                    # Last-write-wins within the file (later lines override).
                    latest[key] = entry
        except OSError as err:
            bt.logging.warning(f"Could not read historical videos for compaction: {err}")
            return 0
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".history_")
            with os.fdopen(fd, "w") as handle:
                for entry in latest.values():
                    handle.write(json.dumps(entry) + "\n")
            os.replace(tmp, self.path)
        except OSError as err:
            bt.logging.warning(f"Historical-video compaction write failed: {err}")
            return 0
        # Rebuild the in-process dedup set so the next match for an existing
        # pair doesn't double-append within this process.
        self._recorded = set(latest.keys())
        return len(latest)
