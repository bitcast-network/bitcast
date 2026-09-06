"""RFC3339 timestamp parsing shared by the API client, scoring and matching."""

from datetime import UTC, datetime

from bitcast.validator.youtube.timestamps import parse_timestamp


def test_parses_fractional_seconds():
    assert parse_timestamp("2026-07-31T12:30:45.123Z") == datetime(2026, 7, 31, 12, 30, 45, 123000, tzinfo=UTC)


def test_parses_whole_seconds():
    assert parse_timestamp("2026-07-31T12:30:45Z") == datetime(2026, 7, 31, 12, 30, 45, tzinfo=UTC)


def test_result_is_always_utc_aware():
    parsed = parse_timestamp("2026-07-31T00:00:00Z")
    assert parsed is not None and parsed.tzinfo is UTC


def test_unparseable_values_return_none():
    assert parse_timestamp("") is None
    assert parse_timestamp("31/07/2026") is None
    assert parse_timestamp("2026-07-31T12:30:45+00:00") is None  # offset form is not emitted by the API
