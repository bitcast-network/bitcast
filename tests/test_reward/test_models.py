"""Reward engine model behaviour."""

import numpy as np

from bitcast.protocol import AccessTokenSynapse
from bitcast.validator.reward.models import (
    AccountResult,
    EvaluationResult,
    MinerResponse,
    ScoreMatrix,
)


class TestMinerResponse:
    def test_from_none_synapse_is_invalid(self):
        response = MinerResponse.from_synapse(3, None)
        assert not response.is_valid
        assert not response.has_tokens

    def test_from_synapse_with_tokens(self):
        synapse = AccessTokenSynapse(YT_access_tokens=["a", "b"])
        response = MinerResponse.from_synapse(3, synapse)
        assert response.is_valid and response.has_tokens
        assert response.tokens == ["a", "b"]

    def test_from_synapse_with_none_tokens(self):
        response = MinerResponse.from_synapse(3, AccessTokenSynapse())
        assert response.is_valid and not response.has_tokens

    def test_error_response(self):
        response = MinerResponse.error(3, "timeout")
        assert not response.is_valid and response.error_message == "timeout"


class TestEvaluationResult:
    def test_merge_sums_scores_and_collects_accounts(self):
        first = EvaluationResult(uid=1, platform="youtube", aggregated_scores={"b1": 2.0})
        first.add_account_result(AccountResult(account_id="account_1", scores={"b1": 2.0}))
        second = EvaluationResult(uid=1, platform="youtube", aggregated_scores={"b1": 3.0, "b2": 1.0})
        second.add_account_result(AccountResult(account_id="account_2", scores={"b1": 3.0, "b2": 1.0}))

        first.merge(second)
        assert first.aggregated_scores == {"b1": 5.0, "b2": 1.0}
        assert set(first.account_results) == {"account_1", "account_2"}

    def test_error_result_zeroes_all_briefs(self):
        briefs = [{"id": "b1"}, {"id": "b2"}]
        account = AccountResult.error_result("account_1", "bad token", briefs)
        assert account.scores == {"b1": 0.0, "b2": 0.0}
        assert not account.success


class TestScoreMatrix:
    def test_empty_shape(self):
        matrix = ScoreMatrix.empty(3, 2)
        assert matrix.num_miners == 3 and matrix.num_briefs == 2
        assert matrix.matrix.dtype == np.float64

    def test_to_dict(self):
        matrix = ScoreMatrix.empty(1, 1)
        matrix.matrix[0, 0] = 5.0
        assert matrix.to_dict() == {"matrix": [[5.0]], "num_miners": 1, "num_briefs": 1}
