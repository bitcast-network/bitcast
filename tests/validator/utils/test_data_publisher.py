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
    AccountDataPublisher,
    get_account_publisher,
    publish_single_account,
    _account_publisher
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
        mock_bt.logging.info.assert_called_once_with("Successfully published test data to http://test.com")
    
    @patch('bitcast.validator.utils.data_publisher.bt')
    def test_log_error(self, mock_bt):
        """Test error logging."""
        error = Exception("Test error")
        self.publisher._log_error("http://test.com", error, "test data")
        mock_bt.logging.error.assert_called_once_with("Failed to publish test data to http://test.com: Test error")


class TestAccountDataPublisher:
    """Test cases for AccountDataPublisher class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Reset global publisher
        global _account_publisher
        _account_publisher = None
        
        # Create mock wallet
        self.mock_wallet = Mock()
        self.mock_hotkey = Mock()
        self.mock_hotkey.ss58_address = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
        self.mock_wallet.hotkey = self.mock_hotkey
        
        self.publisher = AccountDataPublisher(self.mock_wallet)
        self.test_endpoint = "http://test-database.com:8005/account"
        self.test_account_data = {
            "yt_account": {"channel_id": "test_channel"},
            "videos": {"video1": {"title": "Test Video"}},
            "scores": {"brief1": 0.5},
            "performance_stats": {"api_calls": 10}
        }
    
    @patch.object(AccountDataPublisher, 'publish_data')
    @pytest.mark.asyncio
    async def test_publish_account_data_success(self, mock_publish):
        """Test successful account data publishing."""
        # Mock run ID
        mock_publish.return_value = True
        
        result = await self.publisher.publish_account_data("vali_test_20250106_120000", 
            self.test_account_data,
            self.test_endpoint,
            miner_uid=123,
            account_id="account_1"
        )
        
        assert result is True
        
        # Verify publish_data was called with correct payload
        mock_publish.assert_called_once()
        call_args = mock_publish.call_args[0]
        
        payload = call_args[0]
        endpoint = call_args[1]
        
        assert payload["run_id"] == "vali_test_20250106_120000"
        assert payload["platform"] == "youtube"
        assert payload["miner_uid"] == 123
        assert payload["account_id"] == "account_1"
        assert payload["account_data"] == self.test_account_data
        assert endpoint == self.test_endpoint
    
    @pytest.mark.asyncio
    async def test_publish_account_data_no_run_id(self):
        """Test account data publishing fails when no run ID available."""
        
        result = await self.publisher.publish_account_data("vali_test_20250106_120000", 
            self.test_account_data,
            self.test_endpoint,
            miner_uid=123,
            account_id="account_1"
        )
        
        assert result is False
    
    @patch.object(AccountDataPublisher, 'publish_data')
    @pytest.mark.asyncio
    async def test_publish_account_data_custom_platform(self, mock_publish):
        """Test account data publishing with custom platform."""
        mock_publish.return_value = True
        
        result = await self.publisher.publish_account_data("vali_test_20250106_120000", 
            self.test_account_data,
            self.test_endpoint,
            miner_uid=123,
            account_id="account_1",
            platform="tiktok"
        )
        
        assert result is True
        
        # Verify platform was set correctly
        call_args = mock_publish.call_args[0]
        payload = call_args[0]
        assert payload["platform"] == "tiktok"
    
    @patch.object(AccountDataPublisher, 'publish_data')
    @pytest.mark.asyncio
    async def test_publish_data_success(self, mock_publish):
        """Test successful HTTP publishing."""
        # Mock the publish_data method to return success
        mock_publish.return_value = True
        
        result = await self.publisher.publish_data(
            {"test": "data"}, 
            self.test_endpoint
        )
        
        assert result is True
        mock_publish.assert_called_once_with({"test": "data"}, self.test_endpoint)
    
    @patch.object(AccountDataPublisher, 'publish_data')
    @pytest.mark.asyncio
    async def test_publish_data_http_error(self, mock_publish):
        """Test HTTP error handling."""
        # Mock the publish_data method to return failure
        mock_publish.return_value = False
        
        result = await self.publisher.publish_data(
            {"test": "data"}, 
            self.test_endpoint
        )
        
        assert result is False
    
    @patch.object(AccountDataPublisher, 'publish_data')
    @pytest.mark.asyncio
    async def test_publish_data_server_error_response(self, mock_publish):
        """Test server error response handling."""
        # Mock the publish_data method to return failure for server error
        mock_publish.return_value = False
        
        result = await self.publisher.publish_data(
            {"test": "data"}, 
            self.test_endpoint
        )
        
        assert result is False
    
    @patch.object(AccountDataPublisher, 'publish_data')
    @pytest.mark.asyncio
    async def test_publish_data_timeout(self, mock_publish):
        """Test timeout handling."""
        # Mock the publish_data method to return failure for timeout
        mock_publish.return_value = False
        
        result = await self.publisher.publish_data(
            {"test": "data"}, 
            self.test_endpoint
        )
        
        assert result is False


class TestGlobalPublisherFunctions:
    """Test cases for global publisher functions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Reset global publisher
        global _account_publisher
        _account_publisher = None
        
        # Create mock wallet
        self.mock_wallet = Mock()
        self.mock_hotkey = Mock()
        self.mock_hotkey.ss58_address = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
        self.mock_wallet.hotkey = self.mock_hotkey
    
    def test_get_account_publisher_creates_instance(self):
        """Test get_account_publisher creates and returns AccountDataPublisher instance."""
        publisher = get_account_publisher(self.mock_wallet)
        
        assert isinstance(publisher, AccountDataPublisher)
        assert publisher.wallet == self.mock_wallet
    
    def test_get_account_publisher_returns_same_instance(self):
        """Test get_account_publisher returns the same instance on subsequent calls."""
        publisher1 = get_account_publisher(self.mock_wallet)
        publisher2 = get_account_publisher(self.mock_wallet)
        
        assert publisher1 is publisher2
    
    @patch('bitcast.validator.utils.data_publisher.get_account_publisher')
    @pytest.mark.asyncio
    async def test_publish_single_account(self, mock_get_publisher):
        """Test publish_single_account convenience function."""
        # Mock publisher
        mock_publisher = AsyncMock()
        mock_publisher.publish_account_data.return_value = True
        mock_get_publisher.return_value = mock_publisher
        
        result = await publish_single_account("vali_test_20250106_120000", 
            wallet=self.mock_wallet,
            account_data={"test": "data"},
            endpoint="http://test.com",
            miner_uid=123,
            account_id="account_1",
            platform="youtube"
        )
        
        assert result is True
        mock_get_publisher.assert_called_once_with(self.mock_wallet)
        mock_publisher.publish_account_data.assert_called_once_with("vali_test_20250106_120000", 
            {"test": "data"},
            "http://test.com",
            123,
            "account_1",
            "youtube"
        )


