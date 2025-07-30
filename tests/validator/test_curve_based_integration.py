"""
Integration tests for the complete curve-based scoring system.
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import numpy as np


class TestCurveBasedIntegration(unittest.TestCase):
    """Test the complete curve-based scoring system integration."""

    def test_end_to_end_ypp_scoring_pipeline(self):
        """Test complete YPP account scoring pipeline."""
        from bitcast.validator.platforms.youtube.evaluation.scoring import calculate_video_score
        from bitcast.validator.reward_engine.services.emission_calculation_service import EmissionCalculationService
        from bitcast.validator.reward_engine.models.score_matrix import ScoreMatrix
        
        # Mock realistic YPP data
        daily_analytics = []
        base_date = datetime.now() - timedelta(days=20)
        for i in range(15):
            date_str = (base_date + timedelta(days=i)).strftime('%Y-%m-%d')
            daily_analytics.append({
                "day": date_str,
                "estimatedRedPartnerRevenue": 5.0 + (i * 0.5)  # Growing revenue
            })
        
        # Mock channel analytics for median capping
        channel_analytics = {"day_metrics": {}}
        for i in range(30, 61):  # T-60 to T-30 
            date_str = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            channel_analytics["day_metrics"][date_str] = {
                "day": date_str,
                "estimatedRedPartnerRevenue": 3.0 + (i % 5)
            }

        with patch('bitcast.validator.platforms.youtube.evaluation.scoring.get_video_analytics') as mock_analytics:
            mock_analytics.return_value = {"day_metrics": {item["day"]: item for item in daily_analytics}}
            
            with patch('bitcast.validator.platforms.youtube.evaluation.scoring.datetime') as mock_datetime:
                mock_datetime.now.return_value = datetime(2024, 1, 15)
                mock_datetime.strptime = datetime.strptime
                import datetime as dt
                mock_datetime.timedelta = dt.timedelta
                
                result = calculate_video_score(
                    "test_video",
                    MagicMock(),
                    "2024-01-01T00:00:00Z",
                    {},
                    is_ypp_account=True,
                    channel_analytics=channel_analytics
                )
        
        # Validate curve-based scoring result structure
        self.assertIn("score", result)
        self.assertEqual(result["scoring_method"], "ypp_curve_based")
        self.assertIsInstance(result["score"], (int, float))
        
        # Test compatibility with EmissionCalculationService
        score_matrix = ScoreMatrix(np.array([[result["score"]]]))
        emission_service = EmissionCalculationService()
        briefs = [{"id": "test_brief", "format": "dedicated", "boost": 1.0}]
        
        targets = emission_service.calculate_targets(score_matrix, briefs)
        
        self.assertEqual(len(targets), 1)
        self.assertIsInstance(targets[0].usd_target, float)
        self.assertTrue(targets[0].usd_target >= 0)

    def test_end_to_end_non_ypp_scoring_pipeline(self):
        """Test complete Non-YPP account scoring pipeline."""
        from bitcast.validator.platforms.youtube.evaluation.scoring import calculate_video_score
        from bitcast.validator.utils.config import YT_NON_YPP_REVENUE_MULTIPLIER
        
        daily_analytics = []
        base_date = datetime.now() - timedelta(days=20)
        for i in range(15):
            date_str = (base_date + timedelta(days=i)).strftime('%Y-%m-%d')
            daily_analytics.append({
                "day": date_str,
                "estimatedMinutesWatched": 1000 + (i * 100)
            })
        
        channel_analytics = {"day_metrics": {}}
        for i in range(30, 61):
            date_str = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            channel_analytics["day_metrics"][date_str] = {
                "day": date_str,
                "estimatedMinutesWatched": 800 + (i % 10) * 50
            }

        with patch('bitcast.validator.platforms.youtube.evaluation.scoring.get_video_analytics') as mock_analytics:
            mock_analytics.return_value = {"day_metrics": {item["day"]: item for item in daily_analytics}}
            
            with patch('bitcast.validator.platforms.youtube.evaluation.scoring.datetime') as mock_datetime:
                mock_datetime.now.return_value = datetime(2024, 1, 15)
                mock_datetime.strptime = datetime.strptime
                import datetime as dt
                mock_datetime.timedelta = dt.timedelta
                
                result = calculate_video_score(
                    "test_video",
                    MagicMock(),
                    "2024-01-01T00:00:00Z",
                    {},
                    is_ypp_account=False,
                    channel_analytics=channel_analytics
                )
        
        self.assertEqual(result["scoring_method"], "non_ypp_curve_based")
        self.assertIn("revenue_multiplier", result)
        self.assertEqual(result["revenue_multiplier"], YT_NON_YPP_REVENUE_MULTIPLIER)

    def test_edge_case_handling(self):
        """Test handling of edge cases like missing data and extreme values."""
        from bitcast.validator.platforms.youtube.evaluation.scoring import calculate_video_score
        
        # Test with sparse data
        daily_analytics = [{
            "day": (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d'),
            "estimatedRedPartnerRevenue": 2.5
        }]
        
        with patch('bitcast.validator.platforms.youtube.evaluation.scoring.get_video_analytics') as mock_analytics:
            mock_analytics.return_value = {"day_metrics": {item["day"]: item for item in daily_analytics}}
            
            with patch('bitcast.validator.platforms.youtube.evaluation.scoring.datetime') as mock_datetime:
                mock_datetime.now.return_value = datetime(2024, 1, 15)
                mock_datetime.strptime = datetime.strptime
                import datetime as dt
                mock_datetime.timedelta = dt.timedelta
                
                result = calculate_video_score(
                    "test_video",
                    MagicMock(),
                    "2024-01-01T00:00:00Z",
                    {},
                    is_ypp_account=True,
                    channel_analytics=None
                )
        
        # Should handle gracefully
        self.assertIn("score", result)
        self.assertIn("scoring_method", result)
        self.assertIsInstance(result["score"], (int, float))


if __name__ == '__main__':
    unittest.main()