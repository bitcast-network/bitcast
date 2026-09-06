"""Sentry initialisation for the Bitcast subnet (V2).

Initialised once at neuron startup via ``init_sentry(settings)``. If
``SENTRY_DSN`` is unset, this is a no-op — no SDK is loaded, no network
calls are made, ``capture_exception`` delegates to ``bt.logging.error``.

Usage::

    from bitcast.sentry import init_sentry
    init_sentry(settings)

    # Later, in error paths:
    from bitcast.sentry import capture_exception
    capture_exception(exc)
"""

import bittensor as bt

_initialized = False


def init_sentry(settings) -> None:
    """Initialise the Sentry SDK if a DSN is configured.

    Safe to call multiple times — only the first call with a valid DSN wins.
    """
    global _initialized
    if _initialized or not settings.sentry_dsn or settings.sentry_dsn == "not-set":
        return

    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
    _initialized = True
    bt.logging.info(f"Sentry initialised (env={settings.sentry_environment})")


def capture_exception(exc: BaseException) -> None:
    """Capture an exception in Sentry.

    Falls back to ``bt.logging.error`` if Sentry was not initialised.
    """
    if _initialized:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    else:
        bt.logging.error(f"{type(exc).__name__}: {exc}")
