"""Shared fixtures. All tests run offline: chain, YouTube and LLM are mocked."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pytest


@pytest.fixture
def today():
    return datetime.now(UTC).date()


@pytest.fixture
def briefs(today):
    """Two active briefs relative to the real clock (evaluator paths use now())."""
    start = (today - timedelta(days=7)).isoformat()
    end = (today + timedelta(days=7)).isoformat()
    return [
        {"id": "brief-1", "brief": "Make a video about widgets.", "start_date": start, "end_date": end, "weight": 5},
        {
            "id": "brief-2",
            "brief": "Mention gadgets.",
            "start_date": start,
            "end_date": end,
            "weight": 1,
            "format": "ad-read",
        },
    ]


class FakeLLM:
    """Deterministic LLM stub: matches briefs whose id is in ``matching_ids``."""

    def __init__(self, matching_ids=("brief-1",), injection=False):
        self.matching_ids = set(matching_ids)
        self.injection = injection
        self.calls = 0

    async def evaluate_content_against_brief(self, brief, duration, description, transcript):
        self.calls += 1
        matched = brief["id"] in self.matching_ids
        return matched, "matched" if matched else "not matched"

    async def check_for_prompt_injection(self, description, transcript):
        return self.injection


@pytest.fixture
def fake_llm():
    return FakeLLM()


# ---------------------------------------------------------------------------
# Chain fakes — satisfy bitcast.chain.interface Protocols so weight_utils and
# chain-submit paths run fully offline. No subtensor, no network.
# ---------------------------------------------------------------------------


class FakeMetagraph:
    """Minimal metagraph satisfying chain.interface.MetagraphLike."""

    def __init__(self, n: int = 8, hotkeys: list[str] | None = None) -> None:
        self._n = n
        self.hotkeys = hotkeys or [f"hotkey{i}" for i in range(n)]
        self.axons: list[Any] = []
        self.uids = np.arange(n)
        self.last_update = np.zeros(n)

    @property
    def n(self) -> np.int64:
        return np.int64(self._n)

    def sync(self, subtensor: Any = None) -> None:
        pass


@dataclass
class FakeExtrinsicResponse:
    """Mirrors ``bittensor.core.types.ExtrinsicResponse``, the real return of
    ``Subtensor.set_weights``: attribute access plus tuple-like unpacking."""

    success: bool = True
    message: str = "ok"

    def __iter__(self):
        return iter((self.success, self.message))

    def __getitem__(self, index: int):
        return (self.success, self.message)[index]

    def __len__(self) -> int:
        return 2


class FakeSubtensor:
    """Minimal subtensor satisfying chain.interface.SubtensorLike."""

    chain_endpoint = "fake://local"

    def __init__(self, n: int = 8, min_allowed: int = 0, max_weight: float = 1.0) -> None:
        self.n = n
        self.set_weights_calls: list[dict[str, Any]] = []
        self.set_weights_result = FakeExtrinsicResponse()
        # Hyperparameters tests can override per-case (constructor or attribute).
        self.min_allowed = min_allowed
        self.max_weight = max_weight

    def get_current_block(self) -> int:
        return 1000

    def metagraph(self, netuid: int) -> FakeMetagraph:
        return FakeMetagraph(self.n)

    def is_hotkey_registered(self, hotkey_ss58: str, netuid=None, block=None) -> bool:
        return True

    def min_allowed_weights(self, netuid: int, block=None) -> int:
        return self.min_allowed

    def max_weight_limit(self, netuid: int, block=None) -> float:
        return self.max_weight

    def set_weights(self, wallet, netuid, uids, weights, **kwargs):
        self.set_weights_calls.append({"uids": uids, "weights": weights, "kwargs": {"netuid": netuid, **kwargs}})
        return self.set_weights_result

    def serve_axon(self, netuid: int, axon: Any) -> None:
        pass


class FakeKeypair:
    ss58_address = "5FakeValidatorHotkeyAddressForTests0000000000000"

    def sign(self, data: str) -> bytes:
        return b"signed:" + data.encode()[:16]


class FakeWallet:
    hotkey = FakeKeypair()


@pytest.fixture
def fake_metagraph():
    return FakeMetagraph()


@pytest.fixture
def fake_subtensor():
    return FakeSubtensor()


@pytest.fixture
def fake_wallet():
    return FakeWallet()
