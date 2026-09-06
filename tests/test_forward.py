"""Validator step loop: cycle cadence, brief fetching, structured telemetry."""

import json

import numpy as np
import pytest

from bitcast.config import VALIDATOR_STEPS_INTERVAL
from bitcast.validator import forward as forward_module
from bitcast.validator.forward import forward, get_all_uids
from tests.conftest import FakeMetagraph


class FakeValidator:
    def __init__(self, step: int, n: int = 4) -> None:
        self.step = step
        self.metagraph = FakeMetagraph(n)
        self.updated: list[tuple[np.ndarray, list[int]]] = []

    def update_scores(self, rewards, uids):
        self.updated.append((rewards, uids))


class FakePublisher:
    def __init__(self) -> None:
        self.runs = 0

    def new_run(self) -> str:
        self.runs += 1
        return f"run-{self.runs}"

    async def publish_account_results(self, result) -> None: ...

    async def publish_weight_corrections(self, corrections) -> None: ...


class FakeOrchestrator:
    def __init__(self, publisher=None, rewards=None) -> None:
        self.publisher = publisher
        self.rewards = rewards if rewards is not None else np.array([0.4, 0.6, 0.0, 0.0])
        self.calls: list[tuple[list[int], list[dict]]] = []

    async def calculate_rewards(self, validator, uids, briefs):
        self.calls.append((uids, briefs))
        return self.rewards, [{"uid": uid} for uid in uids]


@pytest.fixture(autouse=True)
def instant_sleep(monkeypatch):
    async def noop(_seconds):
        return None

    monkeypatch.setattr(forward_module.asyncio, "sleep", noop)


@pytest.fixture
def captured_logs(monkeypatch):
    lines: list[str] = []
    for level in ("info", "warning", "error"):
        monkeypatch.setattr(f"bitcast.validator.forward.bt.logging.{level}", lines.append)
    return lines


def stub_briefs(monkeypatch, briefs=None, error: Exception | None = None):
    async def fake_get_briefs(cache_path=None):
        if error is not None:
            raise error
        return briefs or []

    monkeypatch.setattr(forward_module, "get_briefs", fake_get_briefs)


def json_events(lines: list[str]) -> list[dict]:
    return [json.loads(line) for line in lines if line.startswith("{")]


def test_get_all_uids_covers_the_metagraph():
    assert get_all_uids(FakeValidator(step=0, n=5)) == [0, 1, 2, 3, 4]


class TestCadence:
    async def test_non_cycle_step_skips_the_reward_cycle(self, monkeypatch, captured_logs):
        stub_briefs(monkeypatch, [{"id": "b1"}])
        validator = FakeValidator(step=1)
        orchestrator = FakeOrchestrator()

        await forward(validator, orchestrator)

        assert orchestrator.calls == []
        assert validator.updated == []

    async def test_cycle_step_runs_and_updates_scores(self, monkeypatch, captured_logs):
        briefs = [{"id": "b1"}, {"id": "b2"}]
        stub_briefs(monkeypatch, briefs)
        validator = FakeValidator(step=VALIDATOR_STEPS_INTERVAL)
        orchestrator = FakeOrchestrator()

        await forward(validator, orchestrator)

        assert orchestrator.calls == [([0, 1, 2, 3], briefs)]
        rewards, uids = validator.updated[0]
        assert uids == [0, 1, 2, 3]
        assert rewards.tolist() == [0.4, 0.6, 0.0, 0.0]


class TestBriefs:
    async def test_unreachable_briefs_server_falls_through_to_empty(self, monkeypatch, captured_logs):
        stub_briefs(monkeypatch, error=ConnectionError("briefs down"))
        validator = FakeValidator(step=VALIDATOR_STEPS_INTERVAL)
        orchestrator = FakeOrchestrator()

        await forward(validator, orchestrator)

        assert orchestrator.calls == [([0, 1, 2, 3], [])]
        assert any("Could not fetch briefs" in line for line in captured_logs)


class TestPublisherRun:
    async def test_new_run_is_started_once_per_cycle(self, monkeypatch, captured_logs):
        stub_briefs(monkeypatch, [{"id": "b1"}])
        publisher = FakePublisher()
        orchestrator = FakeOrchestrator(publisher=publisher)

        await forward(FakeValidator(step=VALIDATOR_STEPS_INTERVAL), orchestrator)
        assert publisher.runs == 1

    async def test_absent_publisher_is_tolerated(self, monkeypatch, captured_logs):
        stub_briefs(monkeypatch, [{"id": "b1"}])
        orchestrator = FakeOrchestrator(publisher=None)
        await forward(FakeValidator(step=VALIDATOR_STEPS_INTERVAL), orchestrator)
        assert orchestrator.calls


class TestStructuredEvent:
    async def test_reward_cycle_event_is_valid_json(self, monkeypatch, captured_logs):
        stub_briefs(monkeypatch, [{"id": "b1"}, {"id": "b2"}])
        orchestrator = FakeOrchestrator(rewards=np.array([0.25, 0.5, 0.25, 0.0]))

        await forward(FakeValidator(step=VALIDATOR_STEPS_INTERVAL), orchestrator)

        [event] = json_events(captured_logs)
        assert event == {
            "event": "reward_cycle",
            "step": VALIDATOR_STEPS_INTERVAL,
            "briefs": 2,
            "earning_miners": 2,
            "total_miners": 4,
            "burn": 0.25,
            "videos_evaluated": 4,
        }
