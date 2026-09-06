"""Loki log handler tests — init, no-op, buffering, flush, shutdown, and thread-safety."""

import logging
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bitcast.config import Settings
from bitcast.loki import LokiHandler, init_loki, shutdown_loki, shutdown_loki_sync


class TestInitLoki:
    def test_no_url_is_noop(self):
        """Without LOKI_URL, init_loki must not create a handler."""
        settings = Settings(loki_url=None)
        with patch("bitcast.loki._handler", None):
            init_loki(settings)
            import bitcast.loki as mod

            assert mod._handler is None

    def test_incomplete_config_is_noop(self):
        """URL set but missing username/token — still a no-op."""
        settings = Settings(loki_url="https://logs-prod.grafana.net", loki_username=None, loki_token=None)
        with patch("bitcast.loki._handler", None):
            init_loki(settings)
            import bitcast.loki as mod

            assert mod._handler is None

    @pytest.mark.asyncio
    async def test_full_config_initialises_async(self):
        """With URL + username + token in async context, handler is attached."""
        settings = Settings(
            loki_url="https://logs-prod.grafana.net",
            loki_username="123456",
            loki_token="abc-token",
        )
        with (
            patch("bitcast.loki._handler", None),
            patch("bitcast.loki._flush_task", None),
            patch("bitcast.loki._loop_thread", None),
            patch("bitcast.loki._loop", None),
        ):
            init_loki(settings, labels={"uid": "42"})
            import bitcast.loki as mod

            assert mod._handler is not None
            assert mod._handler._static_labels == {"uid": "42"}
            assert mod._handler._url == "https://logs-prod.grafana.net"
            # In async context, should create a task (not a thread)
            assert mod._flush_task is not None
            assert mod._loop_thread is None

            await shutdown_loki()

    def test_full_config_initialises_sync(self):
        """With URL + username + token in sync context (no event loop), a daemon thread is spawned."""
        settings = Settings(
            loki_url="https://logs-prod.grafana.net",
            loki_username="123456",
            loki_token="abc-token",
        )
        with (
            patch("bitcast.loki._handler", None),
            patch("bitcast.loki._flush_task", None),
            patch("bitcast.loki._loop_thread", None),
            patch("bitcast.loki._loop", None),
        ):
            init_loki(settings, labels={"uid": "99"})
            import bitcast.loki as mod

            assert mod._handler is not None
            # In sync context, should spawn a thread (not a task)
            assert mod._flush_task is None
            assert mod._loop_thread is not None
            assert mod._loop is not None

            # Clean up the thread
            shutdown_loki_sync()

    @pytest.mark.asyncio
    async def test_double_init_is_idempotent(self):
        """Calling init twice does not create a second handler."""
        settings = Settings(
            loki_url="https://logs-prod.grafana.net",
            loki_username="123456",
            loki_token="abc-token",
        )
        with (
            patch("bitcast.loki._handler", None),
            patch("bitcast.loki._flush_task", None),
            patch("bitcast.loki._loop_thread", None),
            patch("bitcast.loki._loop", None),
        ):
            init_loki(settings)
            import bitcast.loki as mod

            first = mod._handler
            init_loki(settings)
            assert mod._handler is first

            await shutdown_loki()


