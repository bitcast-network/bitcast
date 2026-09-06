"""HistoricalVideoRegistry: append-only JSONL with restart-safe dedup."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from bitcast.validator.youtube.cache import HistoricalVideoRegistry


def _entry(video_id: str, channel_id: str, brief_id: str, days_ago: int = 0) -> dict:
    matched = (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    return {
        "video_id": video_id,
        "channel_id": channel_id,
        "brief_id": brief_id,
        "date_first_matched": matched,
    }


class TestHistoricalVideoRegistryCompact:
    def test_compact_dedupes_repeated_pairs(self, tmp_path: Path):
        """Same (video, channel) appended on every restart collapses to one line."""
        path = tmp_path / "historical_videos.jsonl"
        reg = HistoricalVideoRegistry(path)
        # Simulate three validator restarts each re-recording the same match.
        for _ in range(3):
            fresh_reg = HistoricalVideoRegistry(path)
            fresh_reg.record_match("vid1", "chanA", "brief1")
        # File has three lines for the same pair.
        assert len(path.read_text().strip().splitlines()) == 3

        n = reg.compact()
        assert n == 1
        # File now has exactly one line.
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["video_id"] == "vid1"
        assert entry["channel_id"] == "chanA"

    def test_compact_drops_entries_outside_lookback_window(self, tmp_path: Path):
        """Entries older than YT_LOOKBACK (default 60d) are pruned by compact."""
        path = tmp_path / "historical_videos.jsonl"
        # Write one recent and one ancient entry directly.
        path.write_text(
            json.dumps(_entry("vid_recent", "chanA", "b1", days_ago=1))
            + "\n"
            + json.dumps(_entry("vid_old", "chanA", "b1", days_ago=365))
            + "\n"
        )
        reg = HistoricalVideoRegistry(path)
        n = reg.compact()
        assert n == 1  # the ancient entry is dropped
        lines = path.read_text().strip().splitlines()
        assert json.loads(lines[0])["video_id"] == "vid_recent"

    def test_compact_noop_on_missing_file(self, tmp_path: Path):
        """Compacting a registry whose file doesn't exist is a safe no-op."""
        reg = HistoricalVideoRegistry(tmp_path / "does_not_exist.jsonl")
        assert reg.compact() == 0

    def test_compact_rebuilds_inprocess_dedup_set(self, tmp_path: Path):
        """After compaction, a subsequent record_match for the same pair is a no-op.

        Without this, the in-memory set would be empty post-compact, and the
        very next call would re-append the line we just deduped.
        """
        path = tmp_path / "historical_videos.jsonl"
        reg = HistoricalVideoRegistry(path)
        reg.record_match("vid1", "chanA", "b1")
        reg.compact()
        # Simulate a fresh match call for the same pair within the same process.
        before = len(path.read_text().strip().splitlines())
        reg.record_match("vid1", "chanA", "b1")
        after = len(path.read_text().strip().splitlines())
        assert before == after  # no new line written
