"""Briefs filtering, publisher payloads and the TTL cache."""

import json
from datetime import date
from pathlib import Path

import httpx
import numpy as np
import pytest

from bitcast.utils.briefs import _is_active, get_briefs
from bitcast.utils.cache import JsonlCache, TTLCache
from bitcast.utils.publisher import Publisher, account_posting_payload, convert_numpy_types
from bitcast.validator.reward.models import AccountResult
from bitcast.validator.reward.orchestrator import ResultPublisher


class TestBriefActivity:
    BRIEF = {"id": "x", "start_date": "2026-07-01", "end_date": "2026-07-10"}

    def test_window_opens_after_reward_delay(self):
        assert not _is_active(self.BRIEF, today=date(2026, 7, 3))
        assert _is_active(self.BRIEF, today=date(2026, 7, 4))  # start + 3

    def test_window_extends_past_end_date(self):
        assert _is_active(self.BRIEF, today=date(2026, 7, 27))  # end + 14 + 3
        assert not _is_active(self.BRIEF, today=date(2026, 7, 28))

    def test_invalid_dates_excluded(self):
        assert not _is_active({"id": "bad", "start_date": "soon"}, today=date(2026, 7, 4))


class TestPublisherContract:
    """The orchestrator drives Publisher through the ResultPublisher protocol,
    and forward.py calls new_run() once per cycle — so it must be on both."""

    def test_publisher_satisfies_the_result_publisher_protocol(self, fake_wallet):
        publisher: ResultPublisher = Publisher(fake_wallet)
        assert isinstance(publisher, ResultPublisher)

    def test_new_run_rotates_the_run_id(self, fake_wallet, monkeypatch):
        publisher = Publisher(fake_wallet)
        first = publisher.run_id
        assert first.startswith("vali_")

        stamps = iter(["20260731_120000", "20260731_160000"])
        monkeypatch.setattr(Publisher, "_generate_run_id", lambda self: f"vali_x_{next(stamps)}")
        second = publisher.new_run()
        assert second != first
        assert publisher.run_id == second
        assert publisher.new_run() != second


class TestPublisherPayloads:
    def test_numpy_conversion(self):
        converted = convert_numpy_types({"a": np.int64(3), "b": [np.float32(1.5), np.array([1, 2])]})
        assert converted == {"a": 3, "b": [1.5, [1, 2]]}

    def test_account_payload_strips_bulky_fields(self):
        account = AccountResult(
            account_id="account_1",
            videos={
                "vid": {
                    "details": {"description": "long text", "transcript": "longer", "title": "T"},
                    "brief_metrics": {"b": {"usd_target": 1.0}},
                }
            },
            scores={"b": 1.0},
        )
        payload = account_posting_payload(account)
        video = payload["videos"]["vid"]
        assert "description" not in video["details"] and "transcript" not in video["details"]
        assert video["per_video_metrics"] == {"b": {"usd_target": 1.0}}
        assert "brief_metrics" not in video
        assert payload["scores"] == {"b": 1.0}


class TestTTLCache:
    def test_set_get_and_expiry(self, monkeypatch):
        clock = {"now": 0.0}
        monkeypatch.setattr("bitcast.utils.cache.time.monotonic", lambda: clock["now"])
        cache = TTLCache(ttl=10)
        cache.set("k", "v")
        assert cache.get("k") == "v"
        clock["now"] = 11.0
        assert cache.get("k") is None

    def test_sliding_expiry_refreshes_on_read(self, monkeypatch):
        clock = {"now": 0.0}
        monkeypatch.setattr("bitcast.utils.cache.time.monotonic", lambda: clock["now"])
        cache = TTLCache(ttl=10, sliding=True)
        cache.set("k", "v")
        clock["now"] = 8.0
        assert cache.get("k") == "v"  # read refreshes expiry
        clock["now"] = 17.0
        assert cache.get("k") == "v"
        clock["now"] = 28.0
        assert cache.get("k") is None


