"""Generate parity fixtures pinning the full weight-emission pipeline.

Dev tool — NOT run in CI. Produces ``fixtures/parity.json`` containing
representative inputs plus the EXACT outputs of the weight-processing pipeline:

    normalize_scores  →  process_weights_for_netuid  →  convert_weights_and_uids_for_emit

This mirrors ``bitcast/validator/weights.py::set_weights``. The vendored
``weight_utils`` (verbatim bittensor 10.3.0) is consensus-critical: every
validator on the subnet must produce byte-identical u16 weights for identical
scores and chain hyperparameters. ``test_parity.py`` replays these fixtures and
asserts ``np.array_equal`` — equal, not "close" — so no refactor can silently
diverge this validator from the network.

Run::

    python tests/parity/generate_fixtures.py
"""

import json
from pathlib import Path
from typing import Any

import numpy as np

from bitcast.chain.weight_utils import (
    convert_weights_and_uids_for_emit,
    process_weights_for_netuid,
)
from bitcast.validator.weights import normalize_scores

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "parity.json"
NETUID = 93


# ---------------------------------------------------------------------------
# Minimal chain fakes (mirror tests/conftest.py so this stays standalone)
# ---------------------------------------------------------------------------


class FakeMetagraph:
    def __init__(self, n: int = 8) -> None:
        self._n = n
        self.hotkeys = [f"hotkey{i}" for i in range(n)]
        self.axons: list[Any] = []
        self.uids = np.arange(n)
        self.last_update = np.zeros(n)

    @property
    def n(self) -> np.int64:
        return np.int64(self._n)

    def sync(self, subtensor: Any = None) -> None:
        pass


class FakeSubtensor:
    chain_endpoint = "fake://local"

    def __init__(self, n: int = 8, min_allowed: int = 0, max_weight: float = 1.0) -> None:
        self.n = n
        self.min_allowed = min_allowed
        self.max_weight = max_weight

    def get_current_block(self) -> int:
        return 1000

    def metagraph(self, netuid: int) -> FakeMetagraph:
        return FakeMetagraph(self.n)

    def min_allowed_weights(self, netuid: int, block=None) -> int:
        return self.min_allowed

    def max_weight_limit(self, netuid: int, block=None) -> float:
        return self.max_weight


# ---------------------------------------------------------------------------
# Representative cases
# ---------------------------------------------------------------------------

CASES = [
    {
        "id": "uniform",
        "description": "Uniform scores across all UIDs",
        "n": 8,
        "scores": [1.0] * 8,
        "min_allowed": 0,
        "max_weight": 1.0,
        "exclude_quantile": 0,
    },
    {
        "id": "single_dominant",
        "description": "One dominant UID, rest zero",
        "n": 8,
        "scores": [0.0, 0.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "min_allowed": 0,
        "max_weight": 1.0,
        "exclude_quantile": 0,
    },
    {
        "id": "two_split",
        "description": "Two UIDs split 75/25",
        "n": 8,
        "scores": [0.0, 0.0, 0.75, 0.0, 0.0, 0.25, 0.0, 0.0],
        "min_allowed": 0,
        "max_weight": 1.0,
        "exclude_quantile": 0,
    },
    {
        "id": "max_weight_limit_0.1",
        "description": "Capped max weight (0.1) spreads a dominant UID",
        "n": 8,
        "scores": [1.0, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1],
        "min_allowed": 0,
        "max_weight": 0.1,
        "exclude_quantile": 0,
    },
    {
        "id": "min_allowed_padding",
        "description": "min_allowed_weights forces epsilon padding",
        "n": 8,
        "scores": [0.0, 0.0, 0.0, 8.0, 0.0, 0.0, 0.0, 0.0],
        "min_allowed": 4,
        "max_weight": 1.0,
        "exclude_quantile": 0,
    },
    {
        "id": "exclude_quantile",
        "description": "exclude_quantile drops the lowest-weight UIDs",
        "n": 8,
        "scores": [0.0, 0.1, 0.4, 0.5, 0.0, 0.0, 0.0, 0.0],
        "min_allowed": 0,
        "max_weight": 1.0,
        "exclude_quantile": int(0.5 * 65535),
    },
    {
        "id": "all_zero",
        "description": "All-zero scores → uniform fallback",
        "n": 8,
        "scores": [0.0] * 8,
        "min_allowed": 0,
        "max_weight": 1.0,
        "exclude_quantile": 0,
    },
    {
        "id": "large_subnet",
        "description": "64-UID subnet with a few dominant accounts",
        "n": 64,
        "scores": [0.0] * 8 + [3.0, 0.0, 0.0, 7.0] + [0.0] * 49,
        "min_allowed": 1,
        "max_weight": 0.2,
        "exclude_quantile": 0,
    },
]


def run_pipeline(case: dict) -> dict[str, Any]:
    """Replay validator/weights.py::set_weights math (without the extrinsic)."""
    n = case["n"]
    scores = np.array(case["scores"], dtype=np.float32)
    subtensor = FakeSubtensor(n, min_allowed=case["min_allowed"], max_weight=case["max_weight"])
    metagraph = FakeMetagraph(n)

    raw_weights = normalize_scores(scores)
    processed_uids, processed_weights = process_weights_for_netuid(
        uids=metagraph.uids,
        weights=raw_weights,
        netuid=NETUID,
        subtensor=subtensor,
        metagraph=metagraph,
        exclude_quantile=case["exclude_quantile"],
    )
    uint_uids, uint_weights = convert_weights_and_uids_for_emit(processed_uids, processed_weights)

    return {
        "raw_weights": [float(x) for x in np.asarray(raw_weights)],
        "processed_uids": [int(x) for x in np.asarray(processed_uids)],
        "processed_weights": [float(x) for x in np.asarray(processed_weights)],
        "uint_uids": [int(x) for x in uint_uids],
        "uint_weights": [int(x) for x in uint_weights],
    }


def main() -> None:
    results = []
    for case in CASES:
        out = run_pipeline(case)
        results.append({**case, "expected": out})

    fixture = {"netuid": NETUID, "cases": results}
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(fixture, indent=2))
    print(f"Wrote {FIXTURE_PATH} ({len(results)} cases)")


if __name__ == "__main__":
    main()
