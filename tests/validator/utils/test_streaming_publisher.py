"""
Tests for the streaming per-account publisher functionality.

Tests cover streaming publishing of account data immediately after miner evaluation,
ensuring the new system works independently from the monolithic flow.
"""

import pytest
import bittensor as bt
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any

from bitcast.validator.utils.streaming_publisher import (
    publish_miner_accounts,
    publish_miner_accounts_safe,
    log_streaming_status
)
from bitcast.validator.reward_engine.models.evaluation_result import EvaluationResult, AccountResult


class TestStreamingPublisher:
    """Test cases for streaming per-account publisher."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_wallet = Mock()
        self.mock_wallet.hotkey.ss58_address = "test_validator_hotkey"
        
        # Create test account results
        self.account_result_1 = AccountResult(
            account_id="account_1",
            platform_data={"channel_id": "test_channel_1"},
            videos={"video_1": {"title": "Test Video 1"}},
            scores={"brief1": 2.5, "brief2": 1.8},
            performance_stats={"total_score": 4.3},
            success=True
        )
        
        self.account_result_2 = AccountResult(
            account_id="account_2", 
            platform_data={"channel_id": "test_channel_2"},
            videos={"video_2": {"title": "Test Video 2"}},
            scores={"brief1": 1.2, "brief2": 2.1},
            performance_stats={"total_score": 3.3},
            success=True
        )
        
        # Create test evaluation result
        self.evaluation_result = EvaluationResult(
            uid=123,
            platform="youtube",
            aggregated_scores={"brief1": 3.7, "brief2": 3.9},
            account_results={
                "account_1": self.account_result_1,
                "account_2": self.account_result_2
            }
        )
        
        self.run_id = "vali_test_20250106_120000"
    
    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', True)
    @patch('bitcast.validator.utils.streaming_publisher.publish_single_account')
    @pytest.mark.asyncio
    async def test_publish_miner_accounts_success(self, mock_publish_single):
        """Test successful streaming publishing for a miner's accounts."""
        mock_publish_single.return_value = True
        
        result = await publish_miner_accounts(
            self.evaluation_result,
            self.run_id,
            self.mock_wallet
        )
        
        assert result is True
        assert mock_publish_single.call_count == 2  # Two accounts
        
        # Verify first account call
        first_call = mock_publish_single.call_args_list[0]
        assert first_call[1]["wallet"] == self.mock_wallet
        assert first_call[1]["run_id"] == self.run_id
        assert first_call[1]["miner_uid"] == 123
        assert first_call[1]["account_id"] == "account_1"
        assert first_call[1]["platform"] == "youtube"
    
    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', False)
    @patch('bitcast.validator.utils.streaming_publisher.publish_single_account')
    @pytest.mark.asyncio
    async def test_publish_miner_accounts_disabled(self, mock_publish_single):
        """Test that streaming is skipped when disabled."""
        result = await publish_miner_accounts(
            self.evaluation_result,
            self.run_id,
            self.mock_wallet
        )
        
        assert result is True
        mock_publish_single.assert_not_called()
    
    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', True)
    @patch('bitcast.validator.utils.streaming_publisher.publish_single_account')
    @pytest.mark.asyncio
    async def test_publish_miner_accounts_no_accounts(self, mock_publish_single):
        """Test streaming with no account results."""
        empty_result = EvaluationResult(
            uid=456,
            platform="youtube",
            aggregated_scores={"brief1": 0.0},
            account_results={}
        )
        
        result = await publish_miner_accounts(
            empty_result,
            self.run_id,
            self.mock_wallet
        )
        
        assert result is True
        mock_publish_single.assert_not_called()
    
    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', True)
    @patch('bitcast.validator.utils.streaming_publisher.publish_single_account')
    @pytest.mark.asyncio
    @pytest.mark.parametrize("failure_scenario,side_effect,expected_result", [
        ("partial_failure", [True, False], True),  # Some succeed
        ("all_failures", [False, False], False),   # All fail
        ("with_exceptions", [True, Exception("Network error")], True),  # Exception handled
        ("all_exceptions", [Exception("Error1"), Exception("Error2")], False),  # All exceptions
    ])
    async def test_publish_miner_accounts_failures(self, mock_publish_single, failure_scenario, side_effect, expected_result):
        """Test streaming with various failure scenarios."""
        mock_publish_single.side_effect = side_effect
        
        result = await publish_miner_accounts(
            self.evaluation_result,
            self.run_id,
            self.mock_wallet
        )
        
        assert result is expected_result
        assert mock_publish_single.call_count == 2
    
    @patch('bitcast.validator.utils.streaming_publisher.publish_miner_accounts')
    @pytest.mark.asyncio
    async def test_publish_miner_accounts_safe_wrapper(self, mock_publish):
        """Test the safe wrapper that never raises exceptions."""
        # Mock the function to raise an exception
        mock_publish.side_effect = Exception("Unexpected error")
        
        # Should not raise exception
        await publish_miner_accounts_safe(
            self.evaluation_result,
            self.run_id,
            self.mock_wallet
        )
        
        mock_publish.assert_called_once_with(
            self.evaluation_result,
            self.run_id,
            self.mock_wallet
        )
    
    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', True)
    def test_log_streaming_status_enabled(self, caplog):
        """Test logging when streaming is enabled."""
        log_streaming_status(50)
        
        # Check that appropriate logs were created (we can't easily assert on bt.logging)
        # This test mainly ensures the function runs without error
    
    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', False)  
    def test_log_streaming_status_disabled(self, caplog):
        """Test logging when streaming is disabled."""
        log_streaming_status(50)
        
        # Check that appropriate logs were created (we can't easily assert on bt.logging)
        # This test mainly ensures the function runs without error


