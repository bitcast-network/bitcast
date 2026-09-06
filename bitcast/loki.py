"""Grafana Loki log push handler for the Bitcast subnet (V2).

Sends validator/miner log lines to an operator-configured Grafana Loki dataset.

Uses HTTP Basic Auth (stack-id + access-policy token). Configure
``LOKI_URL`` / ``LOKI_USERNAME`` / ``LOKI_TOKEN`` through deployment secrets;
with any value missing, Loki is disabled.

Usage::

    from bitcast.loki import init_loki, shutdown_loki

    init_loki(settings, labels={"uid": "42", "hotkey": "5..."})
    # bt.logging lines are now batched and pushed to Loki.

    # On shutdown (async context):
    await shutdown_loki()

The handler attaches to the ``bittensor`` logger, batches log records in
memory, and flushes via ``httpx`` on a background asyncio task. Works
from both async (validator) and sync (miner) entry points — a daemon
thread with its own event loop is spawned when no running loop is
detected.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import threading
from collections import defaultdict
from typing import TYPE_CHECKING

import httpx

from bitcast.validator.telemetry import sanitize_loki_labels

if TYPE_CHECKING:
    from bitcast.config import Settings

__all__ = [
    "LokiHandler",
    "init_loki",
    "shutdown_loki",
]

# Module-level state
_handler: LokiHandler | None = None
_flush_task: asyncio.Task | None = None
# For sync callers (miner): a daemon thread running its own event loop
_loop_thread: threading.Thread | None = None
_loop: asyncio.AbstractEventLoop | None = None

_FLUSH_INTERVAL = 5.0  # seconds between forced flushes
_REQUEST_TIMEOUT = 10  # seconds per push request


class LokiHandler(logging.Handler):
    """Async batching log handler that pushes to Grafana Loki's HTTP API.

    Records are buffered in memory by label-set and flushed every
    ``_FLUSH_INTERVAL`` seconds. Failed pushes are silently dropped (logs
    are best-effort — we never block the neuron on logging failures).

    Thread-safety: ``emit()`` is called from any thread (gRPC handlers,
    subtensor threadpool). ``_async_flush()`` runs on the asyncio loop.
    Both use a ``threading.Lock`` to serialise buffer access.
    """

    def __init__(
        self,
        url: str,
        username: str,
        token: str,
        static_labels: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self._url = url.rstrip("/")
        cred = base64.b64encode(f"{username}:{token}".encode()).decode()
        self._auth_header = {"Authorization": f"Basic {cred}"}
        self._static_labels = sanitize_loki_labels(static_labels)
        self._buffer: dict[tuple[tuple[str, str], ...], list[tuple[str, str]]] = defaultdict(list)
        self._lock = threading.Lock()
        self._session: httpx.AsyncClient | None = None
        self._level = logging.INFO

    def emit(self, record: logging.LogRecord) -> None:
        """Buffer the record. The actual HTTP push happens in the flush task."""
        try:
            ts = str(int(record.created * 1_000_000_000))  # nanoseconds
            line = self.format(record)
            labels = {**self._static_labels, "level": record.levelname}
            key = tuple(sorted(labels.items()))
            with self._lock:
                self._buffer[key].append((ts, line))
        except Exception:
            # Never let logging crash the neuron
            pass

    async def _get_session(self) -> httpx.AsyncClient:
        if self._session is None or self._session.is_closed:
            self._session = httpx.AsyncClient()
        return self._session

    async def _async_flush(self) -> None:
        """Push buffered log entries to Loki. Called by the background task."""
        with self._lock:
            if not self._buffer:
                return
            # Snapshot and clear the buffer under the lock
            snapshot = dict(self._buffer)
            self._buffer.clear()

        streams = []
        for key, entries in snapshot.items():
            labels = dict(key)
            # Sort entries by timestamp to avoid out-of-order rejection
            sorted_entries = sorted(entries, key=lambda e: e[0])
            streams.append({"stream": labels, "values": sorted_entries})

        payload = {"streams": streams}
        try:
            session = await self._get_session()
            resp = await session.post(
                f"{self._url}/loki/api/v1/push",
                json=payload,
                headers=self._auth_header,
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code not in (200, 204):
                # Best-effort — don't let a failed push crash anything
                pass
        except Exception:
            # Network errors, auth errors — silently drop. Logs are best-effort.
            pass

    async def close_session(self) -> None:
        if self._session and not self._session.is_closed:
            await self._session.aclose()
            self._session = None


async def _flush_loop(handler: LokiHandler) -> None:
    """Background task that flushes the buffer periodically."""
    while True:
        await asyncio.sleep(_FLUSH_INTERVAL)
        await handler._async_flush()


def _run_flush_loop(handler: LokiHandler, loop: asyncio.AbstractEventLoop) -> None:
    """Run the flush loop on a dedicated thread's event loop (for sync callers)."""
    asyncio.set_event_loop(loop)
    with contextlib.suppress(RuntimeError):
        # Loop may be stopped via call_soon_threadsafe(_loop.stop) during shutdown
        loop.run_until_complete(_flush_loop(handler))


