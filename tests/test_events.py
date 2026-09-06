"""Structured log events must always survive a LogQL ``| json`` round-trip."""

import json

import pytest

from bitcast.events import log_event


@pytest.fixture
def captured(monkeypatch):
    lines: list[str] = []
    monkeypatch.setattr("bitcast.events.bt.logging.info", lines.append)
    return lines


def test_event_is_compact_single_line_json(captured):
    log_event({"event": "demo", "count": 3})
    [line] = captured
    assert line == '{"event":"demo","count":3}'


def test_quotes_and_newlines_are_escaped(captured):
    log_event({"event": "demo", "error": 'bad "state"\nline two'})
    [line] = captured
    assert "\n" not in line
    assert json.loads(line)["error"] == 'bad "state"\nline two'


def test_non_serializable_values_degrade_to_strings(captured):
    log_event({"event": "demo", "path": object()})
    [line] = captured
    assert isinstance(json.loads(line)["path"], str)
