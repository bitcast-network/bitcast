"""Unit tests for WeightCorrectionsPublisher."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import asyncio

from bitcast.validator.utils.weight_corrections_publisher import (
    WeightCorrectionsPublisher, 
    publish_weight_corrections
)


class TestWeightCorrectionsPublisher:
    """Test WeightCorrectionsPublisher class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_wallet = Mock()
        self.publisher = WeightCorrectionsPublisher(self.mock_wallet)
        
    def test_build_corrections_payload(self):
        """Test payload format construction."""
        corrections = [
            {"content_id": "bitcast_abc123", "brief_id": "brief_1", "scaling_factor": 0.6},
            {"content_id": "bitcast_def456", "brief_id": "brief_2", "scaling_factor": 1.0},
            {"content_id": "bitcast_ghi789", "brief_id": "brief_1", "scaling_factor": 0.0}
        ]
        run_id = "vali_test_20250120_120000"
        
        payload = self.publisher._build_corrections_payload(corrections, run_id)
        
        # Verify payload structure
        assert payload["payload_type"] == "weight_corrections"
        assert payload["run_id"] == run_id
        assert len(payload["corrections"]) == 3
        
        # Verify corrections data
        assert payload["corrections"][0]["content_id"] == "bitcast_abc123"
        assert payload["corrections"][0]["brief_id"] == "brief_1"
        assert payload["corrections"][0]["scaling_factor"] == 0.6
    
    @patch('bitcast.validator.utils.weight_corrections_publisher.bt.logging')
    @pytest.mark.asyncio
    async def test_publish_corrections_success(self, mock_logging):
        """Test successful corrections publishing."""
        # Mock the publish_data method
        self.publisher.publish_data = AsyncMock(return_value=True)
        
        corrections = [
            {"content_id": "bitcast_abc123", "brief_id": "brief_1", "scaling_factor": 0.8}
        ]
        run_id = "vali_test_123"
        endpoint = "http://test:8001/weight-corrections"
        
        # Should not raise any exceptions
        await self.publisher.publish_corrections(corrections, run_id, endpoint)
        
        # Verify publish_data was called with correct arguments
        self.publisher.publish_data.assert_called_once()
        call_args = self.publisher.publish_data.call_args
        
        # Check the payload structure
        payload = call_args[0][0]  # First positional argument
        endpoint_arg = call_args[0][1]  # Second positional argument
        
        assert endpoint_arg == endpoint
        assert payload["payload_type"] == "weight_corrections"
        assert payload["run_id"] == run_id
        
        # Verify logging
        mock_logging.info.assert_called()
    
    @patch('bitcast.validator.utils.weight_corrections_publisher.bt.logging')
    @pytest.mark.asyncio
    async def test_publish_corrections_failure_logged(self, mock_logging):
        """Test that publishing failures are logged but not raised."""
        # Mock publish_data to raise an exception
        self.publisher.publish_data = AsyncMock(side_effect=Exception("Network error"))
        
        corrections = [{"content_id": "test", "brief_id": "brief_1", "scaling_factor": 1.0}]
        run_id = "vali_test_123"
        endpoint = "http://test:8001/weight-corrections"
        
        # Should not raise any exceptions (fire-and-forget)
        await self.publisher.publish_corrections(corrections, run_id, endpoint)
        
        # Verify error was logged as warning
        mock_logging.warning.assert_called_once()
        call_args = mock_logging.warning.call_args[0][0]
        assert "Weight corrections publishing failed" in call_args
    
    @pytest.mark.asyncio
    async def test_empty_corrections_list(self):
        """Test handling of empty corrections list."""
        self.publisher.publish_data = AsyncMock(return_value=True)
        
        corrections = []
        run_id = "vali_test_123"
        endpoint = "http://test:8001/weight-corrections"
        
        # Should handle empty list gracefully
        await self.publisher.publish_corrections(corrections, run_id, endpoint)
        
        # Should still call publish_data with empty corrections
        self.publisher.publish_data.assert_called_once()
        call_args = self.publisher.publish_data.call_args
        payload = call_args[0][0]  # First positional argument
        assert len(payload["corrections"]) == 0
    
    def test_authentication_fields_included(self):
        """Test that authentication fields (vali_hotkey, signature, signer) are included in signed payload."""
        corrections = [
            {"content_id": "bitcast_test123", "brief_id": "brief_1", "scaling_factor": 0.75}
        ]
        run_id = "vali_test_auth"
        
        # Build the base payload
        payload = self.publisher._build_corrections_payload(corrections, run_id)
        
        # Sign the payload (this should add authentication fields)
        signed_payload = self.publisher._sign_message(payload)
        
        # Verify all required authentication fields are present
        assert "vali_hotkey" in signed_payload
        assert "signature" in signed_payload  
        assert "signer" in signed_payload
        
        # Verify the fields have reasonable values (Mock objects in test environment)
        assert signed_payload["vali_hotkey"] == self.mock_wallet.hotkey.ss58_address
        assert signed_payload["signer"] == self.mock_wallet.hotkey.ss58_address
        # In test environment, signature will be a Mock object that simulates the signing process
        assert signed_payload["signature"] is not None
        
        # Verify payload content is preserved
        assert signed_payload["payload_type"] == "weight_corrections"
        assert signed_payload["run_id"] == run_id
        assert len(signed_payload["corrections"]) == 1


