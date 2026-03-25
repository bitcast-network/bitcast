"""Simplified integration test for forward.py with new reward system."""

import pytest
import numpy as np
from unittest.mock import Mock, AsyncMock, patch

from bitcast.validator.forward import forward, get_reward_orchestrator


class TestForwardIntegrationSimple:
    """Simplified integration test for forward function."""
    
    @pytest.mark.asyncio
    async def test_orchestrator_initialization_with_youtube(self):
        """Test that orchestrator initializes correctly with YouTube evaluator."""
        
        orchestrator = get_reward_orchestrator()
        
        # Verify YouTube evaluator is registered
        assert len(orchestrator.platforms) == 1
        assert "youtube" in orchestrator.platforms.get_available_platforms()
        
        # Verify orchestrator structure
        assert orchestrator.miner_query is not None
        assert orchestrator.platforms is not None
        assert orchestrator.score_aggregator is not None
        assert orchestrator.emission_calculator is not None
        assert orchestrator.reward_distributor is not None
    
    @pytest.mark.asyncio 
    @patch('bitcast.validator.forward.get_all_uids')  # Fix: Mock get_all_uids
    @patch('bitcast.validator.forward.get_reward_orchestrator')
    async def test_forward_core_workflow(self, mock_get_orchestrator, mock_get_uids):
        """Test forward function core workflow."""
        # Setup mocks
        
        # Mock validator with proper wallet structure
        mock_validator = Mock()
        mock_validator.step = 0  # Trigger processing
        mock_validator.wallet = Mock()
        mock_validator.wallet.hotkey = Mock()  # Fix: Add hotkey attribute
        mock_validator.update_scores = Mock()
        
        # Mock metagraph
        mock_validator.metagraph = Mock()
        mock_n = Mock()
        mock_n.item.return_value = 1000
        mock_validator.metagraph.n = mock_n
        mock_validator.metagraph.S = [100.0, 200.0]
        mock_validator.metagraph.alpha_stake = [50.0, 100.0]
        
        # Mock orchestrator
        orchestrator = Mock()
        mock_get_orchestrator.return_value = orchestrator
        
        test_uids = [123, 456]
        mock_get_uids.return_value = test_uids  # Fix: Mock the UID return
        mock_rewards = [0.5, 0.5]
        
        # Create simple stats without Mock objects to avoid JSON serialization issues
        mock_stats = [
            {"uid": 123, "scores": {"brief1": 0.5}, "yt_account": {}},
            {"uid": 456, "scores": {"brief1": 0.3}, "yt_account": {}}
        ]
        orchestrator.calculate_rewards = AsyncMock(return_value=(mock_rewards, mock_stats))
        
        # Execute forward function
        await forward(mock_validator)
        
        # Verify core functionality
        orchestrator.calculate_rewards.assert_called_once_with(mock_validator, test_uids)
        mock_validator.update_scores.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('bitcast.validator.forward.get_all_uids')  # Fix: Mock get_all_uids
    @patch('bitcast.validator.forward.get_reward_orchestrator')
    async def test_forward_error_resilience(self, mock_get_orchestrator):
        """Test forward function error handling."""
        
        # Mock validator with proper wallet structure
        mock_validator = Mock()
        mock_validator.step = 0
        mock_validator.wallet = Mock() 
        mock_validator.wallet.hotkey = Mock()  # Fix: Add hotkey attribute
        mock_validator.update_scores = Mock()
        
        # Mock metagraph
        mock_validator.metagraph = Mock()
        mock_n = Mock()
        mock_n.item.return_value = 1000
        mock_validator.metagraph.n = mock_n
        mock_validator.metagraph.S = [100.0, 200.0]
        mock_validator.metagraph.alpha_stake = [50.0, 100.0]
        
        # Mock orchestrator that raises an exception
        orchestrator = Mock()
        mock_get_orchestrator.return_value = orchestrator
        orchestrator.calculate_rewards = AsyncMock(side_effect=Exception("Test error"))
        
        # Execute forward function - should handle error gracefully and NOT raise
        await forward(mock_validator)


@pytest.mark.asyncio
async def test_forward_integration_imports():
    """Test that forward integration imports work correctly."""
    from bitcast.validator.forward import forward, get_reward_orchestrator
    
    # Test that we can get an orchestrator
    orchestrator = get_reward_orchestrator()
    assert orchestrator is not None
    
    # Test that forward function is callable
    assert callable(forward)


def test_forward_module_structure():
    """Test forward module functions can be imported and are callable."""
    # Test that we can import the functions directly
    from bitcast.validator.forward import forward, get_reward_orchestrator
    
    # Test that functions are callable
    assert callable(forward)
    assert callable(get_reward_orchestrator) 