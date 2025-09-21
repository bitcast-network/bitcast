"""
Tests for DataPublisher classes and account data publishing functionality.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

import bittensor as bt
import aiohttp

from bitcast.validator.utils.data_publisher import (
    DataPublisher,
    UnifiedDataPublisher,
    publish_single_account
)


class TestDataPublisher:
    """Test cases for DataPublisher abstract base class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create mock wallet
        self.mock_wallet = Mock()
        self.mock_hotkey = Mock()
        self.mock_hotkey.ss58_address = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
        self.mock_wallet.hotkey = self.mock_hotkey
        
        # Create concrete implementation for testing
        class ConcreteDataPublisher(DataPublisher):
            async def publish_data(self, data, endpoint):
                return True
        
        self.publisher = ConcreteDataPublisher(self.mock_wallet)
    
    def test_data_publisher_initialization(self):
        """Test DataPublisher initializes correctly."""
        assert self.publisher.wallet == self.mock_wallet
        assert self.publisher.timeout_seconds == 10
    
    def test_data_publisher_custom_timeout(self):
        """Test DataPublisher with custom timeout."""
        class ConcreteDataPublisher(DataPublisher):
            async def publish_data(self, data, endpoint):
                return True
        
        publisher = ConcreteDataPublisher(self.mock_wallet, timeout_seconds=30)
        assert publisher.timeout_seconds == 30
    
    @patch('bitcast.validator.utils.data_publisher.convert_numpy_types')
    @patch('bitcast.validator.utils.data_publisher.datetime')
    def test_sign_message(self, mock_datetime, mock_convert):
        """Test message signing follows publish_stats.py pattern exactly."""
        # Mock datetime
        mock_datetime.utcnow.return_value.isoformat.return_value = "2025-01-06T12:00:00"
        
        # Create realistic payload structure with account_data
        account_data = {"yt_account": {"channel_id": "UC123"}, "videos": {}, "scores": {}}
        test_payload = {
            "run_id": "test_run_123",
            "platform": "youtube", 
            "miner_uid": 456,
            "account_id": "account_1",
            "account_data": account_data
        }
        
        # Mock convert_numpy_types to return the input (simulating successful conversion)
        mock_convert.side_effect = lambda x: x  # Return input unchanged for testing
        
        # Mock signature
        mock_signature = Mock()
        mock_signature.hex.return_value = "0x123456789abcdef"
        self.mock_hotkey.sign.return_value = mock_signature
        
        result = self.publisher._sign_message(test_payload)
        
        # Verify structure - should include original payload + signature/signer
        expected_keys = ["run_id", "platform", "miner_uid", "account_id", "account_data", "signature", "signer"]
        assert all(key in result for key in expected_keys)
        
        # Verify values
        assert result["run_id"] == "test_run_123"
        assert result["platform"] == "youtube"
        assert result["signature"] == "0x123456789abcdef"
        assert result["signer"] == "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
        
        # Verify signing call - should sign only the account_data portion (like publish_stats.py)
        expected_message = f"5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY:2025-01-06T12:00:00:{json.dumps(account_data, sort_keys=True)}"
        self.mock_hotkey.sign.assert_called_once_with(data=expected_message)
    
    @patch('bitcast.validator.utils.data_publisher.bt')
    def test_log_success(self, mock_bt):
        """Test success logging."""
        self.publisher._log_success("http://test.com", "test data")
        mock_bt.logging.info.assert_called_once_with("Successfully published test data")
    
    @patch('bitcast.validator.utils.data_publisher.bt')
    def test_log_error(self, mock_bt):
        """Test error logging."""
        error = Exception("Test error")
        self.publisher._log_error("http://test.com", error, "test data")
        mock_bt.logging.error.assert_called_once_with("Failed to publish test data to http://test.com: Test error")



class TestPublishSingleAccountFunction:
    """Test cases for publish_single_account convenience function."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create mock wallet
        self.mock_wallet = Mock()
        self.mock_hotkey = Mock()
        self.mock_hotkey.ss58_address = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
        self.mock_wallet.hotkey = self.mock_hotkey
    
    @patch('bitcast.validator.utils.data_publisher.UnifiedDataPublisher')
    @pytest.mark.asyncio
    async def test_publish_single_account_success(self, mock_publisher_class):
        """Test publish_single_account convenience function using unified format."""
        # Mock unified publisher
        mock_publisher = AsyncMock()
        mock_publisher.publish_unified_payload = AsyncMock(return_value=True)
        mock_publisher_class.return_value = mock_publisher
        
        result = await publish_single_account("vali_test_20250106_120000", 
            wallet=self.mock_wallet,
            account_data={"test": "data"},
            endpoint="http://test.com",
            miner_uid=123,
            account_id="account_1",
            platform="youtube"
        )
        
        assert result is True
        
        # Verify unified format is used with correct parameters
        mock_publisher_class.assert_called_once_with(self.mock_wallet)
        mock_publisher.publish_unified_payload.assert_called_once_with(
            payload_type="youtube",
            run_id="vali_test_20250106_120000",
            payload_data={
                "account_data": {"test": "data"},
                "account_id": "account_1"
            },
            endpoint="http://test.com",
            miner_uid=123
        )
    
    @patch('bitcast.validator.utils.data_publisher.UnifiedDataPublisher')
    @pytest.mark.asyncio
    async def test_publish_single_account_failure(self, mock_publisher_class):
        """Test publish_single_account failure handling."""
        # Mock unified publisher to return failure
        mock_publisher = AsyncMock()
        mock_publisher.publish_unified_payload = AsyncMock(return_value=False)
        mock_publisher_class.return_value = mock_publisher
        
        result = await publish_single_account("vali_test_20250106_120000", 
            wallet=self.mock_wallet,
            account_data={"test": "data"},
            endpoint="http://test.com",
            miner_uid=123,
            account_id="account_1"
        )
        
        assert result is False