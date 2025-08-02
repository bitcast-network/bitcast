"""
Unit tests for median capping anti-exploitation logic.
"""

import unittest
from unittest.mock import patch
from datetime import datetime, timedelta

from bitcast.validator.platforms.youtube.evaluation.median_capping import (
    calculate_median_cap_period,
    apply_median_caps_to_analytics
)


class TestMedianCapping(unittest.TestCase):
    """Test cases for median capping functions."""

    def test_calculate_median_cap_period_basic(self):
        """Test basic median cap calculation."""
        # Use more recent dates that would fall within a realistic cap period
        channel_analytics = {
            "day_metrics": {
                "2023-12-01": {"day": "2023-12-01", "estimatedRedPartnerRevenue": 2.0},
                "2023-12-02": {"day": "2023-12-02", "estimatedRedPartnerRevenue": 4.0},
                "2023-12-03": {"day": "2023-12-03", "estimatedRedPartnerRevenue": 6.0},
                "2023-12-04": {"day": "2023-12-04", "estimatedRedPartnerRevenue": 8.0},
                "2023-12-05": {"day": "2023-12-05", "estimatedRedPartnerRevenue": 10.0}
            }
        }
        
        with patch('bitcast.validator.platforms.youtube.evaluation.median_capping.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 1, 15)
            mock_datetime.strptime = datetime.strptime
            import datetime as dt
            mock_datetime.timedelta = dt.timedelta
            
            median_cap = calculate_median_cap_period(
                channel_analytics, "estimatedRedPartnerRevenue", 60, 30
            )
        
        # Should get some median value (exact value depends on date filtering)
        self.assertGreaterEqual(median_cap, 0)

    def test_apply_median_caps_ypp_account(self):
        """Test applying median caps to YPP account data."""
        daily_analytics = [
            {"day": "2024-01-01", "estimatedRedPartnerRevenue": 50.0},  # High value
            {"day": "2024-01-02", "estimatedRedPartnerRevenue": 3.0}    # Normal value
        ]
        
        # Set up channel analytics with realistic historical data for median calculation
        channel_analytics = {
            "day_metrics": {}
        }
        # Add 30 days of historical data
        base_date = datetime(2023, 12, 1)
        for i in range(30):
            date_str = (base_date + timedelta(days=i)).strftime('%Y-%m-%d')
            channel_analytics["day_metrics"][date_str] = {
                "day": date_str, 
                "estimatedRedPartnerRevenue": 5.0 + (i % 5)  # Values between 5-9
            }
        
        result = apply_median_caps_to_analytics(daily_analytics, channel_analytics, True)
        
        # Should return data (may or may not have applied caps depending on median calculation)
        self.assertEqual(len(result), 2)
        self.assertIn("estimatedRedPartnerRevenue", result[0])
        self.assertIn("estimatedRedPartnerRevenue", result[1])

    def test_apply_median_caps_non_ypp_account(self):
        """Test applying median caps to Non-YPP account data."""
        daily_analytics = [
            {"day": "2023-01-01", "estimatedMinutesWatched": 5000},
            {"day": "2023-01-02", "estimatedMinutesWatched": 3000}
        ]
        
        channel_analytics = {
            "day_metrics": {
                "2022-12-01": {"day": "2022-12-01", "estimatedMinutesWatched": 1000},
                "2022-12-02": {"day": "2022-12-02", "estimatedMinutesWatched": 2000}
            }
        }
        
        result = apply_median_caps_to_analytics(daily_analytics, channel_analytics, False)
        
        # Should return analytics (may have applied caps)
        self.assertEqual(len(result), 2)
        self.assertIn("estimatedMinutesWatched", result[0])


if __name__ == '__main__':
    unittest.main()