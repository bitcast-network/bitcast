"""Parsing for the RFC3339 timestamps the YouTube APIs return.

Shared by the API client, channel/video vetting and brief matching, which
previously reached into the API client for a private helper.
"""

from datetime import UTC, datetime

# The Data API emits both forms; neither carries a numeric UTC offset.
_FORMATS = ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ")


def parse_timestamp(value: str) -> datetime | None:
    """Parse a YouTube timestamp into a UTC-aware datetime, or None if unparseable."""
    for fmt in _FORMATS:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None
