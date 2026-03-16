"""
Tests for the streaming per-account publisher functionality.

Tests cover bounded streaming publishing of account data immediately after
miner evaluation, ensuring the new system works independently from the monolithic flow.
"""

import pytest
import bittensor as bt
from unittest.mock import Mock, patch, AsyncMock

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
    @patch('bitcast.validator.utils.streaming_publisher.publish_single_account', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_publish_miner_accounts_success(self, mock_publish_single):
        """Test successful bounded streaming publishing for a miner's accounts."""
        mock_publish_single.return_value = True

        await publish_miner_accounts(
            self.evaluation_result,
            self.run_id,
            self.mock_wallet
        )

        assert mock_publish_single.call_count == 2

    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', False)
    @patch('bitcast.validator.utils.streaming_publisher.publish_single_account', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_publish_miner_accounts_disabled(self, mock_publish_single):
        """Test that streaming is skipped when disabled."""
        await publish_miner_accounts(
            self.evaluation_result,
            self.run_id,
            self.mock_wallet
        )

        mock_publish_single.assert_not_called()

    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', True)
    @patch('bitcast.validator.utils.streaming_publisher.publish_single_account', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_publish_miner_accounts_no_accounts(self, mock_publish_single):
        """Test streaming with no account results."""
        empty_result = EvaluationResult(
            uid=456,
            platform="youtube",
            aggregated_scores={"brief1": 0.0},
            account_results={}
        )

        await publish_miner_accounts(
            empty_result,
            self.run_id,
            self.mock_wallet
        )

        mock_publish_single.assert_not_called()

    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', True)
    @patch('bitcast.validator.utils.streaming_publisher.publish_single_account', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_publish_miner_accounts_awaits_all_tasks(self, mock_publish_single):
        """Test that publishing awaits all tasks (bounded, not fire-and-forget)."""
        mock_publish_single.return_value = True

        await publish_miner_accounts(
            self.evaluation_result,
            self.run_id,
            self.mock_wallet
        )

        # All tasks should have completed (awaited via gather)
        assert mock_publish_single.call_count == 2

    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', True)
    @patch('bitcast.validator.utils.streaming_publisher.publish_single_account', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_publish_miner_accounts_handles_failures(self, mock_publish_single):
        """Test that individual publishing failures are logged but don't crash."""
        mock_publish_single.side_effect = Exception("Network error")

        # Should not raise
        await publish_miner_accounts(
            self.evaluation_result,
            self.run_id,
            self.mock_wallet
        )

    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', True)
    @patch('bitcast.validator.utils.streaming_publisher.publish_single_account', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_publish_miner_accounts_safe_wrapper(self, mock_publish_single):
        """Test the safe wrapper that never raises exceptions."""
        mock_publish_single.side_effect = Exception("Unexpected error")

        # Should not raise
        await publish_miner_accounts_safe(
            self.evaluation_result,
            self.run_id,
            self.mock_wallet
        )

    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', True)
    def test_log_streaming_status_enabled(self, caplog):
        """Test logging when streaming is enabled."""
        log_streaming_status(50)

    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', False)
    def test_log_streaming_status_disabled(self, caplog):
        """Test logging when streaming is disabled."""
        log_streaming_status(50)

    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', False)
    @patch('bitcast.validator.utils.streaming_publisher.publish_single_account', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_publish_miner_accounts_safe_disabled(self, mock_publish_single):
        """Test that publishing is skipped when ENABLE_DATA_PUBLISH is False."""
        await publish_miner_accounts_safe(
            self.evaluation_result,
            self.run_id,
            self.mock_wallet
        )

        mock_publish_single.assert_not_called()


class TestStreamingPublisherIntegration:
    """Integration tests for streaming publisher with real data structures."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_wallet = Mock()
        self.mock_wallet.hotkey.ss58_address = "test_validator_hotkey"

    @patch('bitcast.validator.utils.streaming_publisher.ENABLE_DATA_PUBLISH', True)
    @patch('bitcast.validator.utils.streaming_publisher.publish_single_account', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_realistic_streaming_scenario(self, mock_publish_single):
        """Test bounded streaming with realistic evaluation result structure."""
        mock_publish_single.return_value = True

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

        await publish_miner_accounts(
            evaluation_result,
            run_id,
            self.mock_wallet
        )

        mock_publish_single.assert_called_once()
