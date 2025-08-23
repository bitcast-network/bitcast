"""Unit tests for weight corrections publishing."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import asyncio

from bitcast.validator.utils.weight_corrections_publisher import publish_weight_corrections





class TestWeightCorrectionsPublishing:
    """Test weight corrections publishing functionality."""
    
    @patch('bitcast.validator.utils.weight_corrections_publisher.UnifiedDataPublisher')
    @pytest.mark.asyncio
    async def test_publish_weight_corrections_success(self, mock_publisher_class):
        """Test successful publishing via convenience function."""
        # Mock publisher instance
        mock_publisher = AsyncMock()
        mock_publisher.publish_unified_payload = AsyncMock(return_value=True)
        mock_publisher_class.return_value = mock_publisher
        
        corrections = [{"content_id": "test", "brief_id": "brief_1", "scaling_factor": 0.7}]
        run_id = "vali_test_456"
        mock_wallet = Mock()
        endpoint = "http://test:8001/weight-corrections"
        
        # Should return True for success
        result = await publish_weight_corrections(corrections, run_id, mock_wallet, endpoint)
        
        # Verify publisher was created with wallet
        mock_publisher_class.assert_called_once_with(mock_wallet)
        
        # Verify publish_unified_payload was called with correct arguments
        mock_publisher.publish_unified_payload.assert_called_once_with(
            payload_type="weight_corrections",
            run_id=run_id,
            payload_data=corrections,
            endpoint=endpoint
        )
        
        # Verify return value
        assert result is True
    
    @patch('bitcast.validator.utils.weight_corrections_publisher.UnifiedDataPublisher')
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
        
        # Should return False and not raise exceptions (fire-and-forget)
        result = await publish_weight_corrections(corrections, run_id, mock_wallet, endpoint)
        
        # Verify critical error was logged
        mock_logging.error.assert_called_once()
        call_args = mock_logging.error.call_args[0][0]
        assert "Critical weight corrections publishing error" in call_args
        
        # Verify return value
        assert result is False
    
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