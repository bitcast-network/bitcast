"""Sentry init and capture_exception tests."""

from unittest.mock import patch

from bitcast.config import Settings
from bitcast.sentry import capture_exception, init_sentry


class TestInitSentry:
    def test_no_dsn_is_noop(self):
        """Without a DSN, init_sentry must not load the SDK."""
        settings = Settings(sentry_dsn=None)
        with patch("bitcast.sentry._initialized", False):
            init_sentry(settings)
            import bitcast.sentry as s

            assert s._initialized is False

    def test_with_dsn_initializes(self):
        """With a DSN, sentry_sdk.init is called once."""
        settings = Settings(sentry_dsn="https://fake@host/123")
        with (
            patch("bitcast.sentry._initialized", False),
            patch("sentry_sdk.init") as mock_init,
        ):
            init_sentry(settings)
            assert mock_init.called
            call_kwargs = mock_init.call_args.kwargs
            assert call_kwargs["dsn"] == "https://fake@host/123"
            assert call_kwargs["send_default_pii"] is False

    def test_double_init_is_idempotent(self):
        """Calling init twice does not re-initialise."""
        settings = Settings(sentry_dsn="https://fake@host/123")
        with (
            patch("bitcast.sentry._initialized", False),
            patch("sentry_sdk.init") as mock_init,
        ):
            init_sentry(settings)
            init_sentry(settings)
            assert mock_init.call_count == 1


class TestCaptureException:
    def test_uninitialised_falls_back_to_logging(self):
        """Without Sentry, capture_exception logs via bt.logging."""
        with (
            patch("bitcast.sentry._initialized", False),
            patch("bittensor.logging.error") as mock_log,
        ):
            exc = RuntimeError("boom")
            capture_exception(exc)
            mock_log.assert_called_once()
            assert "RuntimeError" in mock_log.call_args[0][0]

    def test_initialised_captures(self):
        """With Sentry active, capture_exception delegates to sentry_sdk."""
        with (
            patch("bitcast.sentry._initialized", True),
            patch("sentry_sdk.capture_exception") as mock_cap,
        ):
            exc = ValueError("snap")
            capture_exception(exc)
            mock_cap.assert_called_once_with(exc)