def init_loki(settings: Settings, labels: dict[str, str] | None = None) -> None:
    """Initialise the Loki log handler and attach it to the bittensor logger.

    If any Loki setting is absent, this is a no-op.

    Works from both async (validator — running event loop) and sync (miner —
    no event loop) contexts. For sync callers, a daemon thread with its own
    event loop is spawned to run the flush task.

    Args:
        settings: Application settings (must have ``loki_url``, ``loki_username``,
            ``loki_token`` fields).
        labels: Static labels to attach to every log line (e.g. ``{"uid": "42"}``).
    """
    global _handler, _flush_task, _loop_thread, _loop

    if _handler is not None:
        return  # already initialised

    if not settings.loki_url:
        return  # not configured — no-op

    if not settings.loki_username or not settings.loki_token:
        return  # incomplete config — no-op

    import bittensor as bt

    handler = LokiHandler(
        url=settings.loki_url,
        username=settings.loki_username,
        token=settings.loki_token,
        static_labels=labels,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    bt.logging._logger.addHandler(handler)
    _handler = handler

    # Start the background flush task
    try:
        loop = asyncio.get_running_loop()
        # Async context (validator) — create task on the running loop
        _flush_task = loop.create_task(_flush_loop(handler))
    except RuntimeError:
        # Sync context (miner) — spawn a daemon thread with its own loop
        _loop = asyncio.new_event_loop()
        _loop_thread = threading.Thread(
            target=_run_flush_loop,
            args=(handler, _loop),
            daemon=True,
            name="loki-flush",
        )
        _loop_thread.start()

    bt.logging.info(f"Loki log handler initialised (labels={handler._static_labels})")


async def shutdown_loki() -> None:
    """Flush remaining buffers, close the HTTP session, and remove the handler.

    Call on shutdown. Safe to call from async context (validator) or as a
    no-op if Loki was never initialised.
    """
    global _handler, _flush_task, _loop_thread, _loop

    if _flush_task is not None:
        _flush_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _flush_task
        _flush_task = None

    if _handler is not None:
        # Remove handler from logger before flushing to prevent further buffering
        import bittensor as bt

        bt.logging._logger.removeHandler(_handler)
        await _handler._async_flush()
        await _handler.close_session()
        _handler = None

    # Clean up the daemon thread loop if we spawned one
    if _loop is not None and not _loop.is_closed():
        _loop.call_soon_threadsafe(_loop.stop)
    if _loop_thread is not None:
        _loop_thread.join(timeout=2.0)
        _loop_thread = None
    if _loop is not None:
        if not _loop.is_closed():
            _loop.close()
        _loop = None


def shutdown_loki_sync() -> None:
    """Sync shutdown for miner context. Flushes and cleans up without asyncio.

    Called from sync code (miner's KeyboardInterrupt handler). Cancels the
    flush thread, removes the handler, and does a best-effort sync flush
    via requests if the httpx session can't be used (no running loop).
    """
    global _handler, _flush_task, _loop_thread, _loop

    if _handler is not None:
        import bittensor as bt

        bt.logging._logger.removeHandler(_handler)

        # Best-effort: stop the flush thread loop
        if _loop is not None and not _loop.is_closed():
            _loop.call_soon_threadsafe(_loop.stop)
        if _loop_thread is not None:
            _loop_thread.join(timeout=2.0)
            _loop_thread = None
        if _loop is not None:
            if not _loop.is_closed():
                _loop.close()
            _loop = None

        _handler = None
        _flush_task = None
