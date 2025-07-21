"""Basic integration tests for RewardOrchestrator core functionality."""

import pytest
import numpy as np
from unittest.mock import AsyncMock, Mock, patch

from bitcast.validator.reward_engine.orchestrator import RewardOrchestrator
from bitcast.validator.reward_engine.models.miner_response import MinerResponse


class TestRewardOrchestratorBasic:
    """Basic integration tests for RewardOrchestrator."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.orchestrator = RewardOrchestrator()
        
        # Mock validator object  
        self.mock_validator = Mock()
        self.mock_validator.metagraph = Mock()
        self.mock_validator.metagraph.S = [100.0, 200.0, 150.0]
        self.mock_validator.metagraph.alpha = Mock()
        self.mock_validator.metagraph.alpha.S = [50.0, 100.0, 75.0]
        self.mock_validator.metagraph.I = [0.1, 0.2, 0.15]
        self.mock_validator.metagraph.E = [0.05, 0.1, 0.075]
        
        self.uids = [123, 456, 789]
        self.briefs = [
            {"id": "brief1", "title": "Test Brief 1", "format": "dedicated", "weight": 100},
            {"id": "brief2", "title": "Test Brief 2", "format": "ad-read", "weight": 100}
        ]
    
    @pytest.mark.asyncio
    @patch('bitcast.validator.utils.briefs.get_briefs')
    async def test_orchestrator_no_briefs(self, mock_get_briefs):
        """Test orchestrator when no briefs are available."""
        mock_get_briefs.return_value = []
        
        rewards, stats_list = await self.orchestrator.calculate_rewards(
            self.mock_validator, self.uids
        )
        
        # Should return fallback values since no UID 0
        expected_rewards = np.array([0.0, 0.0, 0.0])
        np.testing.assert_array_equal(rewards, expected_rewards)
        
        assert len(stats_list) == 3
        for i, stats in enumerate(stats_list):
            assert stats["uid"] == self.uids[i]
            assert stats["scores"] == {}
    
    @pytest.mark.asyncio
    @patch('bitcast.validator.utils.briefs.get_briefs')
    async def test_orchestrator_with_burn_uid(self, mock_get_briefs):
        """Test orchestrator with burn UID (UID 0)."""
        mock_get_briefs.return_value = self.briefs
        uids_with_burn = [0, 123, 456]
        
        # Mock miner query to return empty responses
        mock_miner_responses = {}
        for uid in uids_with_burn:
            mock_miner_responses[uid] = MinerResponse.create_error(uid, "No response")
        
        self.orchestrator.miner_query.query_miners = AsyncMock(return_value=mock_miner_responses)
        
        rewards, stats_list = await self.orchestrator.calculate_rewards(
            self.mock_validator, uids_with_burn
        )
        
        # UID 0 should get most of the reward due to normalization
        assert rewards[0] > 0.5  # Burn UID gets significant portion
        assert len(stats_list) == 3
        
        # Verify stats structure
        for stats in stats_list:
            assert "uid" in stats
            assert "scores" in stats
    
    def test_metagraph_info_extraction(self):
        """Test metagraph information extraction."""
        info = self.orchestrator._extract_metagraph_info(self.mock_validator.metagraph, 1)
        
        expected = {
            'stake': 200.0,
            'alpha_stake': 100.0, 
            'incentive': 0.2,
            'emission': 0.1
        }
        assert info == expected
    
    def test_metagraph_info_none(self):
        """Test metagraph info with None input."""
        info = self.orchestrator._extract_metagraph_info(None, 0)
        assert info == {}
    
    def test_metagraph_info_missing_attributes(self):
        """Test metagraph info with missing attributes."""
        # Create a simple object instead of Mock to avoid hasattr() returning True for everything
        class MockMetagraph:
            def __init__(self):
                self.S = [100.0]  # Only S attribute exists
                # alpha, I, E attributes are missing
        
        mock_metagraph = MockMetagraph()
        
        info = self.orchestrator._extract_metagraph_info(mock_metagraph, 0)
        assert info == {'stake': 100.0}
    
    @pytest.mark.asyncio
    @patch('bitcast.validator.utils.briefs.get_briefs')
    async def test_orchestrator_error_handling(self, mock_get_briefs):
        """Test error handling in orchestrator."""
        mock_get_briefs.return_value = self.briefs
        
        # Force an error in miner query
        self.orchestrator.miner_query.query_miners = AsyncMock(
            side_effect=Exception("Network error")
        )
        
        rewards, stats_list = await self.orchestrator.calculate_rewards(
            self.mock_validator, self.uids
        )
        
        # Should return error fallback values
        expected_rewards = np.array([0.0, 0.0, 0.0])  # No burn UID
        np.testing.assert_array_equal(rewards, expected_rewards)
        
        assert len(stats_list) == 3
        for i, stats in enumerate(stats_list):
            assert stats["uid"] == self.uids[i]
            assert stats["scores"] == {}
    
    @pytest.mark.asyncio
    @patch('bitcast.validator.utils.briefs.get_briefs')
    @patch('bitcast.validator.utils.token_pricing.get_bitcast_alpha_price')
    @patch('bitcast.validator.utils.token_pricing.get_total_miner_emissions')
    async def test_orchestrator_complete_workflow_no_evaluators(
        self, mock_emissions, mock_price, mock_get_briefs
    ):
        """Test complete workflow with no platform evaluators registered."""
        mock_get_briefs.return_value = self.briefs
        mock_price.return_value = 1.0
        mock_emissions.return_value = 1000.0
        
        # Mock miner responses but no evaluators registered
        mock_miner_responses = {}
        for uid in self.uids:
            mock_response = Mock()
            mock_response.YT_access_tokens = ["mock_token"]
            mock_miner_responses[uid] = MinerResponse.from_response(uid, mock_response)
        
        self.orchestrator.miner_query.query_miners = AsyncMock(return_value=mock_miner_responses)
        
        rewards, stats_list = await self.orchestrator.calculate_rewards(
            self.mock_validator, self.uids
        )
        
        # Should complete but with zero scores since no evaluators
        assert isinstance(rewards, np.ndarray)
        assert len(rewards) == 3
        assert len(stats_list) == 3
        
        # All rewards should be 0 or minimal since no evaluators found
        assert all(reward >= 0 for reward in rewards)
        
        # Check stats structure
        for stats in stats_list:
            assert "uid" in stats
            assert "scores" in stats
            assert stats["uid"] in self.uids


class TestRewardOrchestratorServices:
    """Test orchestrator interaction with individual services."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.orchestrator = RewardOrchestrator()
    
    @pytest.mark.asyncio
    @patch('bitcast.validator.utils.briefs.get_briefs')
    async def test_service_initialization(self, mock_get_briefs):
        """Test that all services are properly initialized."""
        mock_get_briefs.return_value = []
        
        # Check that all services exist
        assert self.orchestrator.miner_query is not None
        assert self.orchestrator.platforms is not None  
        assert self.orchestrator.score_aggregator is not None
        assert self.orchestrator.emission_calculator is not None
        assert self.orchestrator.reward_distributor is not None
        
        # Check they have expected types
        from bitcast.validator.reward_engine.services.miner_query_service import MinerQueryService
        from bitcast.validator.reward_engine.services.platform_registry import PlatformRegistry
        from bitcast.validator.reward_engine.services.score_aggregation_service import ScoreAggregationService
        from bitcast.validator.reward_engine.services.emission_calculation_service import EmissionCalculationService
        from bitcast.validator.reward_engine.services.reward_distribution_service import RewardDistributionService
        
        assert isinstance(self.orchestrator.miner_query, MinerQueryService)
        assert isinstance(self.orchestrator.platforms, PlatformRegistry)
        assert isinstance(self.orchestrator.score_aggregator, ScoreAggregationService)
        assert isinstance(self.orchestrator.emission_calculator, EmissionCalculationService)
        assert isinstance(self.orchestrator.reward_distributor, RewardDistributionService)
    
    def test_custom_service_injection(self):
        """Test that custom services can be injected."""
        custom_miner_query = Mock()
        custom_platform_registry = Mock()
        
        orchestrator = RewardOrchestrator(
            miner_query_service=custom_miner_query,
            platform_registry=custom_platform_registry
        )
        
        assert orchestrator.miner_query == custom_miner_query
        assert orchestrator.platforms == custom_platform_registry
        
        # Others should be defaults
        assert orchestrator.score_aggregator is not None
        assert orchestrator.emission_calculator is not None
        assert orchestrator.reward_distributor is not None 