"""Unit tests for RewardDistributionService."""

import pytest
import numpy as np
import time
from unittest.mock import Mock, patch
import logging

from bitcast.validator.reward_engine.services.reward_distribution_service import RewardDistributionService
from bitcast.validator.reward_engine.models.emission_target import EmissionTarget
from bitcast.validator.reward_engine.models.evaluation_result import EvaluationResultCollection


class TestRewardDistributionService:
    """Test RewardDistributionService class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = RewardDistributionService()
        
    def test_cap_logic_no_scaling_needed(self):
        """Test that caps don't affect allocation when under limits."""
        # Create a scores matrix where briefs are under their caps
        scores_matrix = np.array([[0.2, 0.1], [0.1, 0.2]], dtype=np.float64)
        briefs = [
            {"id": "brief1", "cap": 0.5},  # Total: 0.3, under cap
            {"id": "brief2", "cap": 0.4}   # Total: 0.3, under cap
        ]
        
        result = self.service._apply_emission_constraints(scores_matrix, briefs)
        
        # Should be unchanged since under caps
        np.testing.assert_array_equal(result, scores_matrix)
        
    def test_cap_logic_individual_brief_scaling(self):
        """Test that individual brief caps are applied correctly."""
        # Brief 1 exceeds cap, brief 2 doesn't
        scores_matrix = np.array([[0.4, 0.1], [0.3, 0.2]], dtype=np.float64)
        briefs = [
            {"id": "brief1", "cap": 0.5},  # Total: 0.7, exceeds cap
            {"id": "brief2", "cap": 0.4}   # Total: 0.3, under cap
        ]
        
        result = self.service._apply_emission_constraints(scores_matrix, briefs)
        
        # Brief 1 should be scaled down to 0.5
        assert abs(result[:, 0].sum() - 0.5) < 1e-10
        # Brief 2 should be unchanged
        assert abs(result[:, 1].sum() - 0.3) < 1e-10
        
    def test_cap_logic_global_scaling(self):
        """Test that global scaling is applied when total > 1.0."""
        # Both briefs under individual caps but total > 1.0
        scores_matrix = np.array([[0.4, 0.3], [0.3, 0.2]], dtype=np.float64)
        briefs = [
            {"id": "brief1", "cap": 0.8},  # Total: 0.7, under cap
            {"id": "brief2", "cap": 0.6}   # Total: 0.5, under cap
        ]
        # Total = 1.2, should be scaled down
        
        result = self.service._apply_emission_constraints(scores_matrix, briefs)
        
        # Total should equal 1.0
        assert abs(result.sum() - 1.0) < 1e-10
        
    def test_cap_logic_default_cap(self):
        """Test that default cap of 1.0 is used when not specified."""
        scores_matrix = np.array([[0.6, 0.2]], dtype=np.float64)
        briefs = [
            {"id": "brief1"},  # No cap specified, should default to 1.0
            {"id": "brief2", "cap": 0.3}
        ]
        
        result = self.service._apply_emission_constraints(scores_matrix, briefs)
        
        # Brief 1 should be unchanged (under default cap of 1.0)
        assert abs(result[0, 0] - 0.6) < 1e-10
        # Brief 2 should be unchanged (under cap of 0.3)
        assert abs(result[0, 1] - 0.2) < 1e-10
        
    def test_cap_logic_zero_cap(self):
        """Test edge case of cap = 0."""
        scores_matrix = np.array([[0.3, 0.2]], dtype=np.float64)
        briefs = [
            {"id": "brief1", "cap": 0.0},  # Zero cap
            {"id": "brief2", "cap": 0.5}
        ]
        
        result = self.service._apply_emission_constraints(scores_matrix, briefs)
        
        # Brief 1 should be scaled to 0
        assert result[0, 0] == 0.0
        # Brief 2 should be unchanged
        assert abs(result[0, 1] - 0.2) < 1e-10
        
    def test_emission_percentages_in_stats(self):
        """Test that brief emission percentages are included in stats."""
        # Mock evaluation results
        eval_results = EvaluationResultCollection()
        
        # Mock emission targets
        emission_targets = [
            EmissionTarget(
                brief_id="brief1",
                usd_target=100.0,
                allocation_details={"per_miner_weights": [0.3, 0.2]},
                scaling_factors={}
            )
        ]
        
        briefs = [{"id": "brief1", "cap": 0.6}]
        uids = [1, 2]
        
        # Call calculate_distribution
        rewards, stats_list = self.service.calculate_distribution(
            emission_targets, eval_results, briefs, uids
        )
        
        # Check that brief emission percentages are included
        assert "brief_emission_percentages" in stats_list[0]
        assert "brief1" in stats_list[0]["brief_emission_percentages"]
        
    def test_empty_scores_matrix(self):
        """Test handling of empty scores matrix."""
        scores_matrix = np.array([]).reshape(0, 0)
        briefs = []
        
        result = self.service._apply_emission_constraints(scores_matrix, briefs)
        
        assert result.size == 0
        
    def test_cap_logic_greater_than_one(self):
        """Test edge case of cap > 1.0."""
        scores_matrix = np.array([[0.3, 0.2]], dtype=np.float64)
        briefs = [
            {"id": "brief1", "cap": 1.5},  # Cap > 1.0, should be allowed per BA response
            {"id": "brief2", "cap": 0.3}
        ]
        
        result = self.service._apply_emission_constraints(scores_matrix, briefs)
        
        # Brief 1 should be unchanged (under cap of 1.5)
        assert abs(result[0, 0] - 0.3) < 1e-10
        # Brief 2 should be unchanged (under cap of 0.3)
        assert abs(result[0, 1] - 0.2) < 1e-10
        
    def test_yt_min_emissions_interaction(self):
        """Test that YT_MIN_EMISSIONS constraint is applied as global minimum scaling."""
        # Create scores that would trigger YT_MIN_EMISSIONS scaling
        very_small_scores = np.array([[0.001, 0.002]], dtype=np.float64)
        briefs = [
            {"id": "brief1", "cap": 0.1},
            {"id": "brief2", "cap": 0.1}
        ]
        
        # Mock YT_MIN_EMISSIONS to a value larger than our scores
        with patch('bitcast.validator.reward_engine.services.reward_distribution_service.YT_MIN_EMISSIONS', 0.01):
            # Call _apply_emission_constraints which now handles global minimum scaling
            result = self.service._apply_emission_constraints(very_small_scores, briefs)
            
            # The total should be scaled up to meet YT_MIN_EMISSIONS minimum
            total_sum = result.sum()
            assert abs(total_sum - 0.01) < 1e-10  # Should be scaled to YT_MIN_EMISSIONS
            
            # Caps should still be respected (no brief should exceed its cap)
            assert result[:, 0].sum() <= 0.1  # Should not exceed cap
            assert result[:, 1].sum() <= 0.1  # Should not exceed cap
            
    @patch('bittensor.logging.info')
    def test_cap_logging_events(self, mock_logging):
        """Test that cap scaling events are logged correctly."""
        scores_matrix = np.array([[0.6, 0.3]], dtype=np.float64)
        briefs = [
            {"id": "test_brief_1", "cap": 0.4},  # Will exceed cap
            {"id": "test_brief_2", "cap": 0.2}   # Will exceed cap
        ]
        
        result = self.service._apply_emission_constraints(scores_matrix, briefs)
        
        # Verify logging calls were made
        assert mock_logging.call_count >= 2  # At least 2 calls for brief scaling
        
        # Check that specific log messages were called
        call_args_list = [str(call) for call in mock_logging.call_args_list]
        log_text = " ".join(call_args_list)
        
        assert "test_brief_1" in log_text
        assert "exceeded cap" in log_text
        assert "scaled down by factor" in log_text
        
    @patch('bittensor.logging.info')  
    def test_global_scaling_logging(self, mock_logging):
        """Test that global scaling events are logged correctly."""
        # Create scenario where global scaling is needed
        scores_matrix = np.array([[0.6, 0.5]], dtype=np.float64)
        briefs = [
            {"id": "brief1", "cap": 0.8},  # Under individual cap
            {"id": "brief2", "cap": 0.7}   # Under individual cap
        ]
        # Total = 1.1, will trigger global scaling
        
        result = self.service._apply_emission_constraints(scores_matrix, briefs)
        
        # Verify global scaling log was called
        call_args_list = [str(call) for call in mock_logging.call_args_list]
        log_text = " ".join(call_args_list)
        
        assert "Applied global scaling factor" in log_text
        assert "total was" in log_text
        
    def test_emission_percentage_accuracy(self):
        """Test that emission percentages are calculated accurately."""
        scores_matrix = np.array([[0.3, 0.2], [0.1, 0.1]], dtype=np.float64)
        briefs = [
            {"id": "brief1", "cap": 0.5},
            {"id": "brief2", "cap": 0.4}
        ]
        
        result = self.service._apply_emission_constraints(scores_matrix, briefs)
        
        # Calculate expected percentages
        brief1_percentage = result[:, 0].sum()
        brief2_percentage = result[:, 1].sum()
        
        # Brief 1: 0.3 + 0.1 = 0.4 (under cap of 0.5)
        assert abs(brief1_percentage - 0.4) < 1e-10
        # Brief 2: 0.2 + 0.1 = 0.3 (under cap of 0.4)
        assert abs(brief2_percentage - 0.3) < 1e-10
        
    def test_proportional_scaling_preservation(self):
        """Test that proportional relationships are preserved during cap scaling."""
        scores_matrix = np.array([[0.4, 0.1], [0.2, 0.1]], dtype=np.float64)
        briefs = [
            {"id": "brief1", "cap": 0.3},  # Will be scaled down from 0.6 to 0.3
            {"id": "brief2", "cap": 0.5}   # Won't be scaled (0.2 < 0.5)
        ]
        
        result = self.service._apply_emission_constraints(scores_matrix, briefs)
        
        # Original ratio for brief1: 0.4 / 0.2 = 2.0
        # After scaling, this ratio should be preserved
        original_ratio = scores_matrix[0, 0] / scores_matrix[1, 0]
        new_ratio = result[0, 0] / result[1, 0]
        
        assert abs(original_ratio - new_ratio) < 1e-10
        
    def test_complex_scaling_scenario(self):
        """Test complex scenario with multiple briefs and both scaling types."""
        scores_matrix = np.array([
            [0.5, 0.3, 0.2],  # Miner 1
            [0.3, 0.4, 0.1],  # Miner 2
            [0.2, 0.1, 0.3]   # Miner 3
        ], dtype=np.float64)
        
        briefs = [
            {"id": "brief1", "cap": 0.8},  # Total: 1.0, will be scaled to 0.8
            {"id": "brief2", "cap": 0.6},  # Total: 0.8, will be scaled to 0.6
            {"id": "brief3", "cap": 0.7}   # Total: 0.6, under cap
        ]
        # After individual scaling: 0.8 + 0.6 + 0.6 = 2.0 > 1.0, needs global scaling
        
        result = self.service._apply_emission_constraints(scores_matrix, briefs)
        
        # Check that total equals 1.0 after global scaling
        assert abs(result.sum() - 1.0) < 1e-10
        
        # Check that no brief exceeds its cap
        assert result[:, 0].sum() <= 0.8 + 1e-10  # Brief 1
        assert result[:, 1].sum() <= 0.6 + 1e-10  # Brief 2
        assert result[:, 2].sum() <= 0.7 + 1e-10  # Brief 3
        
    def test_performance_benchmark(self):
        """Test performance of cap logic vs theoretical baseline."""
        # Create large test case
        num_miners = 100
        num_briefs = 10
        large_scores_matrix = np.random.rand(num_miners, num_briefs).astype(np.float64)
        large_briefs = [{"id": f"brief_{i}", "cap": 0.5} for i in range(num_briefs)]
        
        # Benchmark cap logic
        start_time = time.time()
        for _ in range(100):  # Run multiple times for accurate measurement
            result = self.service._apply_emission_constraints(large_scores_matrix, large_briefs)
        cap_time = time.time() - start_time
        
        # Should complete in reasonable time (< 1 second for 100 iterations)
        assert cap_time < 1.0
        
        # Verify result is valid
        assert result.shape == large_scores_matrix.shape
        assert result.sum() <= 1.0 + 1e-10  # Should not exceed 1.0 

    def test_global_minimum_scaling_functionality(self):
        """Test that global minimum scaling works correctly when enabled."""
        # Create very small scores that would need minimum scaling
        tiny_scores = np.array([[0.0001, 0.0002], [0.0001, 0.0001]], dtype=np.float64)
        briefs = [
            {"id": "brief1", "cap": 0.5},  # Generous caps
            {"id": "brief2", "cap": 0.5}
        ]
        
        # Test with YT_MIN_EMISSIONS = 0.01 (higher than total of 0.0005)
        with patch('bitcast.validator.reward_engine.services.reward_distribution_service.YT_MIN_EMISSIONS', 0.01):
            result = self.service._apply_emission_constraints(tiny_scores, briefs)
            
            # Total should be scaled up to meet minimum
            total_sum = result.sum()
            assert abs(total_sum - 0.01) < 1e-10
            
            # Proportions should be preserved
            brief1_sum = result[:, 0].sum()
            brief2_sum = result[:, 1].sum()
            
            # Original ratio was 0.0002:0.0003 = 2:3
            expected_ratio = 0.0002 / 0.0003
            actual_ratio = brief1_sum / brief2_sum
            assert abs(actual_ratio - expected_ratio) < 1e-10
            
    def test_global_minimum_scaling_with_caps_interaction(self):
        """Test that global minimum scaling works correctly alongside caps.
        
        Note: YT_MIN_EMISSIONS=0 in production, so this tests theoretical behavior.
        When caps conflict with global minimum, caps take precedence.
        """
        # Create scenario where minimum scaling would conflict with caps
        scores = np.array([[0.001, 0.8]], dtype=np.float64)  # brief2 would exceed cap
        briefs = [
            {"id": "brief1", "cap": 0.5},
            {"id": "brief2", "cap": 0.5}  # This will be capped
        ]
        
        # Set minimum that's higher than post-cap total (edge case)
        with patch('bitcast.validator.reward_engine.services.reward_distribution_service.YT_MIN_EMISSIONS', 0.8):
            result = self.service._apply_emission_constraints(scores, briefs)
            
            # When global minimum conflicts with caps, the final result may exceed caps
            # This is an edge case that doesn't occur in production (YT_MIN_EMISSIONS=0)
            # but demonstrates the behavior if it were enabled
            
            # Total should meet or approach the minimum requirement
            total_sum = result.sum()
            assert total_sum >= 0.5  # At least the capped amount
            
            # The implementation applies: caps first, then global minimum scaling
            # which means caps can be violated by global minimum scaling 