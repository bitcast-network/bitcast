"""Audit telemetry for validator score cycles stays safe and side-effect free."""

import json
from types import SimpleNamespace

import numpy as np
import pytest

from bitcast.config import ObservabilitySettings
from bitcast.validator.base import BaseValidatorNeuron
from bitcast.validator.telemetry import MinerScoreTelemetry, sanitize_loki_labels


def test_loki_is_disabled_without_credentials(monkeypatch):
    """No baked-in credentials in the public repo: Loki stays off until
    LOKI_URL/LOKI_USERNAME/LOKI_TOKEN are provided via deployment env
    (re-injected at deploy time from Actions secrets)."""
    for key in ("LOKI_URL", "LOKI_USERNAME", "LOKI_TOKEN"):
        monkeypatch.delenv(key, raising=False)

    settings = ObservabilitySettings()

    assert settings.loki_token is None
    assert settings.loki_username is None


def test_miner_score_schema_contains_only_operational_score_fields():
    lines: list[str] = []
    telemetry = MinerScoreTelemetry(lines.append)

    telemetry.record_scores(
        validator_uid=60,
        step=240,
        uids=[0, 68],
        rewards=np.array([0.0, 3.5], dtype=np.float32),
        ema_before=np.array([0.2, 1.0], dtype=np.float32),
        ema_after=np.array([0.12, 2.5], dtype=np.float32),
    )
    telemetry.flush()

    events = [json.loads(line) for line in lines]
    schema_fields = {
        "event",
        "schema_version",
        "validator_uid",
        "cycle_id",
        "cycle_step",
        "miner_uid",
        "raw_reward",
        "ema_before",
        "ema_after",
    }
    assert [set(event) for event in events] == [schema_fields, schema_fields]
    assert {key: events[0][key] for key in ("event", "schema_version", "validator_uid", "cycle_id", "cycle_step")} == {
        "event": "miner_score",
        "schema_version": 1,
        "validator_uid": 60,
        "cycle_id": "60:240",
        "cycle_step": 240,
    }
    assert events[0]["miner_uid"] == 0
    assert events[0]["raw_reward"] == 0.0
    assert events[0]["ema_before"] == pytest.approx(0.2)
    assert events[0]["ema_after"] == pytest.approx(0.12)
    assert events[1]["miner_uid"] == 68
    assert events[1]["raw_reward"] == 3.5
    assert events[1]["ema_before"] == 1.0
    assert events[1]["ema_after"] == 2.5


def test_submitted_weights_are_added_only_when_submission_succeeds():
    lines: list[str] = []
    telemetry = MinerScoreTelemetry(lines.append)
    telemetry.record_scores(
        validator_uid=0,
        step=480,
        uids=[68],
        rewards=np.array([1.0]),
        ema_before=np.array([0.5]),
        ema_after=np.array([0.8]),
    )

    telemetry.record_submitted_weights(
        processed_uids=np.array([68]),
        processed_weights=np.array([0.123456]),
        uint_uids=np.array([68]),
        uint_weights=np.array([8090]),
    )
    telemetry.flush()

    event = json.loads(lines[0])
    assert event["submitted_weight"] == 0.123456
    assert event["onchain_weight_uint16"] == 8090
    assert "normalized_weight" not in event


def test_telemetry_failure_never_changes_ema_score_update():
    class BrokenTelemetry:
        def record_scores(self, **kwargs):
            raise RuntimeError("Loki unavailable")

    subject = SimpleNamespace(
        scores=np.array([0.2, 0.8], dtype=np.float32),
        config=SimpleNamespace(neuron=SimpleNamespace(moving_average_alpha=0.6)),
        uid=60,
        step=240,
        telemetry=BrokenTelemetry(),
    )

    BaseValidatorNeuron.update_scores(subject, np.array([1.0, 0.0]), [0, 1])

    assert subject.scores.tolist() == pytest.approx([0.68, 0.32])


def test_label_sanitization_keeps_only_bounded_validator_labels():
    labels = sanitize_loki_labels(
        {
            "uid": "60",
            "hotkey": "5CanaryHotkey",
            "netuid": "93",
            "mechid": "0",
            "neuron": "validator",
            "version": "2.0.0",
            "miner_uid": "68",
            "content": "creator transcript should never be a label",
        }
    )

    assert labels == {
        "uid": "60",
        "hotkey": "5CanaryHotkey",
        "netuid": "93",
        "mechid": "0",
        "neuron": "validator",
        "version": "2.0.0",
    }


def test_mechid_label_separates_youtube_from_x():
    """SN93 runs YouTube on mechanism 0 and X on mechanism 1 from the same
    hotkey and the same UID. Without mechid the two validators' logs share an
    identical label-set and merge into a single indistinguishable stream."""
    shared = {"uid": "60", "hotkey": "5CanaryHotkey", "netuid": "93", "neuron": "validator"}

    youtube = sanitize_loki_labels({**shared, "mechid": "0"})
    x = sanitize_loki_labels({**shared, "mechid": "1"})

    assert youtube["mechid"] == "0"
    assert x["mechid"] == "1"
    assert youtube != x
