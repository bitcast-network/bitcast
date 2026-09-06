"""Golden tests for the vendored (verbatim) weight_utils.

This module is consensus-critical: it was vendored VERBATIM from the bittensor
10.3.0 SDK (bittensor/utils/weight_utils.py). These tests pin the exact numeric
behavior — u16 conversion, max-upscale, zero filtering, min-allowed-weights
fallbacks, exclude-quantile, and max-weight-limit normalization — so no
"improvement" to the vendored code can silently diverge this validator's weights
from the rest of the network.
"""

import numpy as np
import pytest

from bitcast.chain.weight_utils import (
    U16_MAX,
    convert_weights_and_uids_for_emit,
    normalize_max_weight,
    process_weights_for_netuid,
)
from tests.conftest import FakeMetagraph, FakeSubtensor


class TestConvertWeightsAndUidsForEmit:
    def test_max_upscale_and_u16(self):
        uids = np.array([1, 2, 3])
        weights = np.array([0.5, 0.25, 0.25])
        out_uids, out_weights = convert_weights_and_uids_for_emit(uids, weights)
        # max-upscale: max weight → exactly 65535; others scaled by the same factor
        assert out_weights == [U16_MAX, round(0.5 * U16_MAX), round(0.5 * U16_MAX)]
        assert out_uids == [1, 2, 3]

    def test_zero_weights_filtered(self):
        uids = np.array([0, 1, 2])
        weights = np.array([0.0, 1.0, 0.0])
        out_uids, out_weights = convert_weights_and_uids_for_emit(uids, weights)
        assert out_uids == [1]
        assert out_weights == [U16_MAX]

    def test_all_zero_returns_empty(self):
        uids = np.array([0, 1])
        weights = np.array([0.0, 0.0])
        assert convert_weights_and_uids_for_emit(uids, weights) == ([], [])

    def test_tiny_weights_round_to_zero_are_dropped(self):
        uids = np.array([1, 2])
        weights = np.array([1.0, 1e-9])
        out_uids, out_weights = convert_weights_and_uids_for_emit(uids, weights)
        assert out_uids == [1]
        assert out_weights == [U16_MAX]

    def test_negative_weight_raises(self):
        with pytest.raises(ValueError):
            convert_weights_and_uids_for_emit(np.array([1]), np.array([-0.1]))

    def test_negative_uid_raises(self):
        with pytest.raises(ValueError):
            convert_weights_and_uids_for_emit(np.array([-1]), np.array([0.5]))

    def test_length_mismatch_raises(self):
        # The verbatim code hits the boolean-mask indexing before its explicit
        # length check, so the mismatch surfaces as IndexError (pinned as-is).
        with pytest.raises((ValueError, IndexError)):
            convert_weights_and_uids_for_emit(np.array([1, 2]), np.array([0.5]))


class TestNormalizeMaxWeight:
    def test_sum_zero_returns_uniform(self):
        x = np.array([0.0, 0.0, 0.0, 0.0])
        result = normalize_max_weight(x, limit=0.5)
        assert np.array_equal(result, np.full(4, 0.25))

    def test_limit_too_small_returns_uniform(self):
        # len(x) * limit <= 1 → uniform
        x = np.array([1.0, 2.0])
        result = normalize_max_weight(x, limit=0.5)
        assert np.array_equal(result, np.full(2, 0.5))

    def test_under_limit_normalizes_plain(self):
        x = np.array([1.0, 1.0, 2.0])
        result = normalize_max_weight(x, limit=0.6)
        assert np.array_equal(result, x / x.sum())

    def test_over_limit_caps_max(self):
        x = np.array([1.0, 1.0, 8.0])
        limit = 0.4
        result = normalize_max_weight(x, limit=limit)
        assert result.sum() == pytest.approx(1.0)
        assert result.max() == pytest.approx(limit, abs=1e-6)
        # smaller entries keep their relative proportion
        assert result[0] == result[1]

    def test_output_sums_to_one(self):
        rng = np.random.default_rng(42)
        x = rng.random(50)
        result = normalize_max_weight(x, limit=0.1)
        assert result.sum() == pytest.approx(1.0)
        assert result.max() <= 0.1 + 1e-6


class TestProcessWeightsForNetuid:
    def test_all_zero_returns_uniform(self):
        n = 8
        subtensor = FakeSubtensor(n)
        metagraph = FakeMetagraph(n)
        uids = np.arange(n)
        weights = np.zeros(n, dtype=np.float32)
        out_uids, out_weights = process_weights_for_netuid(
            uids, weights, netuid=93, subtensor=subtensor, metagraph=metagraph
        )
        assert np.array_equal(out_uids, np.arange(n))
        assert np.array_equal(out_weights, np.full(n, 1.0 / n))

    def test_below_min_allowed_pads_with_epsilon(self):
        n = 8
        subtensor = FakeSubtensor(n)
        subtensor.min_allowed = 4
        metagraph = FakeMetagraph(n)
        uids = np.arange(n)
        weights = np.zeros(n, dtype=np.float32)
        weights[3] = 1.0
        out_uids, out_weights = process_weights_for_netuid(
            uids, weights, netuid=93, subtensor=subtensor, metagraph=metagraph
        )
        # every uid present, weight mass concentrated on uid 3
        assert np.array_equal(out_uids, np.arange(n))
        assert out_weights.sum() == pytest.approx(1.0)
        assert out_weights[3] == out_weights.max()

    def test_normal_path_normalizes_nonzero(self):
        n = 8
        subtensor = FakeSubtensor(n)
        metagraph = FakeMetagraph(n)
        uids = np.arange(n)
        weights = np.zeros(n, dtype=np.float32)
        weights[2] = 0.75
        weights[5] = 0.25
        out_uids, out_weights = process_weights_for_netuid(
            uids, weights, netuid=93, subtensor=subtensor, metagraph=metagraph
        )
        assert list(out_uids) == [2, 5]
        assert np.array_equal(out_weights, np.array([0.75, 0.25], dtype=np.float32))

    def test_exclude_quantile_drops_lowest(self):
        n = 8
        subtensor = FakeSubtensor(n)
        metagraph = FakeMetagraph(n)
        uids = np.arange(n)
        weights = np.zeros(n, dtype=np.float32)
        weights[1] = 0.1
        weights[2] = 0.4
        weights[3] = 0.5
        # exclude_quantile is in u16 units: half the distribution
        out_uids, out_weights = process_weights_for_netuid(
            uids,
            weights,
            netuid=93,
            subtensor=subtensor,
            metagraph=metagraph,
            exclude_quantile=int(0.5 * U16_MAX),
        )
        assert 1 not in list(out_uids)
        assert out_weights.sum() == pytest.approx(1.0)