class TestLokiHandlerBuffering:
    def test_emit_buffers_records(self):
        """emit() stores records in the buffer keyed by label set."""
        handler = LokiHandler(
            url="https://logs-prod.grafana.net",
            username="123",
            token="abc",
            static_labels={"uid": "42"},
        )
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="scoring cycle complete",
            args=None,
            exc_info=None,
        )
        handler.emit(record)
        assert len(handler._buffer) == 1
        for entries in handler._buffer.values():
            assert len(entries) == 1
            ts, line = entries[0]
            assert ts.isdigit()  # nanosecond timestamp
            assert "scoring cycle complete" in line

    def test_emit_with_different_levels(self):
        """INFO and ERROR records get different label keys (level label differs)."""
        handler = LokiHandler(
            url="https://logs-prod.grafana.net",
            username="123",
            token="abc",
            static_labels={"uid": "42"},
        )
        info_record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="t.py",
            lineno=1,
            msg="ok",
            args=None,
            exc_info=None,
        )
        error_record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="t.py",
            lineno=2,
            msg="boom",
            args=None,
            exc_info=None,
        )
        handler.emit(info_record)
        handler.emit(error_record)
        # Two label-sets: one for INFO, one for ERROR
        assert len(handler._buffer) == 2

    def test_emit_never_raises(self):
        """emit must never raise — even with a bad record."""
        handler = LokiHandler(
            url="https://logs-prod.grafana.net",
            username="123",
            token="abc",
        )
        # Pass a None record — should not raise
        handler.emit(None)  # type: ignore[arg-type]
        # Buffer may or may not have an entry, but no exception

    def test_emit_is_thread_safe(self):
        """Concurrent emit() calls from multiple threads must not crash."""
        handler = LokiHandler(
            url="https://logs-prod.grafana.net",
            username="123",
            token="abc",
            static_labels={"uid": "1"},
        )
        errors = []

        def writer(n: int) -> None:
            try:
                for i in range(100):
                    record = logging.LogRecord(
                        name="test",
                        level=logging.INFO,
                        pathname="t.py",
                        lineno=i,
                        msg=f"thread-{n}-line-{i}",
                        args=None,
                        exc_info=None,
                    )
                    handler.emit(record)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent emit errors: {errors}"
        total = sum(len(v) for v in handler._buffer.values())
        assert total == 400  # 4 threads × 100 records


class TestLokiHandlerFlush:
    @pytest.mark.asyncio
    async def test_flush_sends_payload(self):
        """_async_flush() POSTs buffered entries to the Loki push API."""
        handler = LokiHandler(
            url="https://logs-prod.grafana.net",
            username="123",
            token="abc",
            static_labels={"uid": "42"},
        )
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="t.py",
            lineno=1,
            msg="hello loki",
            args=None,
            exc_info=None,
        )
        handler.emit(record)

        # Mock the session's post method (httpx returns response directly)
        mock_resp = MagicMock()
        mock_resp.status_code = 204

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_resp)
        mock_session.is_closed = False

        with patch.object(handler, "_get_session", return_value=mock_session):
            await handler._async_flush()

        # Verify POST was called with the right URL and payload structure
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert "/loki/api/v1/push" in call_args.args[0]
        payload = call_args.kwargs["json"]
        assert "streams" in payload
        assert len(payload["streams"]) == 1
        stream = payload["streams"][0]
        assert stream["stream"]["uid"] == "42"
        assert stream["stream"]["level"] == "INFO"
        assert len(stream["values"]) == 1

    @pytest.mark.asyncio
    async def test_flush_empty_buffer_is_noop(self):
        """_async_flush() with empty buffer does not make an HTTP request."""
        handler = LokiHandler(
            url="https://logs-prod.grafana.net",
            username="123",
            token="abc",
        )
        # No records emitted — should not attempt any HTTP
        mock_session = MagicMock()
        with patch.object(handler, "_get_session", return_value=mock_session):
            await handler._async_flush()
        mock_session.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_flush_failure_is_silent(self):
        """A failed POST is silently dropped — no exception propagated."""
        handler = LokiHandler(
            url="https://logs-prod.grafana.net",
            username="123",
            token="abc",
        )
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="t.py",
            lineno=1,
            msg="error line",
            args=None,
            exc_info=None,
        )
        handler.emit(record)

        mock_session = MagicMock()
        mock_session.post = AsyncMock(side_effect=Exception("network down"))
        mock_session.is_closed = False

        with patch.object(handler, "_get_session", return_value=mock_session):
            await handler._async_flush()  # should not raise

    @pytest.mark.asyncio
    async def test_flush_clears_buffer(self):
        """After flush, the buffer is empty."""
        handler = LokiHandler(
            url="https://logs-prod.grafana.net",
            username="123",
            token="abc",
            static_labels={"uid": "1"},
        )
        for i in range(5):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="t.py",
                lineno=i,
                msg=f"line {i}",
                args=None,
                exc_info=None,
            )
            handler.emit(record)
        assert sum(len(v) for v in handler._buffer.values()) == 5

        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_resp)
        mock_session.is_closed = False

        with patch.object(handler, "_get_session", return_value=mock_session):
            await handler._async_flush()

        assert len(handler._buffer) == 0 or all(len(v) == 0 for v in handler._buffer.values())

    @pytest.mark.asyncio
    async def test_flush_sorts_entries_by_timestamp(self):
        """Entries within a stream are sorted by timestamp before pushing."""
        handler = LokiHandler(
            url="https://logs-prod.grafana.net",
            username="123",
            token="abc",
            static_labels={"uid": "1"},
        )
        # Emit records out of order (older second record first)
        old_record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="t.py",
            lineno=1,
            msg="old",
            args=None,
            exc_info=None,
        )
        old_record.created = 1000.0
        new_record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="t.py",
            lineno=2,
            msg="new",
            args=None,
            exc_info=None,
        )
        new_record.created = 2000.0
        # Insert in reverse order
        handler.emit(new_record)
        handler.emit(old_record)

        captured_payload = None

        mock_resp = MagicMock()
        mock_resp.status_code = 204

        mock_session = MagicMock()
        mock_session.is_closed = False

        async def capturing_post(*args, **kwargs):
            nonlocal captured_payload
            captured_payload = kwargs.get("json")
            return mock_resp

        mock_session.post = capturing_post

        with patch.object(handler, "_get_session", return_value=mock_session):
            await handler._async_flush()

        assert captured_payload is not None
        values = captured_payload["streams"][0]["values"]
        assert values[0][1] == "old"  # older entry first
        assert values[1][1] == "new"


