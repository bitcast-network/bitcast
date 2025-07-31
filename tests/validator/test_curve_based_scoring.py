"""
Unit tests for the main curve-based scoring logic.
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

from bitcast.validator.platforms.youtube.evaluation.curve_based_scoring import (
    calculate_curve_based_score
)


class TestCurveBasedScoring(unittest.TestCase):
    """Test cases for curve-based scoring functions."""

    @patch('bitcast.validator.platforms.youtube.evaluation.curve_based_scoring.datetime')
    def test_calculate_curve_based_score_ypp(self, mock_datetime):
        """Test curve-based scoring for YPP account."""
        mock_datetime.now.return_value = datetime(2024, 1, 15)
        mock_datetime.strptime = datetime.strptime
        import datetime as dt
        mock_datetime.timedelta = dt.timedelta
        
        daily_analytics = [
            {"day": "2024-01-01", "estimatedRedPartnerRevenue": 5.0},
            {"day": "2024-01-02", "estimatedRedPartnerRevenue": 7.0},
            {"day": "2024-01-03", "estimatedRedPartnerRevenue": 10.0}
        ]
        
        result = calculate_curve_based_score(
            daily_analytics, "2024-01-01", "2024-01-15", True, None, "test_video_ypp_001"
        )
        
        self.assertIn("score", result)
        self.assertEqual(result["scoring_method"], "ypp_curve_based")
        self.assertIsInstance(result["score"], (int, float))

    @patch('bitcast.validator.platforms.youtube.evaluation.curve_based_scoring.datetime')
    def test_calculate_curve_based_score_non_ypp(self, mock_datetime):
        """Test curve-based scoring for Non-YPP account."""
        mock_datetime.now.return_value = datetime(2024, 1, 15)
        mock_datetime.strptime = datetime.strptime
        import datetime as dt
        mock_datetime.timedelta = dt.timedelta
        
        daily_analytics = [
            {"day": "2024-01-01", "estimatedMinutesWatched": 1000},
            {"day": "2024-01-02", "estimatedMinutesWatched": 1500},
            {"day": "2024-01-03", "estimatedMinutesWatched": 2000}
        ]
        
        result = calculate_curve_based_score(
            daily_analytics, "2024-01-01", "2024-01-15", False, None, "test_video_non_ypp_001"
        )
        
        self.assertIn("score", result)
        self.assertEqual(result["scoring_method"], "non_ypp_curve_based")
        self.assertIn("revenue_multiplier", result)
        
        # Verify multiplier is applied
        from bitcast.validator.utils.config import YT_NON_YPP_REVENUE_MULTIPLIER
        self.assertEqual(result["revenue_multiplier"], YT_NON_YPP_REVENUE_MULTIPLIER)

    def test_calculate_curve_based_score_empty_analytics(self):
        """Test curve-based scoring with empty analytics."""
        result = calculate_curve_based_score([], "2024-01-01", "2024-01-15", True, None, "test_video_empty")
        
        self.assertIn("score", result)
        self.assertIsInstance(result["score"], (int, float))
        
    def test_curve_scoring_error_handling(self):
        """Test error handling in curve scoring."""
        # Test with invalid data that should trigger error handling
        invalid_analytics = [{"invalid": "data"}]
        
        result = calculate_curve_based_score(
            invalid_analytics, "2024-01-01", "2024-01-15", True, None, "test_video_error"
        )
        
        # Should return error result but not crash
        self.assertIn("score", result)
        self.assertIn("scoring_method", result)


if __name__ == '__main__':
    unittest.main()