"""
Unit tests for data processing utilities for curve-based scoring.
"""

import unittest
from datetime import datetime, timedelta

from bitcast.validator.platforms.youtube.evaluation.data_processing import (
    fill_missing_dates,
    calculate_cumulative_totals,
    get_period_averages
)


class TestDataProcessing(unittest.TestCase):
    """Test cases for data processing functions."""

    def test_fill_missing_dates_basic(self):
        """Test filling missing dates in analytics data."""
        daily_analytics = [
            {"day": "2023-01-01", "estimatedRedPartnerRevenue": 5.0},
            {"day": "2023-01-03", "estimatedRedPartnerRevenue": 7.0}  # Missing 2023-01-02
        ]
        
        result = fill_missing_dates(daily_analytics, "2023-01-01", "2023-01-03")
        
        self.assertEqual(len(result), 3)
        self.assertEqual(result[1]["day"], "2023-01-02")
        self.assertEqual(result[1]["estimatedRedPartnerRevenue"], 0.0)

    def test_calculate_cumulative_totals_basic(self):
        """Test cumulative total calculation."""
        daily_analytics = [
            {"day": "2023-01-01", "estimatedRedPartnerRevenue": 5.0},
            {"day": "2023-01-02", "estimatedRedPartnerRevenue": 3.0},
            {"day": "2023-01-03", "estimatedRedPartnerRevenue": 2.0}
        ]
        
        result = calculate_cumulative_totals(daily_analytics, "estimatedRedPartnerRevenue")
        
        self.assertEqual(result[0]["cumulative_estimatedRedPartnerRevenue"], 5.0)
        self.assertEqual(result[1]["cumulative_estimatedRedPartnerRevenue"], 8.0)
        self.assertEqual(result[2]["cumulative_estimatedRedPartnerRevenue"], 10.0)

    def test_get_period_averages_integration(self):
        """Test integrated period averages calculation."""
        daily_analytics = [
            {"day": "2023-01-01", "estimatedRedPartnerRevenue": 5.0},
            {"day": "2023-01-02", "estimatedRedPartnerRevenue": 10.0},
            {"day": "2023-01-03", "estimatedRedPartnerRevenue": 15.0}
        ]
        
        day1_avg, day2_avg = get_period_averages(
            daily_analytics,
            "estimatedRedPartnerRevenue",
            "2023-01-01", "2023-01-02",  # Day 1 period
            "2023-01-02", "2023-01-03",  # Day 2 period
            2,  # 2-day window
            None,  # No channel analytics
            True   # YPP account
        )
        
        self.assertIsInstance(day1_avg, float)
        self.assertIsInstance(day2_avg, float)
        self.assertGreaterEqual(day1_avg, 0)
        self.assertGreaterEqual(day2_avg, 0)


if __name__ == '__main__':
    unittest.main()