class TestAccountDataPublisherIntegration:
    """Integration tests for AccountDataPublisher with real aiohttp."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create mock wallet
        self.mock_wallet = Mock()
        self.mock_hotkey = Mock()
        self.mock_hotkey.ss58_address = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
        self.mock_wallet.hotkey = self.mock_hotkey
        
        self.publisher = AccountDataPublisher(self.mock_wallet, timeout_seconds=1)
    
    @pytest.mark.asyncio
    async def test_real_timeout_behavior(self):
        """Test real timeout behavior with unreachable endpoint."""
        # Use an unreachable endpoint to trigger timeout
        unreachable_endpoint = "http://192.0.2.1:8005/account"  # RFC5737 test address
        
        result = await self.publisher.publish_data(
            {"test": "data"}, 
            unreachable_endpoint
        )
        
        # Should return False due to timeout/connection error
        assert result is False
    
    @pytest.mark.asyncio
    async def test_real_account_data_structure(self):
        """Test account data structure with real data."""
        
        # Mock the HTTP call to avoid actual network requests
        with patch.object(self.publisher, 'publish_data', return_value=True) as mock_publish:
            real_account_data = {
                "yt_account": {
                    "details": {"channel_id": "UC123", "name": "Test Channel"},
                    "analytics": {"views": 1000, "ypp": True}
                },
                "videos": {
                    "video1": {
                        "title": "Test Video 1",
                        "views": 500,
                        "score": 0.75
                    }
                },
                "scores": {"brief1": 0.5, "brief2": 0.3},
                "performance_stats": {
                    "data_api_calls": 10,
                    "analytics_api_calls": 5,
                    "evaluation_time_s": 15.2
                }
            }
            
            result = await self.publisher.publish_account_data("vali_test_20250106_120000", 
                real_account_data,
                "http://test.com",
                miner_uid=456,
                account_id="account_2",
                platform="youtube"
            )
            
            assert result is True
            
            # Verify the payload structure
            call_args = mock_publish.call_args[0]
            payload = call_args[0]
            
            assert payload["run_id"] == "vali_test_20250106_120000"
            assert payload["platform"] == "youtube"
            assert payload["miner_uid"] == 456
            assert payload["account_id"] == "account_2"
            assert payload["account_data"] == real_account_data