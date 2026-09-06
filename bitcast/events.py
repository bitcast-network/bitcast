"""Structured log events for Grafana Loki / LogQL ``| json`` parsing.

One line per event, serialized by ``json.dumps`` rather than assembled with
f-strings: a value carrying a quote or newline (a chain error message, an
exception repr) would otherwise corrupt the line and silently break the
dashboard query that consumes it.
"""

import json
from typing import Any

import bittensor as bt


def log_event(event: dict[str, Any]) -> None:
    """Emit ``event`` as one compact JSON log line.

    Values that are not JSON-serializable fall back to their ``str()`` form so
    an observability call can never raise into the caller.
    """
    bt.logging.info(json.dumps(event, separators=(",", ":"), default=str))
