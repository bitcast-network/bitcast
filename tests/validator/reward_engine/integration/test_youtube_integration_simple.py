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