"""Integration tests for forward.py with new reward system."""

import pytest
import numpy as np
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from bitcast.validator.forward import forward, get_reward_orchestrator
from bitcast.validator.reward_engine.orchestrator import RewardOrchestrator


class TestForwardIntegration:
    
    def setup_method(self):
        """Set up test fixtures."""
        self.test_uids = [123, 456, 789]
        
        # Create mock validator with proper wallet structure
        self.mock_validator = Mock()
        self.mock_validator.step = 0  # Trigger processing
        self.mock_validator.wallet = Mock()
        self.mock_validator.wallet.hotkey = Mock()  # Fix: Add hotkey attribute
        self.mock_validator.update_scores = Mock()
        
        # Setup config mock with disable_set_weights
        self.mock_validator.config = Mock()
        self.mock_validator.config.neuron = Mock()
        self.mock_validator.config.neuron.disable_set_weights = False
        
        # Setup metagraph with proper structure
        self.mock_validator.metagraph = Mock()
        mock_n = Mock()
        mock_n.item.return_value = 1000
        self.mock_validator.metagraph.n = mock_n
        self.mock_validator.metagraph.S = [100.0, 200.0, 150.0]
        self.mock_validator.metagraph.alpha_stake = [50.0, 100.0, 75.0]
    
    @pytest.mark.asyncio
    @patch('bitcast.validator.forward.get_all_uids')
    @patch('bitcast.validator.forward.get_briefs')
    @patch('time.sleep')
    async def test_forward_function_error_handling(self, mock_sleep, mock_get_briefs, mock_get_uids):
        """Test forward function error handling."""
        # Setup mocks
        mock_get_uids.return_value = self.test_uids
        mock_get_briefs.return_value = [{"id": "brief1", "title": "Test Brief"}]
        
        # Get orchestrator and make it raise an exception
        orchestrator = get_reward_orchestrator()
        
        with patch.object(orchestrator, 'calculate_rewards', new_callable=AsyncMock) as mock_calculate:
            mock_calculate.side_effect = Exception("Test error")
            
            # Should NOT raise the exception - forward function catches and logs it
            await forward(self.mock_validator)
        
        # Verify the orchestrator was called
        mock_calculate.assert_called_once()
        
        # Sleep should still be called after error handling
        mock_sleep.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('bitcast.validator.forward.get_reward_orchestrator')
    async def test_forward_function_orchestrator_exception(self, mock_get_orchestrator):
        """Test forward function with orchestrator exception."""
        # Make orchestrator raise an exception
        mock_orchestrator = Mock()
        mock_get_orchestrator.return_value = mock_orchestrator
        mock_orchestrator.calculate_rewards = AsyncMock(side_effect=Exception("Test error"))
        
        # Should NOT raise the exception - forward function catches and logs it
        await forward(self.mock_validator)
    


class TestForwardIntegrationPerformance:
    
    @pytest.mark.asyncio
    @patch('bitcast.validator.forward.get_all_uids')
    @patch('bitcast.validator.forward.get_briefs')
    @patch('time.sleep')
    async def test_forward_performance_with_many_miners(self, mock_sleep, mock_get_briefs, mock_get_uids):
        """Test forward function performance with many miners."""
        # Setup with many UIDs
        many_uids = list(range(100, 200))  # 100 miners
        mock_get_uids.return_value = many_uids
        mock_get_briefs.return_value = [{"id": "brief1", "title": "Test Brief"}]
        
        # Mock validator with proper wallet structure
        mock_validator = Mock()
        mock_validator.step = 0
        mock_validator.wallet = Mock()
        mock_validator.wallet.hotkey = Mock()  # Fix: Add hotkey attribute
        mock_validator.update_scores = Mock()
        
        # Mock metagraph for many miners
        mock_validator.metagraph = Mock()
        mock_n = Mock()
        mock_n.item.return_value = 1000
        mock_validator.metagraph.n = mock_n
        mock_validator.metagraph.S = [100.0] * len(many_uids)
        mock_validator.metagraph.alpha_stake = [50.0] * len(many_uids)
        
        orchestrator = get_reward_orchestrator()
        
        # Create simplified stats for performance
        mock_rewards = np.array([0.01] * len(many_uids))
        mock_stats_list = [
            {"uid": uid, "scores": {"brief1": 0.01}, "yt_account": {}}
            for uid in many_uids
        ]
        
        with patch.object(orchestrator, 'calculate_rewards', new_callable=AsyncMock) as mock_calculate:
            mock_calculate.return_value = (mock_rewards, mock_stats_list)
            
            # Measure execution time
            import time
            start_time = time.time()
            await forward(mock_validator)
            end_time = time.time()
            
            # Should complete reasonably quickly (< 1 second for mocked execution)
            execution_time = end_time - start_time
            assert execution_time < 1.0, f"Forward function took too long: {execution_time}s"
        
        # Verify it handled all miners
        mock_calculate.assert_called_once_with(mock_validator, many_uids)
        mock_validator.update_scores.assert_called_once()
        
        # Verify all UIDs were processed
        update_call_args = mock_validator.update_scores.call_args[0]
        processed_uids = update_call_args[1]
        assert len(processed_uids) == len(many_uids) 