class TestStreamingPublisherIntegration:
    """Integration tests for streaming publisher with real data structures."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_wallet = Mock()
        self.mock_wallet.hotkey.ss58_address = "test_validator_hotkey"
        
    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', True)
    @patch('bitcast.validator.utils.streaming_publisher.publish_single_account')
    @pytest.mark.asyncio
    async def test_realistic_streaming_scenario(self, mock_publish_single):
        """Test streaming with realistic evaluation result structure."""
        mock_publish_single.return_value = True
        
        # Create realistic account result
        account_result = AccountResult(
            account_id="UC_realistic_channel_id",
            platform_data={
                "channel_id": "UC_realistic_channel_id",
                "subscriber_count": 15000,
                "view_count": 500000
            },
            videos={
                "video_123": {
                    "title": "Realistic Test Video",
                    "view_count": 25000,
                    "like_count": 750
                }
            },
            scores={
                "brief_crypto_analysis": 2.8,
                "brief_market_update": 1.9
            },
            performance_stats={
                "total_score": 4.7,
                "avg_retention": 65.2,
                "engagement_rate": 3.1
            },
            success=True
        )
        
        evaluation_result = EvaluationResult(
            uid=789,
            platform="youtube",
            aggregated_scores={
                "brief_crypto_analysis": 2.8,
                "brief_market_update": 1.9
            },
            account_results={
                "UC_realistic_channel_id": account_result
            }
        )
        
        run_id = "vali_5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY_20250106_143000"
        
        result = await publish_miner_accounts(
            evaluation_result,
            run_id,
            self.mock_wallet
        )
        
        assert result is True
        mock_publish_single.assert_called_once()
        
        # Verify the call structure matches expected format
        call_kwargs = mock_publish_single.call_args[1]
        assert call_kwargs["wallet"] == self.mock_wallet
        assert call_kwargs["run_id"] == run_id
        assert call_kwargs["miner_uid"] == 789
        assert call_kwargs["account_id"] == "UC_realistic_channel_id"
        assert call_kwargs["platform"] == "youtube"
        
        # Verify account data structure
        account_data = call_kwargs["account_data"]
        assert "yt_account" in account_data
        assert "videos" in account_data
        assert "scores" in account_data
        assert "performance_stats" in account_data
        assert account_data["success"] is True