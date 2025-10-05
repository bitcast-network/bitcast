"""
Tests for the streaming per-account publisher functionality.

Tests cover fire and forget streaming publishing of account data immediately after 
miner evaluation, ensuring the new system works independently from the monolithic flow.
The streaming publisher launches publishing tasks without waiting for results.
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
    @patch('bitcast.validator.utils.streaming_publisher.asyncio.create_task')
    @patch('bitcast.validator.utils.streaming_publisher.publish_single_account')
    @pytest.mark.asyncio
    async def test_publish_miner_accounts_success(self, mock_publish_single, mock_create_task):
        """Test successful fire and forget streaming publishing for a miner's accounts."""
        mock_publish_single.return_value = True
        
        result = await publish_miner_accounts(
            self.evaluation_result,
            self.run_id,
            self.mock_wallet
        )
        
        assert result is None  # Fire and forget returns None
        assert mock_create_task.call_count == 2  # Two tasks launched
        
        # Verify that tasks were created for the publish_single_account calls
        assert mock_create_task.called
    
    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', False)
    @patch('bitcast.validator.utils.streaming_publisher.asyncio.create_task')
    @patch('bitcast.validator.utils.streaming_publisher.publish_single_account')
    @pytest.mark.asyncio
    async def test_publish_miner_accounts_disabled(self, mock_publish_single, mock_create_task):
        """Test that streaming is skipped when disabled."""
        result = await publish_miner_accounts(
            self.evaluation_result,
            self.run_id,
            self.mock_wallet
        )
        
        assert result is None  # Fire and forget returns None
        mock_publish_single.assert_not_called()
        mock_create_task.assert_not_called()
    
    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', True)
    @patch('bitcast.validator.utils.streaming_publisher.asyncio.create_task')
    @patch('bitcast.validator.utils.streaming_publisher.publish_single_account')
    @pytest.mark.asyncio
    async def test_publish_miner_accounts_no_accounts(self, mock_publish_single, mock_create_task):
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
        
        assert result is None  # Fire and forget returns None
        mock_publish_single.assert_not_called()
        mock_create_task.assert_not_called()
    
    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', True)
    @patch('bitcast.validator.utils.streaming_publisher.asyncio.create_task')
    @patch('bitcast.validator.utils.streaming_publisher.publish_single_account')
    @pytest.mark.asyncio
    async def test_publish_miner_accounts_fire_and_forget(self, mock_publish_single, mock_create_task):
        """Test that streaming launches tasks without waiting for results (fire and forget)."""
        # Fire and forget doesn't care about success/failure, just launches tasks
        mock_publish_single.return_value = True
        
        result = await publish_miner_accounts(
            self.evaluation_result,
            self.run_id,
            self.mock_wallet
        )
        
        assert result is None  # Fire and forget returns None
        assert mock_create_task.call_count == 2  # Two tasks launched
    
    @patch('bitcast.validator.utils.streaming_publisher.asyncio.create_task')
    def test_publish_miner_accounts_safe_wrapper(self, mock_create_task):
        """Test the safe wrapper that never raises exceptions (fire and forget)."""
        # Mock create_task to raise an exception
        mock_create_task.side_effect = Exception("Unexpected error")
        
        # Should not raise exception (fire and forget)
        publish_miner_accounts_safe(
            self.evaluation_result,
            self.run_id,
            self.mock_wallet
        )
        
        # Should have attempted to create task
        mock_create_task.assert_called_once()
    
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

    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', False)
    @patch('bitcast.validator.utils.streaming_publisher.asyncio.create_task')
    @patch('bitcast.validator.utils.streaming_publisher.publish_single_account')
    def test_publish_miner_accounts_safe_disabled_weights(self, mock_publish_single, mock_create_task):
        """Test that publishing is skipped when ENABLE_DATA_PUBLISH is False (disable_set_weights mode)."""
        # Should create the task (since that's how the safe wrapper works)
        # But the actual publishing should be skipped due to ENABLE_DATA_PUBLISH=False
        publish_miner_accounts_safe(
            self.evaluation_result,
            self.run_id,
            self.mock_wallet
        )
        
        # Task should be created (the wrapper creates it)
        mock_create_task.assert_called_once()
        # But actual publishing should not happen due to ENABLE_DATA_PUBLISH=False
        mock_publish_single.assert_not_called()


class TestStreamingPublisherIntegration:
    """Integration tests for streaming publisher with real data structures."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_wallet = Mock()
        self.mock_wallet.hotkey.ss58_address = "test_validator_hotkey"
        
    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', True)
    @patch('bitcast.validator.utils.streaming_publisher.asyncio.create_task')
    @patch('bitcast.validator.utils.streaming_publisher.publish_single_account')
    @pytest.mark.asyncio
    async def test_realistic_streaming_scenario(self, mock_publish_single, mock_create_task):
        """Test fire and forget streaming with realistic evaluation result structure."""
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
        
        assert result is None  # Fire and forget returns None
        mock_create_task.assert_called_once()  # One task launched for one account