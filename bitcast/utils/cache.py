"""In-memory and disk-backed TTL caches for YouTube search, LLM, and briefs.

``TTLCache``  - process-local dict that expires entries after ``ttl`` s.
``JsonlCache`` - same API, but persists entries to a JSON Lines file so they
                survive validator restarts. Append-only, NFS-safe, and
                editable from any host sharing the filesystem.

JSONL was chosen over SQLite/diskcache because the validator's cache lives on
EFS (NFSv4). SQLite WAL mode relies on mmap'd shared-memory for cross-process
coordination, which NFS does not guarantee — making the cache un-modifiable
while the validator holds an open handle. JSONL append-only writes are atomic
under POSIX (for lines < PIPE_BUF) and require no coordination between hosts.
"""

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

# Sentinel distinguishing "absent" from a stored ``None``. Typed ``Any`` so it
# can stand in for a cached value of any type without widening call sites.
_MISSING: Any = object()


class TTLCache:
    """Dict-like cache whose entries expire ``ttl`` seconds after their last write.

    ``sliding=True`` refreshes an entry's expiry on read, matching the v1
    disk-cache behaviour for LLM responses.
    """

    def __init__(self, ttl: float, sliding: bool = False) -> None:
        self.ttl = ttl
        self.sliding = sliding
        self._entries: dict[Any, tuple[Any, float]] = {}

    def get(self, key: Any, default: Any = None) -> Any:
        entry = self._entries.get(key, _MISSING)
        if entry is _MISSING:
            return default
        value, stored_at = entry
        now = time.monotonic()
        if now - stored_at > self.ttl:
            del self._entries[key]
            return default
        if self.sliding:
            self._entries[key] = (value, now)
        return value

    def set(self, key: Any, value: Any) -> None:
        self._entries[key] = (value, time.monotonic())

    def __contains__(self, key: Any) -> bool:
        return self.get(key, _MISSING) is not _MISSING

    def clear(self) -> None:
        self._entries.clear()


class JsonlCache:
    """Disk-backed TTL cache using a JSON Lines file.

    Same semantics as :class:`TTLCache` (fixed or sliding expiry, ``get`` /
    ``set`` / ``__contains__`` / ``clear``), but every entry is also appended to
    a JSONL file at ``cache_path`` so a validator restart, redeploy, or
    container swap does not throw away expensive LLM responses or YouTube API
    results.

    **Format** (one JSON object per line)::

        {"key": "<prompt text>", "value": <any json>, "stored_at": 1784739120.0}

    On startup the file is scanned once to build an in-memory dict; subsequent
    reads are O(1) dict lookups. Writes append a single line and update the
    in-memory dict atomically (under a lock). The file is append-only, so it
    can be read, appended to, or replaced from any host sharing the filesystem
    (e.g. a cache-admin EC2) without coordinating with the running validator.

    **NFS safety:** POSIX guarantees atomic writes for appends smaller than
    ``PIPE_BUF`` (4096 bytes). For larger lines (long LLM prompts), concurrent
    writers from *different* processes could interleave bytes and corrupt a
    line — but the reader treats malformed lines as warnings and skips them,
    so the system degrades gracefully rather than corrupting good entries.
    In practice the validator is the sole writer during normal operation;
    the admin box only writes during migration or manual injection.

    **JSON type note:** tuples are stored as JSON arrays and read back as
    lists. Callers that unpack ``value`` (e.g. ``a, b = cache.get(key)``) are
    unaffected; callers that type-check ``isinstance(value, tuple)`` must use
    ``isinstance(value, (list, tuple))`` or ``isinstance(value, Sequence)``.

    Values must be JSON-serializable (dicts, lists, primitives, nested combos).
    """

    def __init__(
        self,
        cache_path: Path,
        ttl: float,
        sliding: bool = False,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.ttl = ttl
        self.sliding = sliding
        self._lock = threading.Lock()
        self._entries: dict[Any, tuple[Any, float]] = {}
        self._load()

    def _load(self) -> None:
        """Scan the JSONL file and populate ``_entries`` (latest entry per key wins)."""
        if not self.cache_path.exists():
            return
        try:
            with self.cache_path.open() as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        # Malformed line (partial write / concurrent interleave).
                        # Skip it — better to lose one entry than crash the validator.
                        continue
                    key = entry.get("key", _MISSING)
                    if key is _MISSING:
                        continue
                    self._entries[key] = (entry["value"], float(entry["stored_at"]))
        except OSError:
            # File unreadable — start with an empty cache rather than crashing.
            pass

    def _now(self) -> float:
        return time.time()

    def _expired(self, stored_at: float) -> bool:
        return self._now() - stored_at > self.ttl

    def _append(self, key: Any, value: Any, stored_at: float) -> None:
        """Append one entry to the JSONL file (thread-safe, best-effort)."""
        line = json.dumps({"key": key, "value": value, "stored_at": stored_at}) + "\n"
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self.cache_path.open("a") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            # Disk full, EFS hiccup, etc. — keep the in-memory entry so the
            # current cycle works; the write just won't survive a restart.
            pass

    def get(self, key: Any, default: Any = None) -> Any:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return default
            value, stored_at = entry
            if self._expired(stored_at):
                del self._entries[key]
                return default
            if self.sliding:
                now = self._now()
                self._entries[key] = (value, now)
                self._append(key, value, now)
            return value

    def set(self, key: Any, value: Any) -> None:
        now = self._now()
        with self._lock:
            self._entries[key] = (value, now)
        self._append(key, value, now)

    def __contains__(self, key: Any) -> bool:
        return self.get(key, _MISSING) is not _MISSING

    def clear(self) -> None:
        """Truncate the file and wipe in-memory entries."""
        with self._lock:
            self._entries.clear()
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic truncation: write empty to tmp, rename.
            fd, tmp = tempfile.mkstemp(dir=str(self.cache_path.parent), prefix=".cache_")
            os.close(fd)
            os.replace(tmp, self.cache_path)
        except OSError:
            pass

    def compact(self) -> int:
        """Rewrite the file keeping only the latest non-expired entry per key.

        Returns the number of entries written. Safe to call from any host;
        uses tmp + rename for atomicity. The validator can call this
        periodically to prevent unbounded growth from sliding-refresh appends.
        """
        with self._lock:
            live = {
                key: (value, stored_at)
                for key, (value, stored_at) in self._entries.items()
                if not self._expired(stored_at)
            }
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self.cache_path.parent), prefix=".cache_")
            with os.fdopen(fd, "w") as handle:
                for key, (value, stored_at) in live.items():
                    handle.write(json.dumps({"key": key, "value": value, "stored_at": stored_at}) + "\n")
            os.replace(tmp, self.cache_path)
        except OSError:
            pass
        return len(live)
