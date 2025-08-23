"""Unit tests for WeightCorrectionsService."""

import pytest
import numpy as np
from unittest.mock import Mock

from bitcast.validator.reward_engine.services.weight_corrections_service import WeightCorrectionsService
from bitcast.validator.reward_engine.models.evaluation_result import EvaluationResultCollection, AccountResult


class TestWeightCorrectionsService:
    """Test WeightCorrectionsService class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = WeightCorrectionsService()
        
    def test_calculate_corrections_basic(self):
        """Test basic scaling factor calculation."""
        # Create mock evaluation results
        evaluation_results = self._create_mock_evaluation_results()
        
        # Create weight matrices
        pre_constraint_weights = np.array([[1.0, 0.5], [0.8, 0.3]], dtype=np.float64)
        post_constraint_weights = np.array([[0.6, 0.3], [0.48, 0.18]], dtype=np.float64)  # 60% scaling
        
        briefs = [
            {"id": "brief_1"},
            {"id": "brief_2"}
        ]
        
        corrections = self.service.calculate_corrections(
            evaluation_results, pre_constraint_weights, post_constraint_weights, briefs
        )
        
        # Should have 2 corrections (1 video × 2 briefs)
        assert len(corrections) == 2
        
        # Check scaling factors
        for correction in corrections:
            assert correction["content_id"] == "bitcast_video123"
            assert correction["brief_id"] in ["brief_1", "brief_2"]
            assert abs(correction["scaling_factor"] - 0.6) < 1e-10  # 60% scaling
    
    def test_zero_pre_weight_handling(self):
        """Test handling of zero pre-constraint weights."""
        evaluation_results = self._create_mock_evaluation_results()
        
        # Pre-weight is zero, post-weight is non-zero (shouldn't happen but test edge case)
        pre_constraint_weights = np.array([[0.0, 0.5]], dtype=np.float64)
        post_constraint_weights = np.array([[0.1, 0.3]], dtype=np.float64)
        
        briefs = [{"id": "brief_1"}, {"id": "brief_2"}]
        
        corrections = self.service.calculate_corrections(
            evaluation_results, pre_constraint_weights, post_constraint_weights, briefs
        )
        
        # Find correction for brief_1 (zero pre-weight)
        brief_1_correction = next(c for c in corrections if c["brief_id"] == "brief_1")
        assert brief_1_correction["scaling_factor"] == 0.0
        
        # Find correction for brief_2 (normal scaling)
        brief_2_correction = next(c for c in corrections if c["brief_id"] == "brief_2")
        assert abs(brief_2_correction["scaling_factor"] - 0.6) < 1e-10
    
    def test_complete_limitation_scaling(self):
        """Test scaling factor when content is completely limited."""
        evaluation_results = self._create_mock_evaluation_results()
        
        pre_constraint_weights = np.array([[1.0, 0.5]], dtype=np.float64)
        post_constraint_weights = np.array([[0.0, 0.0]], dtype=np.float64)  # Completely limited
        
        briefs = [{"id": "brief_1"}, {"id": "brief_2"}]
        
        corrections = self.service.calculate_corrections(
            evaluation_results, pre_constraint_weights, post_constraint_weights, briefs
        )
        
        # All scaling factors should be 0.0
        for correction in corrections:
            assert correction["scaling_factor"] == 0.0
    
    def test_no_scaling_applied(self):
        """Test when no constraints are applied (scaling factor = 1.0)."""
        evaluation_results = self._create_mock_evaluation_results()
        
        weights = np.array([[1.0, 0.5]], dtype=np.float64)
        # Same pre and post weights
        
        briefs = [{"id": "brief_1"}, {"id": "brief_2"}]
        
        corrections = self.service.calculate_corrections(
            evaluation_results, weights, weights, briefs  # Same weights
        )
        
        # All scaling factors should be 1.0
        for correction in corrections:
            assert abs(correction["scaling_factor"] - 1.0) < 1e-10
    
    def test_matrix_bounds_handling(self):
        """Test handling of matrix bounds edge cases."""
        evaluation_results = self._create_mock_evaluation_results()
        
        # Mismatched matrix sizes
        pre_constraint_weights = np.array([[1.0]], dtype=np.float64)  # 1x1
        post_constraint_weights = np.array([[0.5]], dtype=np.float64)  # 1x1
        
        briefs = [{"id": "brief_1"}, {"id": "brief_2"}]  # 2 briefs but only 1 column
        
        corrections = self.service.calculate_corrections(
            evaluation_results, pre_constraint_weights, post_constraint_weights, briefs
        )
        
        # Should handle missing brief gracefully
        assert len(corrections) == 2  # Both briefs processed, brief_2 gets 0.0
        
        # Find corrections by brief_id
        brief_1_correction = next(c for c in corrections if c["brief_id"] == "brief_1")
        brief_2_correction = next(c for c in corrections if c["brief_id"] == "brief_2")
        
        # brief_1 should have normal scaling
        assert abs(brief_1_correction["scaling_factor"] - 0.5) < 1e-10
        # brief_2 should be 0.0 (out of bounds)
        assert brief_2_correction["scaling_factor"] == 0.0
    
    def test_extract_content_id(self):
        """Test content_id extraction from various video data formats."""
        # Normal case with bitcastVideoId
        video_data = {
            "details": {"bitcastVideoId": "bitcast_abc123"}
        }
        content_id = self.service._extract_content_id(video_data, "fallback_id")
        assert content_id == "bitcast_abc123"
        
        # Missing bitcastVideoId - use fallback
        video_data = {
            "details": {"videoId": "youtube_id"}
        }
        content_id = self.service._extract_content_id(video_data, "fallback_id")
        assert content_id == "fallback_id"
        
        # Missing details entirely
        video_data = {"score": 1.0}
        content_id = self.service._extract_content_id(video_data, "fallback_id")
        assert content_id == "fallback_id"
        
        # Non-dict details
        video_data = {"details": "invalid"}
        content_id = self.service._extract_content_id(video_data, "fallback_id")
        assert content_id == "fallback_id"
    
    def test_numerical_stability(self):
        """Test numerical stability with very small numbers."""
        evaluation_results = self._create_mock_evaluation_results()
        
        # Very small numbers
        pre_constraint_weights = np.array([[1e-10, 1e-8]], dtype=np.float64)
        post_constraint_weights = np.array([[5e-11, 5e-9]], dtype=np.float64)  # 50% scaling
        
        briefs = [{"id": "brief_1"}, {"id": "brief_2"}]
        
        corrections = self.service.calculate_corrections(
            evaluation_results, pre_constraint_weights, post_constraint_weights, briefs
        )
        
        # Should handle small numbers correctly
        for correction in corrections:
            assert abs(correction["scaling_factor"] - 0.5) < 1e-6
    
    def _create_mock_evaluation_results(self):
        """Create mock evaluation results for testing."""
        evaluation_results = EvaluationResultCollection()
        
        # Mock account result with video data
        account_result = Mock()
        account_result.videos = {
            "youtube_video_123": {
                "details": {"bitcastVideoId": "bitcast_video123"},
                "brief_metrics": {
                    "brief_1": {"weight": 1.0},
                    "brief_2": {"weight": 0.5}
                }
            }
        }
        
        # Mock evaluation result
        eval_result = Mock()
        eval_result.account_results = {"account_1": account_result}
        
        evaluation_results.add_result(0, eval_result)  # UID 0
        
        return evaluation_results