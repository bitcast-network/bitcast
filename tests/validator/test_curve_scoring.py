"""
Unit tests for curve-based scoring calculation functions.
"""

import unittest

from bitcast.validator.platforms.youtube.evaluation.curve_scoring import (
    calculate_curve_value,
    calculate_curve_difference
)


class TestCurveScoring(unittest.TestCase):
    """Test cases for curve-based scoring functions."""

    def test_calculate_curve_value_basic_functionality(self):
        """Test curve calculation with various inputs."""
        # Zero input
        self.assertEqual(calculate_curve_value(0.0), 0.0)
        
        # Negative input should return 0
        self.assertEqual(calculate_curve_value(-10.0), 0.0)
        
        # Positive value: sqrt(1) / (1 + 0.1 * sqrt(1)) = 1/1.1 ≈ 0.909091
        result = calculate_curve_value(1.0)
        expected = 1.0 / (1 + 0.1 * 1.0)
        self.assertAlmostEqual(result, expected, places=6)
        
        # Large value should show diminishing returns
        result_large = calculate_curve_value(10000.0)
        self.assertGreater(result_large, result)  # Should be larger but not 10000x larger

    def test_curve_value_error_handling(self):
        """Test curve calculation with invalid inputs."""
        self.assertEqual(calculate_curve_value(float('inf')), 0.0)
        self.assertEqual(calculate_curve_value(float('-inf')), 0.0)
        self.assertEqual(calculate_curve_value(float('nan')), 0.0)

    def test_calculate_curve_difference(self):
        """Test curve difference calculation."""
        # Positive growth
        result_growth = calculate_curve_difference(100.0, 150.0)
        self.assertGreater(result_growth, 0)
        
        # Decline
        result_decline = calculate_curve_difference(150.0, 100.0)
        self.assertLess(result_decline, 0)
        
        # No change
        result_same = calculate_curve_difference(100.0, 100.0)
        self.assertAlmostEqual(result_same, 0.0, places=6)


if __name__ == '__main__':
    unittest.main()