class TestPublishWeightCorrectionsFunction:
    """Test the standalone publish_weight_corrections function."""
    
    @patch('bitcast.validator.utils.weight_corrections_publisher.WeightCorrectionsPublisher')
    @pytest.mark.asyncio
    async def test_publish_weight_corrections_success(self, mock_publisher_class):
        """Test successful publishing via convenience function."""
        # Mock publisher instance
        mock_publisher = AsyncMock()
        mock_publisher_class.return_value = mock_publisher
        
        corrections = [{"content_id": "test", "brief_id": "brief_1", "scaling_factor": 0.7}]
        run_id = "vali_test_456"
        mock_wallet = Mock()
        endpoint = "http://test:8001/weight-corrections"
        
        # Should not raise any exceptions
        await publish_weight_corrections(corrections, run_id, mock_wallet, endpoint)
        
        # Verify publisher was created with wallet
        mock_publisher_class.assert_called_once_with(mock_wallet)
        
        # Verify publish_corrections was called
        mock_publisher.publish_corrections.assert_called_once_with(corrections, run_id, endpoint)
    
    @patch('bitcast.validator.utils.weight_corrections_publisher.WeightCorrectionsPublisher')
    @patch('bitcast.validator.utils.weight_corrections_publisher.bt.logging')
    @pytest.mark.asyncio
    async def test_publish_weight_corrections_critical_failure(self, mock_logging, mock_publisher_class):
        """Test critical failure handling in convenience function."""
        # Mock publisher creation to raise exception
        mock_publisher_class.side_effect = Exception("Critical error")
        
        corrections = [{"content_id": "test", "brief_id": "brief_1", "scaling_factor": 0.7}]
        run_id = "vali_test_456" 
        mock_wallet = Mock()
        endpoint = "http://test:8001/weight-corrections"
        
        # Should not raise any exceptions (fire-and-forget)
        await publish_weight_corrections(corrections, run_id, mock_wallet, endpoint)
        
        # Verify critical error was logged
        mock_logging.error.assert_called_once()
        call_args = mock_logging.error.call_args[0][0]
        assert "Critical weight corrections publishing error" in call_args
    
    @pytest.mark.asyncio
    async def test_fire_and_forget_behavior(self):
        """Test that the function truly never raises exceptions."""
        # This test ensures fire-and-forget behavior even with malformed inputs
        
        # Should handle None inputs gracefully
        await publish_weight_corrections(None, None, None, None)
        
        # Should handle malformed corrections gracefully
        malformed_corrections = [{"invalid": "data"}]
        await publish_weight_corrections(malformed_corrections, "test", Mock(), "test")
        
        # If we reach here, no exceptions were raised (fire-and-forget working)
        assert True