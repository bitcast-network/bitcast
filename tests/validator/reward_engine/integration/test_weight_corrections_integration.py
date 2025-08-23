"""Integration tests for weight corrections publishing pipeline."""

import pytest
import numpy as np
from unittest.mock import Mock, AsyncMock, patch

from bitcast.validator.reward_engine.services.weight_corrections_service import WeightCorrectionsService
from bitcast.validator.reward_engine.services.reward_distribution_service import RewardDistributionService
from bitcast.validator.reward_engine.models.evaluation_result import (
    EvaluationResultCollection, EvaluationResult, AccountResult
)
from bitcast.validator.reward_engine.models.emission_target import EmissionTarget
from bitcast.validator.utils.weight_corrections_publisher import publish_weight_corrections


class TestWeightCorrectionsIntegration:
    """Integration tests for the complete weight corrections pipeline."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.corrections_service = WeightCorrectionsService()
        self.distribution_service = RewardDistributionService()
        
    def _create_test_evaluation_results(self):
        """Create realistic evaluation results for testing."""
        evaluation_results = EvaluationResultCollection()
        
        # Create account result with video data
        account_result = AccountResult(
            account_id="test_account_1",
            platform_data={"channel_id": "UCtest123"},
            videos={
                "video_123": {
                    "details": {"bitcastVideoId": "bitcast_video123"},
                    "brief_metrics": {
                        "brief_1": {
                            "base_score": 2.5,
                            "scaling_factor": 2000,
                            "scaled_score": 5000.0,
                            "weight": 5000.0,
                            "limitation_status": "active"
                        },
                        "brief_2": {
                            "base_score": 1.0,
                            "scaling_factor": 400,
                            "scaled_score": 400.0,
                            "weight": 400.0,
                            "limitation_status": "active"
                        }
                    }
                },
                "video_456": {
                    "details": {"bitcastVideoId": "bitcast_video456"},
                    "brief_metrics": {
                        "brief_1": {
                            "base_score": 1.8,
                            "scaling_factor": 2000,
                            "scaled_score": 3600.0,
                            "weight": 3600.0,
                            "limitation_status": "limited_fifo"  # This video was limited
                        }
                    }
                }
            },
            scores={"brief_1": 8600.0, "brief_2": 400.0},
            performance_stats={},
            success=True
        )
        
        # Create evaluation result
        eval_result = EvaluationResult(
            uid=1,
            platform="youtube",
            account_results={"test_account_1": account_result}
        )
        
        evaluation_results.add_result(1, eval_result)
        return evaluation_results
    
    def _create_test_emission_targets(self):
        """Create emission targets for testing."""
        return [
            EmissionTarget(
                brief_id="brief_1",
                usd_target=100.0,
                allocation_details={"per_miner_weights": [8600.0]},
                scaling_factors={"boost_factor": 1.0}
            ),
            EmissionTarget(
                brief_id="brief_2", 
                usd_target=20.0,
                allocation_details={"per_miner_weights": [400.0]},
                scaling_factors={"boost_factor": 1.0}
            )
        ]
    
    def test_end_to_end_weight_corrections_pipeline(self):
        """Test the complete pipeline from evaluation results to corrections calculation."""
        # Setup
        evaluation_results = self._create_test_evaluation_results()
        emission_targets = self._create_test_emission_targets()
        briefs = [{"id": "brief_1"}, {"id": "brief_2"}]
        uids = [1]
        
        # Get final rewards through distribution service
        final_rewards, stats_list, pre_constraint_weights, post_constraint_weights = (
            self.distribution_service.calculate_distribution(
                emission_targets, evaluation_results, briefs, uids
            )
        )
        
        # Calculate corrections
        corrections = self.corrections_service.calculate_corrections(
            evaluation_results, pre_constraint_weights, post_constraint_weights, briefs
        )
        
        # Verify corrections structure
        assert len(corrections) > 0
        for correction in corrections:
            assert "content_id" in correction
            assert "brief_id" in correction  
            assert "scaling_factor" in correction
            assert correction["content_id"].startswith("bitcast_")
            assert correction["brief_id"] in ["brief_1", "brief_2"]
            assert isinstance(correction["scaling_factor"], float)
            assert 0.0 <= correction["scaling_factor"] <= 10.0
    
    def test_scaling_factors_accuracy(self):
        """Test that scaling factors accurately represent constraint transformations."""
        evaluation_results = self._create_test_evaluation_results()
        emission_targets = self._create_test_emission_targets()
        briefs = [{"id": "brief_1", "cap": 0.5}, {"id": "brief_2", "cap": 0.8}]  # Add caps
        uids = [1]
        
        # Get weights matrices
        final_rewards, stats_list, pre_constraint_weights, post_constraint_weights = (
            self.distribution_service.calculate_distribution(
                emission_targets, evaluation_results, briefs, uids
            )
        )
        
        # Calculate corrections
        corrections = self.corrections_service.calculate_corrections(
            evaluation_results, pre_constraint_weights, post_constraint_weights, briefs
        )
        
        # Verify that scaling factors reflect the constraint transformations
        # When caps are applied, scaling factors should be < 1.0 for affected briefs
        brief_1_corrections = [c for c in corrections if c["brief_id"] == "brief_1"]
        brief_2_corrections = [c for c in corrections if c["brief_id"] == "brief_2"]
        
        assert len(brief_1_corrections) > 0
        assert len(brief_2_corrections) > 0
        
        # Check that scaling factors are reasonable
        for correction in corrections:
            scaling_factor = correction["scaling_factor"]
            assert 0.0 <= scaling_factor <= 1.0  # Should be reduced due to caps
    
    @pytest.mark.asyncio
    async def test_publishing_integration(self):
        """Test integration with the publishing system."""
        evaluation_results = self._create_test_evaluation_results()
        emission_targets = self._create_test_emission_targets()
        briefs = [{"id": "brief_1"}, {"id": "brief_2"}]
        uids = [1]
        
        # Get corrections
        final_rewards, stats_list, pre_constraint_weights, post_constraint_weights = (
            self.distribution_service.calculate_distribution(
                emission_targets, evaluation_results, briefs, uids
            )
        )
        
        corrections = self.corrections_service.calculate_corrections(
            evaluation_results, pre_constraint_weights, post_constraint_weights, briefs
        )
        
        # Mock the publishing (now uses UnifiedDataPublisher directly)
        with patch('bitcast.validator.utils.weight_corrections_publisher.UnifiedDataPublisher') as mock_publisher_class:
            mock_publisher = AsyncMock()
            mock_publisher.publish_unified_payload = AsyncMock(return_value=True)
            mock_publisher_class.return_value = mock_publisher
            
            mock_wallet = Mock()
            run_id = "test_run_123"
            endpoint = "http://test:8001/weight-corrections"
            
            # Test publishing
            await publish_weight_corrections(corrections, run_id, mock_wallet, endpoint)
            
            # Verify publisher was called correctly
            mock_publisher_class.assert_called_once_with(mock_wallet)
            mock_publisher.publish_unified_payload.assert_called_once_with(
                payload_type="weight_corrections",
                run_id=run_id,
                payload_data=corrections,
                endpoint=endpoint
            )
    
    def test_constraint_scenarios(self):
        """Test various constraint scenarios and their impact on scaling factors."""
        evaluation_results = self._create_test_evaluation_results()
        emission_targets = self._create_test_emission_targets()
        uids = [1]
        
        # Scenario 1: No constraints (should have scaling factors near 1.0)
        briefs_no_constraints = [{"id": "brief_1", "cap": 1.0}, {"id": "brief_2", "cap": 1.0}]
        
        _, _, pre_weights_1, post_weights_1 = self.distribution_service.calculate_distribution(
            emission_targets, evaluation_results, briefs_no_constraints, uids
        )
        
        corrections_1 = self.corrections_service.calculate_corrections(
            evaluation_results, pre_weights_1, post_weights_1, briefs_no_constraints
        )
        
        # Scenario 2: Heavy constraints (should have scaling factors < 1.0)
        briefs_heavy_constraints = [{"id": "brief_1", "cap": 0.1}, {"id": "brief_2", "cap": 0.1}]
        
        _, _, pre_weights_2, post_weights_2 = self.distribution_service.calculate_distribution(
            emission_targets, evaluation_results, briefs_heavy_constraints, uids
        )
        
        corrections_2 = self.corrections_service.calculate_corrections(
            evaluation_results, pre_weights_2, post_weights_2, briefs_heavy_constraints
        )
        
        # Verify that heavy constraints result in lower scaling factors
        avg_scaling_1 = np.mean([c["scaling_factor"] for c in corrections_1])
        avg_scaling_2 = np.mean([c["scaling_factor"] for c in corrections_2])
        
        assert avg_scaling_2 < avg_scaling_1  # Heavy constraints should reduce scaling factors
        assert avg_scaling_2 < 0.5  # Should be significantly reduced
    
    def test_limited_content_handling(self):
        """Test that limited content (FIFO, etc.) is handled correctly."""
        evaluation_results = self._create_test_evaluation_results()
        emission_targets = self._create_test_emission_targets()
        briefs = [{"id": "brief_1"}, {"id": "brief_2"}]
        uids = [1]
        
        # Get corrections
        _, _, pre_constraint_weights, post_constraint_weights = (
            self.distribution_service.calculate_distribution(
                emission_targets, evaluation_results, briefs, uids
            )
        )
        
        corrections = self.corrections_service.calculate_corrections(
            evaluation_results, pre_constraint_weights, post_constraint_weights, briefs
        )
        
        # Find corrections for the limited video (video_456)
        limited_corrections = [
            c for c in corrections 
            if c["content_id"] == "bitcast_video456"
        ]
        
        assert len(limited_corrections) > 0
        
        # Limited content should have scaling factors that reflect the limitation
        for correction in limited_corrections:
            # The exact scaling factor depends on the implementation, but it should be valid
            assert 0.0 <= correction["scaling_factor"] <= 1.0
    
    def test_platform_agnostic_design(self):
        """Test that the system works with platform-agnostic content IDs."""
        evaluation_results = self._create_test_evaluation_results()
        emission_targets = self._create_test_emission_targets()
        briefs = [{"id": "brief_1"}, {"id": "brief_2"}]
        uids = [1]
        
        # Get corrections
        _, _, pre_constraint_weights, post_constraint_weights = (
            self.distribution_service.calculate_distribution(
                emission_targets, evaluation_results, briefs, uids
            )
        )
        
        corrections = self.corrections_service.calculate_corrections(
            evaluation_results, pre_constraint_weights, post_constraint_weights, briefs
        )
        
        # Verify all content IDs are platform-agnostic (bitcast_xxx format)
        for correction in corrections:
            content_id = correction["content_id"]
            assert content_id.startswith("bitcast_") or content_id.startswith("video_")  # Fallback case
            
        # Verify the system doesn't depend on YouTube-specific IDs
        content_ids = {c["content_id"] for c in corrections}
        assert len(content_ids) > 0
        assert all("youtube" not in cid.lower() for cid in content_ids)