"""Unit tests for ScoreAggregationService."""

import pytest
from bitcast.validator.reward_engine.services.score_aggregation_service import ScoreAggregationService
from bitcast.validator.reward_engine.models.evaluation_result import (
    EvaluationResult, AccountResult, EvaluationResultCollection
)


class TestScoreAggregationService:
    """Test ScoreAggregationService class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = ScoreAggregationService()
        self.briefs = [
            {"id": "brief1", "title": "Test Brief 1"},
            {"id": "brief2", "title": "Test Brief 2"}
        ]
    
    def test_aggregate_scores_single_miner(self):
        """Test aggregating scores for a single miner."""
        # Create evaluation results
        results = EvaluationResultCollection()
        
        # Create account results
        account1 = AccountResult(
            account_id="account1",
            platform_data={},
            videos={},
            scores={"brief1": 0.5, "brief2": 0.3},
            performance_stats={},
            success=True
        )
        account2 = AccountResult(
            account_id="account2", 
            platform_data={},
            videos={},
            scores={"brief1": 0.2, "brief2": 0.4},
            performance_stats={},
            success=True
        )
        
        # Create evaluation result
        eval_result = EvaluationResult(uid=123, platform="youtube")
        eval_result.add_account_result("account1", account1)
        eval_result.add_account_result("account2", account2)
        
        results.add_result(123, eval_result)
        
        # Aggregate scores
        score_matrix = self.service.aggregate_scores(results, self.briefs)
        
        # Check results
        assert score_matrix.num_miners == 1
        assert score_matrix.num_briefs == 2
        assert score_matrix.get_score(0, 0) == 0.7  # 0.5 + 0.2 for brief1
        assert score_matrix.get_score(0, 1) == 0.7  # 0.3 + 0.4 for brief2
    
    def test_aggregate_scores_multiple_miners(self):
        """Test aggregating scores for multiple miners."""
        results = EvaluationResultCollection()
        
        # Miner 1
        account1 = AccountResult(
            account_id="account1",
            platform_data={},
            videos={},
            scores={"brief1": 1.0, "brief2": 0.5},
            performance_stats={},
            success=True
        )
        eval_result1 = EvaluationResult(uid=123, platform="youtube")
        eval_result1.add_account_result("account1", account1)
        results.add_result(123, eval_result1)
        
        # Miner 2
        account2 = AccountResult(
            account_id="account1",
            platform_data={},
            videos={},
            scores={"brief1": 0.3, "brief2": 0.8},
            performance_stats={},
            success=True
        )
        eval_result2 = EvaluationResult(uid=456, platform="youtube")
        eval_result2.add_account_result("account1", account2)
        results.add_result(456, eval_result2)
        
        # Aggregate scores
        score_matrix = self.service.aggregate_scores(results, self.briefs)
        
        # Check results
        assert score_matrix.num_miners == 2
        assert score_matrix.num_briefs == 2
        # Note: order depends on dict iteration order, let's check both possibilities
        scores = [
            (score_matrix.get_score(0, 0), score_matrix.get_score(0, 1)),
            (score_matrix.get_score(1, 0), score_matrix.get_score(1, 1))
        ]
        assert (1.0, 0.5) in scores
        assert (0.3, 0.8) in scores
    
    def test_aggregate_brief_scores(self):
        """Test the _aggregate_brief_scores method."""
        # Create evaluation result with multiple accounts
        eval_result = EvaluationResult(uid=123, platform="youtube")
        
        account1 = AccountResult(
            account_id="account1",
            platform_data={},
            videos={},
            scores={"brief1": 0.5, "brief2": 0.3},
            performance_stats={},
            success=True
        )
        account2 = AccountResult(
            account_id="account2",
            platform_data={},
            videos={},
            scores={"brief1": 0.2, "brief2": 0.4},
            performance_stats={},
            success=True
        )
        
        eval_result.add_account_result("account1", account1)
        eval_result.add_account_result("account2", account2)
        
        # Test aggregation
        total_brief1 = self.service._aggregate_brief_scores(eval_result, "brief1")
        total_brief2 = self.service._aggregate_brief_scores(eval_result, "brief2")
        
        assert total_brief1 == 0.7  # 0.5 + 0.2
        assert total_brief2 == 0.7  # 0.3 + 0.4
    
    def test_aggregate_scores_empty_results(self):
        """Test aggregating with empty results."""
        results = EvaluationResultCollection()
        score_matrix = self.service.aggregate_scores(results, self.briefs)
        
        assert score_matrix.num_miners == 0
        assert score_matrix.num_briefs == 2 