class TestJsonlCache:
    """Disk-backed cache: same semantics as TTLCache plus restart survival.

    Uses a plain JSONL file instead of SQLite/diskcache, so it's NFS-safe and
    editable from any host sharing the filesystem.
    """

    def test_set_get_and_expiry(self, tmp_path: Path, monkeypatch):
        clock = {"now": 1000.0}
        monkeypatch.setattr("bitcast.utils.cache.time.time", lambda: clock["now"])
        cache = JsonlCache(tmp_path / "c.jsonl", ttl=10)
        cache.set("k", "v")
        assert cache.get("k") == "v"
        clock["now"] = 1011.0
        assert cache.get("k") is None

    def test_sliding_refresh_on_read(self, tmp_path: Path, monkeypatch):
        clock = {"now": 1000.0}
        monkeypatch.setattr("bitcast.utils.cache.time.time", lambda: clock["now"])
        cache = JsonlCache(tmp_path / "c.jsonl", ttl=10, sliding=True)
        cache.set("k", "v")
        clock["now"] = 1008.0
        assert cache.get("k") == "v"
        clock["now"] = 1017.0
        assert cache.get("k") == "v"  # refresh extended expiry
        clock["now"] = 1028.0
        assert cache.get("k") is None

    def test_survives_restart(self, tmp_path: Path, monkeypatch):
        """Entries written by one cache instance are visible to a fresh one."""
        clock = {"now": 1000.0}
        monkeypatch.setattr("bitcast.utils.cache.time.time", lambda: clock["now"])
        cache_path = tmp_path / "c.jsonl"
        cache_a = JsonlCache(cache_path, ttl=3600)
        cache_a.set("prompt-1", [True, "matched"])
        cache_a.set("prompt-2", [False, "no match"])

        # New process pointing at the same file.
        cache_b = JsonlCache(cache_path, ttl=3600)
        assert cache_b.get("prompt-1") == [True, "matched"]
        assert cache_b.get("prompt-2") == [False, "no match"]
        assert cache_b.get("prompt-3") is None

    def test_clear_purges_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("bitcast.utils.cache.time.time", lambda: 1000.0)
        cache_path = tmp_path / "c.jsonl"
        cache = JsonlCache(cache_path, ttl=3600)
        cache.set("k", "v")
        cache.clear()
        fresh = JsonlCache(cache_path, ttl=3600)
        assert fresh.get("k") is None

    def test_complex_value_roundtrip(self, tmp_path: Path, monkeypatch):
        """LLM cache stores (bool, str); search cache stores list[str].

        JSON converts tuples to lists, so callers unpack via indexing or
        sequence unpacking (``a, b = cache.get(key)``), not isinstance(tuple).
        """
        monkeypatch.setattr("bitcast.utils.cache.time.time", lambda: 1000.0)
        cache_path = tmp_path / "c.jsonl"
        cache = JsonlCache(cache_path, ttl=3600)
        cache.set("llm-key", (True, "All requirements met."))
        cache.set("search-key", ["vid1", "vid2", "vid3"])
        cache.set("injection-key", False)
        fresh = JsonlCache(cache_path, ttl=3600)
        # Tuple → list under JSON, but unpacking works identically.
        llm_val = fresh.get("llm-key")
        assert llm_val == [True, "All requirements met."]
        a, b = llm_val  # sequence unpacking still works
        assert a is True and b == "All requirements met."
        assert fresh.get("search-key") == ["vid1", "vid2", "vid3"]
        assert fresh.get("injection-key") is False

    def test_compact_deduplicates(self, tmp_path: Path, monkeypatch):
        """Multiple writes of the same key leave stale lines; compact rewrites."""
        clock = {"now": 1000.0}
        monkeypatch.setattr("bitcast.utils.cache.time.time", lambda: clock["now"])
        cache_path = tmp_path / "c.jsonl"
        cache = JsonlCache(cache_path, ttl=3600)
        cache.set("k", "v1")
        cache.set("k", "v2")
        cache.set("k", "v3")
        # File should have 3 lines (all appends).
        assert len(cache_path.read_text().strip().split("\n")) == 3
        n = cache.compact()
        assert n == 1
        # File now has 1 line, value is the latest.
        assert len(cache_path.read_text().strip().split("\n")) == 1
        assert cache.get("k") == "v3"

    def test_malformed_lines_skipped(self, tmp_path: Path, monkeypatch):
        """A corrupt line (partial write / NFS interleave) doesn't crash the reader."""
        monkeypatch.setattr("bitcast.utils.cache.time.time", lambda: 1000.0)
        cache_path = tmp_path / "c.jsonl"
        cache_path.write_text(
            '{"key": "good", "value": 1, "stored_at": 1000.0}\n'
            "THIS LINE IS GARBAGE\n"
            '{"key": "also-good", "value": 2, "stored_at": 1000.0}\n'
        )
        cache = JsonlCache(cache_path, ttl=3600)
        assert cache.get("good") == 1
        assert cache.get("also-good") == 2

    def test_compact_drops_expired_entries(self, tmp_path: Path, monkeypatch):
        """Compaction filters out entries past their TTL, not just dedupes writes."""
        clock = {"now": 1000.0}
        monkeypatch.setattr("bitcast.utils.cache.time.time", lambda: clock["now"])
        cache_path = tmp_path / "c.jsonl"
        cache = JsonlCache(cache_path, ttl=10)
        cache.set("fresh", "v1")
        cache.set("stale", "v2")
        # Advance past TTL for one entry, then compact.
        clock["now"] = 1011.0
        # Touch "fresh" so it stays alive (sliding refresh isn't the default;
        # instead, simulate a recent write).
        cache.set("fresh", "v1")
        n = cache.compact()
        assert n == 1  # only "fresh" survives
        fresh = JsonlCache(cache_path, ttl=10)
        assert fresh.get("fresh") == "v1"
        assert fresh.get("stale") is None


class TestBriefsDiskFallback:
    """When the briefs server is unreachable, fall back to the on-disk cache."""

    @pytest.fixture(autouse=True)
    def _reset_briefs_module_cache(self):
        # Each test starts with a clean in-process briefs cache.
        import bitcast.utils.briefs as briefs_mod

        briefs_mod._last_good_briefs = None
        yield
        briefs_mod._last_good_briefs = None

    async def test_disk_fallback_used_when_server_unreachable(self, tmp_path: Path, monkeypatch):
        cache_path = tmp_path / "briefs.json"
        cached = [{"id": "b1", "start_date": "2026-01-01", "end_date": "2030-01-01"}]
        cache_path.write_text(json.dumps(cached))

        async def boom(*args, **kwargs):
            raise httpx.ConnectError("server down")

        monkeypatch.setattr("bitcast.utils.briefs.request_with_retry", boom)
        briefs = await get_briefs(include_all=True, cache_path=cache_path)
        assert briefs == cached

    async def test_no_cache_no_server_raises(self, monkeypatch):
        async def boom(*args, **kwargs):
            raise httpx.ConnectError("server down")

        monkeypatch.setattr("bitcast.utils.briefs.request_with_retry", boom)
        with pytest.raises(ConnectionError):
            await get_briefs(include_all=True)
