"""Simple integration test to validate YouTube evaluator integration."""

import pytest
from unittest.mock import Mock

from bitcast.validator.platforms.youtube.youtube_evaluator import YouTubeEvaluator
from bitcast.validator.reward_engine.models.miner_response import MinerResponse


class TestYouTubeIntegrationSimple:
    """Simple integration test for YouTube evaluator."""
    
    def test_youtube_evaluator_import_and_instantiation(self):
        """Test that YouTube evaluator can be imported and instantiated."""
        evaluator = YouTubeEvaluator()
        
        assert evaluator.platform_name() == "youtube"
        assert "YT_access_tokens" in evaluator.get_supported_token_types()
    
    def test_youtube_evaluator_response_detection(self):
        """Test that YouTube evaluator correctly detects YouTube responses."""
        evaluator = YouTubeEvaluator()
        
        # Valid YouTube response
        mock_response = Mock()
        mock_response.YT_access_tokens = ["test_token"]
        yt_response = MinerResponse.from_response(123, mock_response)
        
        assert evaluator.can_evaluate(yt_response) is True
        
        # Invalid response
        mock_response_invalid = Mock()
        mock_response_invalid.YT_access_tokens = []
        invalid_response = MinerResponse.from_response(456, mock_response_invalid)
        
        assert evaluator.can_evaluate(invalid_response) is False
    
    @pytest.mark.asyncio
    async def test_youtube_evaluator_graceful_error_handling(self):
        """Test that YouTube evaluator handles invalid credentials gracefully."""
        evaluator = YouTubeEvaluator()
        
        # Create miner response with invalid token
        mock_response = Mock()
        mock_response.YT_access_tokens = ["invalid_token"]
        miner_response = MinerResponse.from_response(123, mock_response)
        
        briefs = [
            {"id": "brief1", "title": "Test Brief 1"},
            {"id": "brief2", "title": "Test Brief 2"}
        ]
        
        # This should not crash, even with invalid credentials
        result = await evaluator.evaluate_accounts(
            miner_response, briefs, {"alpha_stake": 10000.0}
        )
        
        # Verify it returns a valid result structure
        assert result.uid == 123
        assert result.platform == "youtube"
        assert len(result.account_results) == 1  # One token processed
        
        # Should have zero scores due to invalid credentials
        assert all(score == 0.0 for score in result.aggregated_scores.values())
        
        # Account result should exist
        account_result = list(result.account_results.values())[0]
        assert account_result.account_id == "account_1"
        
        # Scores should be zero but structure should be correct
        assert account_result.scores == {"brief1": 0, "brief2": 0}


class TestEvaluateTokenBatch:
    """Test YouTubeEvaluator.evaluate_token_batch."""
    
    @pytest.mark.asyncio
    async def test_evaluate_token_batch_offset_naming(self):
        """Tokens are named with offset-based account IDs."""
        evaluator = YouTubeEvaluator()
        briefs = [{"id": "brief1", "title": "B1"}]
        
        result = await evaluator.evaluate_token_batch(
            uid=42,
            tokens=["invalid_tok_a", "invalid_tok_b"],
            account_offset=5,
            briefs=briefs,
            metagraph_info={"alpha_stake": 10000.0}
        )
        
        assert result.uid == 42
        assert result.platform == "youtube"
        assert "account_6" in result.account_results
        assert "account_7" in result.account_results
        assert len(result.account_results) == 2
    
    @pytest.mark.asyncio
    async def test_evaluate_token_batch_empty_tokens(self):
        """Empty tokens produce error results with correct naming."""
        evaluator = YouTubeEvaluator()
        briefs = [{"id": "brief1", "title": "B1"}]
        
        result = await evaluator.evaluate_token_batch(
            uid=10,
            tokens=["", None],
            account_offset=0,
            briefs=briefs,
            metagraph_info={"alpha_stake": 10000.0}
        )
        
        assert len(result.account_results) == 2
        assert "account_1" in result.account_results
        assert "account_2" in result.account_results
        for ar in result.account_results.values():
            assert ar.success is False
    
    @pytest.mark.asyncio
    async def test_evaluate_token_batch_scores_aggregate(self):
        """Aggregated scores sum across tokens in the batch."""
        evaluator = YouTubeEvaluator()
        briefs = [{"id": "brief1", "title": "B1"}, {"id": "brief2", "title": "B2"}]
        
        result = await evaluator.evaluate_token_batch(
            uid=1,
            tokens=["tok1", "tok2", "tok3"],
            account_offset=0,
            briefs=briefs,
            metagraph_info={"alpha_stake": 10000.0}
        )
        
        assert len(result.account_results) == 3
        # All scores should be 0.0 since tokens are invalid, but structure is correct
        for brief in briefs:
            assert brief["id"] in result.aggregated_scores


def test_eval_youtube_function_import():
    """Test that we can import the eval_youtube function directly."""
    from bitcast.validator.platforms.youtube.main import eval_youtube
    
    # Function should be callable
    assert callable(eval_youtube)
    assert eval_youtube.__name__ == "eval_youtube"


def test_youtube_config_imports():
    """Test that YouTube configuration can be imported."""
    from bitcast.validator.utils.config import (
        MAX_ACCOUNTS_PER_SYNAPSE, 
        YT_MIN_ALPHA_STAKE_THRESHOLD
    )
    
    # These should be valid numbers
    assert isinstance(MAX_ACCOUNTS_PER_SYNAPSE, int)
    assert isinstance(YT_MIN_ALPHA_STAKE_THRESHOLD, (int, float))
    assert MAX_ACCOUNTS_PER_SYNAPSE > 0
    # YT_MIN_ALPHA_STAKE_THRESHOLD can be 0 (meaning no minimum stake requirement)
    assert YT_MIN_ALPHA_STAKE_THRESHOLD >= 0 