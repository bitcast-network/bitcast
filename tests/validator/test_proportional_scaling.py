"""
Unit tests for proportional scaling anti-exploitation logic.
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from bitcast.validator.platforms.youtube.evaluation.proportional_scaling import (
    calculate_period_average,
    calculate_scaling_factor,
    apply_proportional_scaling,
    get_median_threshold_for_metric,
    apply_proportional_scaling_to_period
)


class TestProportionalScaling(unittest.TestCase):
    """Test cases for proportional scaling functions."""

    def test_calculate_period_average_basic(self):
        """Test basic period average calculation."""
        daily_data = [
            {"day": "2024-01-01", "estimatedRedPartnerRevenue": 10.0},
            {"day": "2024-01-02", "estimatedRedPartnerRevenue": 20.0},
            {"day": "2024-01-03", "estimatedRedPartnerRevenue": 30.0}
        ]
        
        average = calculate_period_average(daily_data, "estimatedRedPartnerRevenue")
        self.assertEqual(average, 20.0)  # (10 + 20 + 30) / 3

    def test_calculate_period_average_empty_data(self):
        """Test period average with empty data."""
        average = calculate_period_average([], "estimatedRedPartnerRevenue")
        self.assertEqual(average, 0.0)

    def test_calculate_period_average_missing_metric(self):
        """Test period average when metric is missing."""
        daily_data = [
            {"day": "2024-01-01"},  # Missing metric
            {"day": "2024-01-02", "estimatedRedPartnerRevenue": 10.0}
        ]
        
        average = calculate_period_average(daily_data, "estimatedRedPartnerRevenue")
        self.assertEqual(average, 5.0)  # (0 + 10) / 2

    def test_calculate_scaling_factor_scaling_needed(self):
        """Test scaling factor when scaling is needed."""
        # Average exceeds threshold, should scale down
        scaling_factor = calculate_scaling_factor(10.0, 5.0)
        self.assertEqual(scaling_factor, 0.5)

    def test_calculate_scaling_factor_no_scaling_needed(self):
        """Test scaling factor when no scaling is needed."""
        # Average below threshold, no scaling needed
        scaling_factor = calculate_scaling_factor(3.0, 5.0)
        self.assertIsNone(scaling_factor)

    def test_calculate_scaling_factor_zero_threshold(self):
        """Test scaling factor with zero threshold."""
        scaling_factor = calculate_scaling_factor(10.0, 0.0)
        self.assertEqual(scaling_factor, 0.0)

    def test_calculate_scaling_factor_negative_threshold(self):
        """Test scaling factor with negative threshold (should treat as 0)."""
        scaling_factor = calculate_scaling_factor(10.0, -5.0)
        self.assertEqual(scaling_factor, 0.0)

    def test_apply_proportional_scaling_basic(self):
        """Test basic proportional scaling."""
        daily_data = [
            {"day": "2024-01-01", "estimatedRedPartnerRevenue": 10.0},
            {"day": "2024-01-02", "estimatedRedPartnerRevenue": 20.0}
        ]
        
        scaled_data = apply_proportional_scaling(daily_data, 0.5, "estimatedRedPartnerRevenue")
        
        self.assertEqual(len(scaled_data), 2)
        self.assertEqual(scaled_data[0]["estimatedRedPartnerRevenue"], 5.0)
        self.assertEqual(scaled_data[1]["estimatedRedPartnerRevenue"], 10.0)
        # Verify original data is not modified
        self.assertEqual(daily_data[0]["estimatedRedPartnerRevenue"], 10.0)

    def test_apply_proportional_scaling_preserve_relative_distribution(self):
        """Test that proportional scaling preserves relative distribution."""
        daily_data = [
            {"day": "2024-01-01", "estimatedRedPartnerRevenue": 5.0},
            {"day": "2024-01-02", "estimatedRedPartnerRevenue": 10.0},
            {"day": "2024-01-03", "estimatedRedPartnerRevenue": 15.0}
        ]
        
        scaled_data = apply_proportional_scaling(daily_data, 0.2, "estimatedRedPartnerRevenue")
        
        # Check that ratios are preserved
        original_ratio = daily_data[1]["estimatedRedPartnerRevenue"] / daily_data[0]["estimatedRedPartnerRevenue"]
        scaled_ratio = scaled_data[1]["estimatedRedPartnerRevenue"] / scaled_data[0]["estimatedRedPartnerRevenue"]
        self.assertAlmostEqual(original_ratio, scaled_ratio, places=6)

    def test_apply_proportional_scaling_zero_factor(self):
        """Test proportional scaling with zero factor."""
        daily_data = [
            {"day": "2024-01-01", "estimatedRedPartnerRevenue": 10.0},
            {"day": "2024-01-02", "estimatedRedPartnerRevenue": 20.0}
        ]
        
        scaled_data = apply_proportional_scaling(daily_data, 0.0, "estimatedRedPartnerRevenue")
        
        self.assertEqual(scaled_data[0]["estimatedRedPartnerRevenue"], 0.0)
        self.assertEqual(scaled_data[1]["estimatedRedPartnerRevenue"], 0.0)

    def test_apply_proportional_scaling_empty_data(self):
        """Test proportional scaling with empty data."""
        scaled_data = apply_proportional_scaling([], 0.5, "estimatedRedPartnerRevenue")
        self.assertEqual(scaled_data, [])

    @patch('bitcast.validator.platforms.youtube.evaluation.proportional_scaling.calculate_median_from_analytics')
    def test_get_median_threshold_for_metric_ypp(self, mock_median):
        """Test getting median threshold for YPP account."""
        mock_median.return_value = 5.0
        
        channel_analytics = {"some": "data"}
        threshold = get_median_threshold_for_metric(channel_analytics, "estimatedRedPartnerRevenue", True)
        
        self.assertEqual(threshold, 5.0)
        mock_median.assert_called_once_with(channel_analytics, "estimatedRedPartnerRevenue")

    @patch('bitcast.validator.platforms.youtube.evaluation.proportional_scaling.calculate_median_from_analytics')
    def test_get_median_threshold_for_metric_non_ypp(self, mock_median):
        """Test getting median threshold for Non-YPP account."""
        mock_median.return_value = 1000.0
        
        channel_analytics = {"some": "data"}
        threshold = get_median_threshold_for_metric(channel_analytics, "estimatedMinutesWatched", False)
        
        self.assertEqual(threshold, 1000.0)
        mock_median.assert_called_once_with(channel_analytics, "estimatedMinutesWatched")

    def test_get_median_threshold_for_metric_no_analytics(self):
        """Test getting median threshold with no channel analytics."""
        threshold = get_median_threshold_for_metric(None, "estimatedRedPartnerRevenue", True)
        self.assertIsNone(threshold)

    @patch('bitcast.validator.platforms.youtube.evaluation.proportional_scaling.calculate_median_from_analytics')
    def test_get_median_threshold_for_metric_negative_median(self, mock_median):
        """Test getting median threshold when median is negative."""
        mock_median.return_value = -5.0
        
        channel_analytics = {"some": "data"}
        threshold = get_median_threshold_for_metric(channel_analytics, "estimatedRedPartnerRevenue", True)
        
        self.assertEqual(threshold, 0.0)

    @patch('bitcast.validator.platforms.youtube.evaluation.proportional_scaling.get_median_threshold_for_metric')
    def test_apply_proportional_scaling_to_period_scaling_applied(self, mock_threshold):
        """Test applying proportional scaling to period when scaling is needed."""
        mock_threshold.return_value = 5.0
        
        period_data = [
            {"day": "2024-01-01", "estimatedRedPartnerRevenue": 10.0},
            {"day": "2024-01-02", "estimatedRedPartnerRevenue": 20.0}
        ]
        
        result = apply_proportional_scaling_to_period(
            period_data, {"some": "analytics"}, "estimatedRedPartnerRevenue", True
        )
        
        # Average is 15.0, threshold is 5.0, so scaling factor should be 5.0/15.0 = 1/3
        expected_factor = 5.0 / 15.0
        self.assertAlmostEqual(result[0]["estimatedRedPartnerRevenue"], 10.0 * expected_factor, places=6)
        self.assertAlmostEqual(result[1]["estimatedRedPartnerRevenue"], 20.0 * expected_factor, places=6)

    @patch('bitcast.validator.platforms.youtube.evaluation.proportional_scaling.get_median_threshold_for_metric')
    def test_apply_proportional_scaling_to_period_no_scaling_needed(self, mock_threshold):
        """Test applying proportional scaling to period when no scaling is needed."""
        mock_threshold.return_value = 20.0  # Higher than average
        
        period_data = [
            {"day": "2024-01-01", "estimatedRedPartnerRevenue": 5.0},
            {"day": "2024-01-02", "estimatedRedPartnerRevenue": 10.0}
        ]
        
        result = apply_proportional_scaling_to_period(
            period_data, {"some": "analytics"}, "estimatedRedPartnerRevenue", True
        )
        
        # No scaling should be applied
        self.assertEqual(result[0]["estimatedRedPartnerRevenue"], 5.0)
        self.assertEqual(result[1]["estimatedRedPartnerRevenue"], 10.0)

    @patch('bitcast.validator.platforms.youtube.evaluation.proportional_scaling.get_median_threshold_for_metric')
    def test_apply_proportional_scaling_to_period_zero_threshold(self, mock_threshold):
        """Test applying proportional scaling with zero threshold."""
        mock_threshold.return_value = 0.0
        
        period_data = [
            {"day": "2024-01-01", "estimatedRedPartnerRevenue": 10.0},
            {"day": "2024-01-02", "estimatedRedPartnerRevenue": 20.0}
        ]
        
        result = apply_proportional_scaling_to_period(
            period_data, {"some": "analytics"}, "estimatedRedPartnerRevenue", True
        )
        
        # All values should be scaled to 0
        self.assertEqual(result[0]["estimatedRedPartnerRevenue"], 0.0)
        self.assertEqual(result[1]["estimatedRedPartnerRevenue"], 0.0)

    def test_apply_proportional_scaling_to_period_no_analytics(self):
        """Test applying proportional scaling with no channel analytics."""
        period_data = [
            {"day": "2024-01-01", "estimatedRedPartnerRevenue": 10.0}
        ]
        
        result = apply_proportional_scaling_to_period(
            period_data, None, "estimatedRedPartnerRevenue", True
        )
        
        # Should return original data unchanged
        self.assertEqual(result, period_data)

    def test_apply_proportional_scaling_to_period_empty_data(self):
        """Test applying proportional scaling with empty period data."""
        result = apply_proportional_scaling_to_period(
            [], {"some": "analytics"}, "estimatedRedPartnerRevenue", True
        )
        
        self.assertEqual(result, [])



    @patch('bitcast.validator.platforms.youtube.evaluation.proportional_scaling.bt.logging')
    def test_logging_scaling_applied(self, mock_logging):
        """Test that appropriate logging occurs when scaling is applied."""
        daily_data = [
            {"day": "2024-01-01", "estimatedRedPartnerRevenue": 10.0}
        ]
        
        apply_proportional_scaling(daily_data, 0.5, "estimatedRedPartnerRevenue")
        
        # Verify info level logging was called (but not debug - we removed excessive debug logging)
        mock_logging.info.assert_called()

    def test_scaling_factor_no_scaling_needed(self):
        """Test that scaling factor returns None when no scaling is needed."""
        result = calculate_scaling_factor(3.0, 5.0)  # No scaling needed
        
        # Should return None when no scaling is needed
        self.assertIsNone(result)

    def test_scaling_factor_zero_threshold(self):
        """Test that scaling factor handles zero threshold correctly."""
        result = calculate_scaling_factor(10.0, 0.0)
        
        # Should return 0.0 when threshold is zero
        self.assertEqual(result, 0.0)

    @patch('bitcast.validator.platforms.youtube.evaluation.proportional_scaling.bt.logging')
    def test_logging_negative_threshold(self, mock_logging):
        """Test that appropriate logging occurs with negative threshold."""
        calculate_scaling_factor(10.0, -5.0)
        
        # Verify warning level logging was called for negative threshold
        mock_logging.warning.assert_called()


if __name__ == '__main__':
    unittest.main()