class TestShutdownLoki:
    @pytest.mark.asyncio
    async def test_shutdown_flushes_and_cleans_up(self):
        """shutdown_loki flushes remaining logs, removes handler, resets state."""
        settings = Settings(
            loki_url="https://logs-prod.grafana.net",
            loki_username="123",
            loki_token="abc",
        )
        with (
            patch("bitcast.loki._handler", None),
            patch("bitcast.loki._flush_task", None),
            patch("bitcast.loki._loop_thread", None),
            patch("bitcast.loki._loop", None),
        ):
            init_loki(settings, labels={"uid": "99"})
            import bitcast.loki as mod

            assert mod._handler is not None
            handler = mod._handler

            # Emit a record
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="t.py",
                lineno=1,
                msg="final line",
                args=None,
                exc_info=None,
            )
            handler.emit(record)

            # Mock the async flush to avoid real HTTP
            handler._async_flush = AsyncMock()
            handler.close_session = AsyncMock()

            await shutdown_loki()

            handler._async_flush.assert_called_once()
            handler.close_session.assert_called_once()
            assert mod._handler is None
            assert mod._flush_task is None

    @pytest.mark.asyncio
    async def test_shutdown_removes_handler_from_logger(self):
        """shutdown_loki must remove the handler from bt.logging._logger."""
        import bittensor as bt

        settings = Settings(
            loki_url="https://logs-prod.grafana.net",
            loki_username="123",
            loki_token="abc",
        )
        with (
            patch("bitcast.loki._handler", None),
            patch("bitcast.loki._flush_task", None),
            patch("bitcast.loki._loop_thread", None),
            patch("bitcast.loki._loop", None),
        ):
            init_loki(settings)
            import bitcast.loki as mod

            handler = mod._handler
            assert handler in bt.logging._logger.handlers

            handler._async_flush = AsyncMock()
            handler.close_session = AsyncMock()

            await shutdown_loki()

            assert handler not in bt.logging._logger.handlers

    def test_shutdown_sync_cleans_up(self):
        """shutdown_loki_sync removes handler and cleans up thread/loop."""
        settings = Settings(
            loki_url="https://logs-prod.grafana.net",
            loki_username="123",
            loki_token="abc",
        )
        with (
            patch("bitcast.loki._handler", None),
            patch("bitcast.loki._flush_task", None),
            patch("bitcast.loki._loop_thread", None),
            patch("bitcast.loki._loop", None),
        ):
            init_loki(settings)
            import bitcast.loki as mod

            assert mod._handler is not None
            assert mod._loop_thread is not None

            shutdown_loki_sync()

            assert mod._handler is None
            assert mod._loop_thread is None
            assert mod._loop is None
