"""Weight-emission parity harness.

``fixtures/parity.json`` holds representative score vectors plus the EXACT
outputs of the full weight-processing pipeline (generated via
``generate_fixtures.py``). These tests replay the pipeline on identical inputs
and assert ``np.array_equal`` on every stage — raw weights, processed uids/
weights, and the final u16 weight vector — so a refactor of the vendored
``weight_utils`` or ``normalize_scores`` can never silently diverge this
validator's on-chain weights from the rest of the subnet.

Covered: uniform scores, a single dominant UID, a two-way split, max-weight
capping, min-allowed epsilon padding, exclude-quantile pruning, the all-zero
uniform fallback, and a larger 64-UID subnet.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from bitcast.chain.weight_utils import (
    convert_weights_and_uids_for_emit,
    process_weights_for_netuid,
)
from bitcast.validator.weights import normalize_scores
from tests.conftest import FakeMetagraph, FakeSubtensor

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "parity.json"


@pytest.fixture(scope="module")
def fixture():
    with open(FIXTURE_PATH) as f:
        return json.load(f)


def _run_pipeline(case, n: int):
    scores = np.array(case["scores"], dtype=np.float32)
    subtensor = FakeSubtensor(n, min_allowed=case["min_allowed"], max_weight=case["max_weight"])
    metagraph = FakeMetagraph(n)

    raw_weights = normalize_scores(scores)
    processed_uids, processed_weights = process_weights_for_netuid(
        uids=metagraph.uids,
        weights=raw_weights,
        netuid=93,
        subtensor=subtensor,
        metagraph=metagraph,
        exclude_quantile=case["exclude_quantile"],
    )
    uint_uids, uint_weights = convert_weights_and_uids_for_emit(processed_uids, processed_weights)
    return raw_weights, processed_uids, processed_weights, uint_uids, uint_weights


@pytest.mark.parametrize("idx", range(8))
def test_pipeline_parity(fixture, idx):
    case = fixture["cases"][idx]
    expected = case["expected"]
    n = case["n"]

    raw, p_uids, p_weights, u_uids, u_weights = _run_pipeline(case, n)

    # processed_weights are float32; JSON round-trips them as float64, so cast
    # the expected values back to float32 for a byte-exact comparison.
    assert np.array_equal(raw, np.array(expected["raw_weights"], dtype=np.float32)), case["description"]
    assert list(np.asarray(p_uids)) == expected["processed_uids"], case["description"]
    assert np.array_equal(
        np.asarray(p_weights, dtype=np.float32), np.array(expected["processed_weights"], dtype=np.float32)
    ), case["description"]
    assert u_uids == expected["uint_uids"], case["description"]
    assert u_weights == expected["uint_weights"], case["description"]


def test_uint_weights_sum_consistent(fixture):
    """Emitted u16 weights are max-upscaled (max → U16_MAX), not sum-normalized."""
    for case in fixture["cases"]:
        weights = case["expected"]["uint_weights"]
        if weights:
            assert max(weights) == 65535
