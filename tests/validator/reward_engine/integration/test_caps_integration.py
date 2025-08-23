"""Integration tests for caps functionality."""

import pytest
import numpy as np
from unittest.mock import Mock, patch

from bitcast.validator.reward_engine.orchestrator import RewardOrchestrator
from bitcast.validator.reward_engine.services.reward_distribution_service import RewardDistributionService
from bitcast.validator.reward_engine.services.emission_calculation_service import EmissionCalculationService
from bitcast.validator.reward_engine.services.score_aggregation_service import ScoreAggregationService
from bitcast.validator.reward_engine.models.evaluation_result import EvaluationResultCollection, EvaluationResult, AccountResult
from bitcast.validator.reward_engine.models.score_matrix import ScoreMatrix
from bitcast.validator.reward_engine.models.emission_target import EmissionTarget


class TestCapsIntegration:
    """Integration tests for caps functionality across the entire reward system."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.distribution_service = RewardDistributionService()
        self.emission_service = EmissionCalculationService()
        self.score_aggregator = ScoreAggregationService()
        
    def test_end_to_end_caps_workflow(self):
        """Test complete workflow from evaluation results to final rewards with caps."""
        # Create emission targets directly (simpler approach)
        emission_targets = [
            EmissionTarget(
                brief_id="brief_gaming", 
                usd_target=1000.0,
                allocation_details={"per_miner_weights": [1.0, 0.3, 0.2, 0.1]},
                scaling_factors={}
            ),  # Include UID 0
            EmissionTarget(
                brief_id="brief_tech", 
                usd_target=800.0,
                allocation_details={"per_miner_weights": [0.0, 0.2, 0.3, 0.1]},
                scaling_factors={}
            )  # Include UID 0
        ]
        
        # Create briefs with caps
        briefs = [
            {"id": "brief_gaming", "cap": 0.5, "format": "dedicated"},  # Will hit cap (total would be 1.6)
            {"id": "brief_tech", "cap": 0.8, "format": "ad-read"}       # Generous cap (total is 0.6)
        ]
        
        # Create evaluation results
        evaluation_results = EvaluationResultCollection()
        
        # Calculate final distribution with caps
        uids = [0, 1, 2, 3]  # Include burn UID
        final_rewards, stats_list, _, _ = self.distribution_service.calculate_distribution(
            emission_targets, evaluation_results, briefs, uids
        )
        
        # Verify results
        assert len(final_rewards) == 4
        assert len(stats_list) == 4
        assert abs(final_rewards.sum() - 1.0) < 1e-10  # Should sum to 1.0
        
        # Verify brief emission percentages are included
        assert "brief_emission_percentages" in stats_list[0]
        assert "brief_gaming" in stats_list[0]["brief_emission_percentages"]
        assert "brief_tech" in stats_list[0]["brief_emission_percentages"]
        
        # Verify caps were applied
        brief_percentages = stats_list[0]["brief_emission_percentages"]
        assert brief_percentages["brief_gaming"] <= 0.5 + 1e-10  # Should be capped
        assert brief_percentages["brief_tech"] <= 0.8 + 1e-10    # Should be under cap
        
    def test_caps_vs_original_weight_behavior(self):
        """Test that caps behave differently from original weight-based system."""
        # Create scenario where caps would behave differently than weights
        emission_targets = [
            EmissionTarget(
                brief_id="brief1", 
                usd_target=500.0,
                allocation_details={"per_miner_weights": [0.1, 0.6, 0.3]},
                scaling_factors={}
            ),  # Include UID 0
            EmissionTarget(
                brief_id="brief2", 
                usd_target=300.0,
                allocation_details={"per_miner_weights": [0.0, 0.2, 0.4]},
                scaling_factors={}
            )  # Include UID 0
        ]
        
        briefs_with_caps = [
            {"id": "brief1", "cap": 0.4},  # Cap lower than total weights (1.0)
            {"id": "brief2", "cap": 0.8}   # Cap higher than total weights (0.6)
        ]
        
        evaluation_results = EvaluationResultCollection()
        uids = [0, 1, 2]  # Include burn UID
        
        # Test with caps
        rewards_caps, stats_caps, _, _ = self.distribution_service.calculate_distribution(
            emission_targets, evaluation_results, briefs_with_caps, uids
        )
        
        # Verify that brief1 was capped
        brief1_percentage = stats_caps[0]["brief_emission_percentages"]["brief1"]
        brief2_percentage = stats_caps[0]["brief_emission_percentages"]["brief2"]
        
        assert brief1_percentage <= 0.4 + 1e-10  # Should be capped at 0.4
        assert brief2_percentage <= 0.8 + 1e-10  # Should be under cap
        
    @patch('bittensor.logging.info')
    def test_integration_logging_verification(self, mock_logging):
        """Test that logging works correctly in integration scenario."""
        emission_targets = [
            EmissionTarget(
                brief_id="test_brief", 
                usd_target=400.0,
                allocation_details={"per_miner_weights": [0.1, 0.8]},
                scaling_factors={}
            )  # Include UID 0
        ]
        
        briefs = [{"id": "test_brief", "cap": 0.5}]  # Will trigger cap scaling
        evaluation_results = EvaluationResultCollection()
        uids = [0, 1]  # Include burn UID
        
        # Execute distribution
        rewards, stats, _, _ = self.distribution_service.calculate_distribution(
            emission_targets, evaluation_results, briefs, uids
        )
        
        # Verify logging occurred
        assert mock_logging.called
        
        # Check for specific log messages
        call_args_list = [str(call) for call in mock_logging.call_args_list]
        log_text = " ".join(call_args_list)
        
        assert "test_brief" in log_text
        assert any("exceeded cap" in call or "claiming" in call for call in call_args_list)
        
    def test_multiple_briefs_complex_caps(self):
        """Test complex scenario with multiple briefs and various cap constraints."""
        # Create complex emission targets
        emission_targets = [
            EmissionTarget(
                brief_id="brief_1", 
                usd_target=600.0,
                allocation_details={"per_miner_weights": [0.0, 0.3, 0.2, 0.1]},
                scaling_factors={}
            ),  # Include UID 0
            EmissionTarget(
                brief_id="brief_2", 
                usd_target=700.0,
                allocation_details={"per_miner_weights": [0.0, 0.2, 0.3, 0.2]},
                scaling_factors={}
            ),  # Include UID 0
            EmissionTarget(
                brief_id="brief_3", 
                usd_target=600.0,
                allocation_details={"per_miner_weights": [0.0, 0.1, 0.1, 0.4]},
                scaling_factors={}
            ),  # Include UID 0
            EmissionTarget(
                brief_id="brief_4", 
                usd_target=100.0,
                allocation_details={"per_miner_weights": [0.0, 0.0, 0.1, 0.0]},
                scaling_factors={}
            )  # Include UID 0
        ]
        
        briefs = [
            {"id": "brief_1", "cap": 0.5},   # Total: 0.6, will be capped
            {"id": "brief_2", "cap": 0.8},   # Total: 0.7, under cap
            {"id": "brief_3", "cap": 0.4},   # Total: 0.6, will be capped
            {"id": "brief_4", "cap": 0.2}    # Total: 0.1, under cap
        ]
        
        evaluation_results = EvaluationResultCollection()
        uids = [0, 1, 2, 3]  # Include burn UID
        
        # Execute distribution
        rewards, stats, _, _ = self.distribution_service.calculate_distribution(
            emission_targets, evaluation_results, briefs, uids
        )
        
        # Verify all constraints are met
        brief_percentages = stats[0]["brief_emission_percentages"]
        
        assert brief_percentages["brief_1"] <= 0.5 + 1e-10
        assert brief_percentages["brief_2"] <= 0.8 + 1e-10
        assert brief_percentages["brief_3"] <= 0.4 + 1e-10
        assert brief_percentages["brief_4"] <= 0.2 + 1e-10
        
        # Total should equal 1.0
        total_percentage = sum(brief_percentages.values())
        assert abs(total_percentage - 1.0) < 1e-10
        
    def test_edge_case_all_zero_caps(self):
        """Test edge case where all briefs have zero caps."""
        emission_targets = [
            EmissionTarget(
                brief_id="brief1", 
                usd_target=500.0,
                allocation_details={"per_miner_weights": [0.9, 0.5]},
                scaling_factors={}
            ),  # Include UID 0
            EmissionTarget(
                brief_id="brief2", 
                usd_target=300.0,
                allocation_details={"per_miner_weights": [0.1, 0.3]},
                scaling_factors={}
            )  # Include UID 0
        ]
        
        briefs = [
            {"id": "brief1", "cap": 0.0},
            {"id": "brief2", "cap": 0.0}
        ]
        
        evaluation_results = EvaluationResultCollection()
        uids = [0, 1]  # Include burn UID
        
        # Execute distribution
        rewards, stats, _, _ = self.distribution_service.calculate_distribution(
            emission_targets, evaluation_results, briefs, uids
        )
        
        # All emissions should go to burn UID (0) due to zero caps
        brief_percentages = stats[0]["brief_emission_percentages"]
        assert brief_percentages["brief1"] == 0.0
        assert brief_percentages["brief2"] == 0.0
        
    def test_single_brief_exceeds_one(self):
        """Test scenario where single brief would exceed 1.0 without cap."""
        emission_targets = [
            EmissionTarget(
                brief_id="mega_brief", 
                usd_target=2000.0,
                allocation_details={"per_miner_weights": [0.1, 1.5, 0.8]},
                scaling_factors={}
            )  # Include UID 0
        ]
        
        briefs = [{"id": "mega_brief", "cap": 0.9}]  # Cap at 90%
        
        evaluation_results = EvaluationResultCollection()
        uids = [0, 1, 2]  # Include burn UID
        
        # Execute distribution
        rewards, stats, _, _ = self.distribution_service.calculate_distribution(
            emission_targets, evaluation_results, briefs, uids
        )
        
        # Should be capped at 0.9 and then globally scaled if needed
        brief_percentage = stats[0]["brief_emission_percentages"]["mega_brief"]
        assert brief_percentage <= 0.9 + 1e-10
        
        # Total rewards should sum to 1.0
        assert abs(rewards.sum() - 1.0) < 1e-10
        
    def test_performance_with_many_briefs(self):
        """Test performance with many briefs and complex cap constraints."""
        import time
        
        # Create many emission targets
        num_briefs = 50
        num_miners = 20
        
        emission_targets = []
        briefs = []
        
        for i in range(num_briefs):
            weights = np.random.rand(num_miners) * 0.1  # Small random weights
            emission_targets.append(
                EmissionTarget(
                    brief_id=f"brief_{i}", 
                    usd_target=float(np.random.rand() * 1000),
                    allocation_details={"per_miner_weights": weights.tolist()},
                    scaling_factors={}
                )
            )
            briefs.append({"id": f"brief_{i}", "cap": np.random.rand() * 0.5})  # Random caps
        
        evaluation_results = EvaluationResultCollection()
        uids = list(range(1, num_miners + 1))
        
        # Benchmark execution time
        start_time = time.time()
        rewards, stats, _, _ = self.distribution_service.calculate_distribution(
            emission_targets, evaluation_results, briefs, uids
        )
        execution_time = time.time() - start_time
        
        # Should complete in reasonable time (< 0.5 seconds)
        assert execution_time < 0.5
        
        # Verify correctness
        assert len(rewards) == num_miners
        assert abs(rewards.sum() - 1.0) < 1e-10
        assert "brief_emission_percentages" in stats[0]
        assert len(stats[0]["brief_emission_percentages"]) == num_briefs
        
    def test_caps_with_community_reserve(self):
        """Test that caps work correctly with community reserve allocation."""
        emission_targets = [
            EmissionTarget(
                brief_id="brief1", 
                usd_target=400.0,
                allocation_details={"per_miner_weights": [0.0, 0.5, 0.3]},
                scaling_factors={}
            )  # UID 0 gets 0
        ]
        
        briefs = [{"id": "brief1", "cap": 0.6}]
        evaluation_results = EvaluationResultCollection()
        uids = [0, 1, 2]  # Include burn UID
        
        # Execute distribution (includes community reserve allocation)
        with patch('bitcast.validator.reward_engine.services.reward_distribution_service.allocate_community_reserve') as mock_reserve:
            mock_reserve.return_value = np.array([0.2, 0.4, 0.4])  # Mock reserve allocation
            
            rewards, stats, _, _ = self.distribution_service.calculate_distribution(
                emission_targets, evaluation_results, briefs, uids
            )
        
        # Verify community reserve was called
        mock_reserve.assert_called_once()
        
        # Verify final rewards
        assert len(rewards) == 3
        np.testing.assert_array_equal(rewards, [0.2, 0.4, 0.4]) 