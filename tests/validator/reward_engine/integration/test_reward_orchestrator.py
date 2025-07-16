"""Integration tests for RewardOrchestrator and complete reward workflow."""

import pytest
import numpy as np
from unittest.mock import AsyncMock, Mock, patch

from bitcast.validator.reward_engine.orchestrator import RewardOrchestrator
from bitcast.validator.reward_engine.services.platform_registry import PlatformRegistry
from bitcast.validator.platforms.youtube.youtube_evaluator import YouTubeEvaluator
from bitcast.validator.reward_engine.models.miner_response import MinerResponse
from bitcast.validator.reward_engine.models.evaluation_result import EvaluationResult, AccountResult


class TestRewardOrchestrator:
    """Integration tests for RewardOrchestrator."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.orchestrator = RewardOrchestrator()
        
        # Mock validator object
        self.mock_validator = Mock()
        self.mock_validator.metagraph = Mock()
        self.mock_validator.metagraph.S = [100.0, 200.0, 200.0, 150.0]  # Stakes: UID 0=100, UID 1=200, UID 2=200, UID 3=150
        self.mock_validator.metagraph.alpha = Mock()
        self.mock_validator.metagraph.alpha.S = [50.0, 100.0, 100.0, 75.0]  # Alpha stakes: UID 1=100
        self.mock_validator.metagraph.I = [0.1, 0.2, 0.2, 0.15]  # Incentives: UID 1=0.2
        self.mock_validator.metagraph.E = [0.05, 0.1, 0.1, 0.075]  # Emissions: UID 1=0.1
        
        # Test data - include UID 0 for community reserve
        self.uids = [0, 123, 456, 789]  # Include UID 0 for community reserve
        self.briefs = [
            {"id": "brief1", "title": "Test Brief 1", "format": "dedicated", "weight": 100},
            {"id": "brief2", "title": "Test Brief 2", "format": "pre-roll", "weight": 100}
        ]
    
    @pytest.mark.asyncio
    @patch('bitcast.validator.utils.briefs.get_briefs')
    @patch('bitcast.validator.utils.token_pricing.get_bitcast_alpha_price')
    @patch('bitcast.validator.utils.token_pricing.get_total_miner_emissions')
    async def test_calculate_rewards_with_youtube_evaluator(
        self, mock_emissions, mock_price, mock_get_briefs
    ):
        """Test complete reward calculation workflow with YouTube evaluator."""
        # Setup mocks
        mock_get_briefs.return_value = self.briefs
        mock_price.return_value = 1.0  # $1 per token
        mock_emissions.return_value = 1000.0  # 1000 tokens per day
        
        # Register YouTube evaluator
        youtube_evaluator = Mock(spec=YouTubeEvaluator)
        youtube_evaluator.platform_name.return_value = "youtube"
        youtube_evaluator.can_evaluate.return_value = True
        
        # Mock evaluation result
        mock_eval_result = EvaluationResult(
            uid=123,
            platform="youtube",
            aggregated_scores={"brief1": 0.5, "brief2": 0.3}
        )
        
        # Add mock account result
        mock_account_result = AccountResult(
            account_id="account1",
            platform_data={"channel_id": "test123"},
            videos={"video1": {"title": "Test Video"}},
            scores={"brief1": 0.5, "brief2": 0.3},
            performance_stats={"total_views": 1000},
            success=True
        )
        mock_eval_result.add_account_result("account1", mock_account_result)
        
        youtube_evaluator.evaluate_accounts.return_value = mock_eval_result
        
        self.orchestrator.platforms.register_evaluator(youtube_evaluator)
        
        # Mock miner query service to return valid responses
        mock_miner_responses = {}
        for uid in self.uids:
            mock_response = Mock()
            if uid == 0:
                # UID 0 (community reserve) gets no tokens
                mock_response.YT_access_tokens = []
            else:
                mock_response.YT_access_tokens = ["mock_token"]
            miner_response = MinerResponse.from_response(uid, mock_response)
            mock_miner_responses[uid] = miner_response
        
        self.orchestrator.miner_query.query_miners = AsyncMock(return_value=mock_miner_responses)
        
        # Execute reward calculation
        rewards, stats_list = await self.orchestrator.calculate_rewards(
            self.mock_validator, self.uids
        )
        
        # Verify results
        assert isinstance(rewards, np.ndarray)
        assert len(rewards) == len(self.uids)
        assert len(stats_list) == len(self.uids)
    
    def test_get_metagraph_info(self):
        """Test metagraph info extraction."""
        info = self.orchestrator._extract_metagraph_info(self.mock_validator.metagraph, 1)
        
        expected_info = {
            'stake': 200.0,
            'alpha_stake': 100.0,
            'incentive': 0.2,
            'emission': 0.1
        }
        
        assert info == expected_info
    
    def test_get_metagraph_info_missing_data(self):
        """Test metagraph info extraction with missing data."""
        # Create a simple object instead of Mock to avoid hasattr() returning True for everything
        class MockMetagraph:
            def __init__(self):
                self.S = [100.0]  # Only S attribute exists
                # alpha, I, E attributes are missing
        
        mock_metagraph = MockMetagraph()
        
        info = self.orchestrator._extract_metagraph_info(mock_metagraph, 0)
        
        assert info == {'stake': 100.0}
    
    def test_get_metagraph_info_none(self):
        """Test metagraph info extraction with None metagraph."""
        info = self.orchestrator._extract_metagraph_info(None, 0)
        assert info == {}
    
    @pytest.mark.asyncio
    @patch('bitcast.validator.utils.briefs.get_briefs')
    async def test_error_handling(self, mock_get_briefs):
        """Test error handling in reward calculation."""
        mock_get_briefs.return_value = self.briefs
        
        # Force an error in miner query
        self.orchestrator.miner_query.query_miners = AsyncMock(
            side_effect=Exception("Test error")
        )
        
        rewards, stats_list = await self.orchestrator.calculate_rewards(
            self.mock_validator, self.uids
        )
        
        # Should return fallback values
        expected_rewards = np.array([1.0, 0.0, 0.0, 0.0])  # UID 0 gets 1.0, others get 0.0 (4 UIDs total)
        np.testing.assert_array_equal(rewards, expected_rewards)
        
        assert len(stats_list) == len(self.uids)
        for i, stats in enumerate(stats_list):
            assert stats["uid"] == self.uids[i]
            assert stats["scores"] == {}
    
    @pytest.mark.asyncio
    @patch('bitcast.validator.utils.briefs.get_briefs')
    async def test_uid_zero_special_case(self, mock_get_briefs):
        """Test special handling of UID 0 (burn UID)."""
        mock_get_briefs.return_value = self.briefs
        
        uids_with_zero = [0, 123, 456]
        
        # Mock empty miner responses
        mock_miner_responses = {}
        for uid in uids_with_zero:
            miner_response = MinerResponse.create_error(uid, "No response")
            mock_miner_responses[uid] = miner_response
        
        self.orchestrator.miner_query.query_miners = AsyncMock(return_value=mock_miner_responses)
        
        rewards, stats_list = await self.orchestrator.calculate_rewards(
            self.mock_validator, uids_with_zero
        )
        
        # UID 0 should get special treatment and end up with most of the reward
        assert rewards[0] > 0.5  # UID 0 should get significant reward
        assert len(stats_list) == 3


class TestRewardOrchestoratorIntegration:
    """More comprehensive integration tests."""
    
    @pytest.mark.asyncio
    @patch('bitcast.validator.utils.briefs.get_briefs')
    @patch('bitcast.validator.utils.token_pricing.get_bitcast_alpha_price')
    @patch('bitcast.validator.utils.token_pricing.get_total_miner_emissions')
    @patch('bitcast.validator.rewards_scaling.allocate_community_reserve')
    async def test_end_to_end_workflow(
        self, mock_allocate, mock_emissions, mock_price, mock_get_briefs
    ):
        """Test the complete end-to-end reward calculation workflow."""
        # Setup comprehensive test scenario
        briefs = [
            {"id": "brief1", "title": "Gaming Content", "format": "dedicated", "weight": 100},
            {"id": "brief2", "title": "Tech Reviews", "format": "pre-roll", "weight": 100}
        ]
        uids = [0, 123, 456]  # Include burn UID
        
        mock_get_briefs.return_value = briefs
        mock_price.return_value = 2.0  # $2 per token
        mock_emissions.return_value = 500.0  # 500 tokens per day
        mock_allocate.side_effect = lambda x, y: x  # Pass through unchanged
        
        # Setup orchestrator with all services
        orchestrator = RewardOrchestrator()
        
        # Register YouTube evaluator with realistic behavior
        youtube_evaluator = Mock(spec=YouTubeEvaluator)
        youtube_evaluator.platform_name.return_value = "youtube"
        
        # Make can_evaluate check for YouTube access tokens like the real evaluator
        def can_evaluate_mock(miner_response):
            return (hasattr(miner_response, 'YT_access_tokens') and 
                   isinstance(miner_response.YT_access_tokens, list) and
                   len(miner_response.YT_access_tokens) > 0)
        youtube_evaluator.can_evaluate.side_effect = can_evaluate_mock
        
        # Create different evaluation results for different miners
        def create_eval_result(uid, scores):
            result = EvaluationResult(uid=uid, platform="youtube", aggregated_scores=scores)
            account_result = AccountResult(
                account_id="account1",
                platform_data={"channel_id": f"channel_{uid}"},
                videos={f"video_{uid}": {"title": f"Video from {uid}"}},
                scores=scores,
                performance_stats={"total_views": 1000 * uid},
                success=True
            )
            result.add_account_result("account1", account_result)
            return result
        
        # Different performance for different miners
        eval_results = {
            123: create_eval_result(123, {"brief1": 0.8, "brief2": 0.6}),  # High performer
            456: create_eval_result(456, {"brief1": 0.3, "brief2": 0.2})   # Lower performer
        }
        
        def mock_evaluate(response, briefs_param, metagraph_info):
            return eval_results.get(response.uid, create_eval_result(response.uid, {"brief1": 0.0, "brief2": 0.0}))
        
        youtube_evaluator.evaluate_accounts.side_effect = mock_evaluate
        orchestrator.platforms.register_evaluator(youtube_evaluator)
        
        # Mock miner responses
        mock_miner_responses = {}
        for uid in uids:
            if uid == 0:
                # Burn UID gets error response
                mock_miner_responses[uid] = MinerResponse.create_error(uid, "Burn UID")
            else:
                mock_response = Mock()
                mock_response.YT_access_tokens = ["mock_token"]
                mock_miner_responses[uid] = MinerResponse.from_response(uid, mock_response)
        
        orchestrator.miner_query.query_miners = AsyncMock(return_value=mock_miner_responses)
        
        # Mock validator
        mock_validator = Mock()
        mock_validator.metagraph = Mock()
        mock_validator.metagraph.S = [0.0, 100.0, 50.0]  # Proper list instead of Mock
        mock_validator.metagraph.alpha = Mock()
        mock_validator.metagraph.alpha.S = [0.0, 80.0, 40.0]  # Proper list instead of Mock
        mock_validator.metagraph.I = [0.0, 0.2, 0.1]  # Add incentives
        mock_validator.metagraph.E = [0.0, 0.1, 0.05]  # Add emissions
        
        # Execute complete workflow
        rewards, stats_list = await orchestrator.calculate_rewards(mock_validator, uids)
        
        # Comprehensive verification
        assert isinstance(rewards, np.ndarray)
        assert len(rewards) == 3
        assert len(stats_list) == 3
        
        # Verify reward distribution logic - UID 0 (burn/reserve) gets 1.0, others get 0.0
        assert rewards[0] == 1.0  # UID 0 (burn/community reserve) gets special treatment
        assert rewards[1] == 0.0  # UID 123 
        assert rewards[2] == 0.0  # UID 456
        
        # Verify that UID 0 gets higher reward than others
        assert rewards[0] > rewards[1]
        assert rewards[0] > rewards[2]
        
        # Verify stats structure
        for i, stats in enumerate(stats_list):
            assert stats["uid"] == uids[i]
            assert "scores" in stats
            # Basic stats structure is sufficient for integration test
        
        # Integration test passes - orchestrator successfully processes the request
        # and returns the expected reward and stats structure


@pytest.fixture
def mock_brief_data():
    """Fixture providing mock brief data."""
    return [
        {
            "id": "brief_gaming",
            "title": "Gaming Content Brief",
            "format": "dedicated",
            "weight": 100,
            "description": "Create gaming content"
        },
        {
            "id": "brief_tech", 
            "title": "Tech Review Brief",
            "format": "pre-roll",
            "weight": 100,
            "description": "Review latest tech products"
        }
    ]


@pytest.fixture
def mock_miner_data():
    """Fixture providing mock miner data."""
    return {
        "uids": [0, 123, 456, 789],
        "stakes": [0.0, 100.0, 200.0, 150.0],
        "alpha_stakes": [0.0, 50.0, 100.0, 75.0]
    } 