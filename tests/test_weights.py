"""Validator weight normalization and on-chain submission (chain is faked)."""

import json

import numpy as np
import pytest

from bitcast.validator.telemetry import MinerScoreTelemetry
from bitcast.validator.weights import normalize_scores, set_weights
from tests.conftest import FakeExtrinsicResponse, FakeMetagraph, FakeSubtensor, FakeWallet


class TestNormalizeScores:
    def test_l1_normalization(self):
        assert normalize_scores(np.array([1.0, 3.0])).tolist() == [0.25, 0.75]

    def test_zero_scores_pass_through(self):
        assert normalize_scores(np.zeros(3)).tolist() == [0.0, 0.0, 0.0]

    def test_normalized_sum_is_one(self):
        weights = normalize_scores(np.array([0.2, 0.5, 0.3]))
        assert weights.sum() == pytest.approx(1.0)
        assert weights.dtype == np.float32


class FakeValidator:
    """Minimal validator surface consumed by ``weights.set_weights``."""

    spec_version = 2

    def __init__(self, scores: np.ndarray, subtensor: FakeSubtensor | None = None) -> None:
        n = len(scores)
        self.scores = scores
        self.metagraph = FakeMetagraph(n)
        self.subtensor = subtensor or FakeSubtensor(n=n)
        self.wallet = FakeWallet()
        self.config = type("Config", (), {"netuid": 93})()
        self.emitted: list[str] = []
        self.telemetry = MinerScoreTelemetry(self.emitted.append)


@pytest.fixture
def captured_logs(monkeypatch):
    """Collect ``bt.logging.info`` lines emitted by weights.set_weights."""
    lines: list[str] = []
    monkeypatch.setattr("bitcast.validator.weights.bt.logging.info", lines.append)
    monkeypatch.setattr("bitcast.validator.weights.bt.logging.warning", lines.append)
    monkeypatch.setattr("bitcast.validator.weights.bt.logging.error", lines.append)
    return lines


def json_events(lines: list[str]) -> list[dict]:
    """Parse the structured (JSON object) subset of captured log lines."""
    events = []
    for line in lines:
        if line.startswith("{"):
            events.append(json.loads(line))
    return events


class TestSetWeights:
    def test_successful_submission_returns_true_and_emits(self, captured_logs):
        validator = FakeValidator(np.array([0.0, 1.0, 3.0, 0.0], dtype=np.float32))
        assert set_weights(validator) is True

        call = validator.subtensor.set_weights_calls[0]
        assert call["kwargs"]["netuid"] == 93
        assert call["kwargs"]["version_key"] == 2
        # Vendored converter emits numpy-int uids and python-int uint16 weights.
        assert all(isinstance(uid, (int, np.integer)) for uid in call["uids"])
        assert all(isinstance(weight, int) for weight in call["weights"])
        assert max(call["weights"]) == 65535  # max-upscaled before emit

        [event] = json_events(captured_logs)
        assert event["event"] == "set_weights"
        assert event["success"] is True
        assert event["num_weights"] == len(call["weights"])
        assert [entry["uid"] for entry in event["top_weights"]] == [2, 1]

    def test_failed_submission_returns_false(self, captured_logs):
        subtensor = FakeSubtensor(n=4)
        subtensor.set_weights_result = FakeExtrinsicResponse(False, "rejected")
        validator = FakeValidator(np.array([0.0, 1.0, 3.0, 0.0], dtype=np.float32), subtensor)

        assert set_weights(validator) is False
        [event] = json_events(captured_logs)
        assert event == {"event": "set_weights", "success": False, "error": "rejected"}

    def test_failure_message_is_json_escaped(self, captured_logs):
        subtensor = FakeSubtensor(n=4)
        subtensor.set_weights_result = FakeExtrinsicResponse(False, 'bad "state"\nline two')
        validator = FakeValidator(np.array([0.0, 1.0, 3.0, 0.0], dtype=np.float32), subtensor)

        set_weights(validator)
        # The raw quotes/newline must survive a JSON round-trip, not corrupt the line.
        [event] = json_events(captured_logs)
        assert event["error"] == 'bad "state"\nline two'

    def test_nan_scores_are_treated_as_zero(self, captured_logs):
        validator = FakeValidator(np.array([0.0, np.nan, 2.0, 0.0], dtype=np.float32))
        assert set_weights(validator) is True
        assert any("NaN" in line for line in captured_logs)
        [event] = json_events(captured_logs)
        assert [entry["uid"] for entry in event["top_weights"]][0] == 2

    def test_telemetry_joins_submitted_weights_on_success(self):
        validator = FakeValidator(np.array([0.0, 1.0, 3.0, 0.0], dtype=np.float32))
        validator.telemetry.record_scores(
            validator_uid=7,
            step=240,
            uids=[0, 1, 2, 3],
            rewards=np.array([0.0, 0.25, 0.75, 0.0]),
            ema_before=np.zeros(4),
            ema_after=np.array([0.0, 0.15, 0.45, 0.0]),
        )
        set_weights(validator)
        validator.telemetry.flush()

        samples = {json.loads(line)["miner_uid"]: json.loads(line) for line in validator.emitted}
        assert samples[2]["submitted_weight"] > samples[1]["submitted_weight"]
        assert isinstance(samples[2]["onchain_weight_uint16"], int)

    def test_telemetry_is_not_recorded_when_submission_fails(self):
        subtensor = FakeSubtensor(n=4)
        subtensor.set_weights_result = FakeExtrinsicResponse(False, "rejected")
        validator = FakeValidator(np.array([0.0, 1.0, 3.0, 0.0], dtype=np.float32), subtensor)
        validator.telemetry.record_scores(
            validator_uid=7,
            step=240,
            uids=[0, 1, 2, 3],
            rewards=np.array([0.0, 0.25, 0.75, 0.0]),
            ema_before=np.zeros(4),
            ema_after=np.array([0.0, 0.15, 0.45, 0.0]),
        )
        set_weights(validator)
        validator.telemetry.flush()

        assert all("submitted_weight" not in line for line in validator.emitted)

    def test_telemetry_failure_never_blocks_submission(self):
        validator = FakeValidator(np.array([0.0, 1.0, 3.0, 0.0], dtype=np.float32))

        class ExplodingTelemetry:
            def record_submitted_weights(self, **kwargs):
                raise RuntimeError("telemetry down")

        validator.telemetry = ExplodingTelemetry()
        assert set_weights(validator) is True
