"""
Unit tests for curve-based scoring calculation functions.
"""

import unittest

from bitcast.validator.platforms.youtube.evaluation.curve_scoring import (
    calculate_curve_value,
    calculate_curve_difference,
    calculate_adjusted_curve_difference
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


class TestAdjustedCurveDifference(unittest.TestCase):
    """Test cases for adjusted curve difference with lifetime deduction."""

    def test_lifetime_deduction_reduces_score(self):
        """Adjusted score should be lower than unadjusted score."""
        raw = calculate_curve_difference(50.0, 100.0)
        adjusted = calculate_adjusted_curve_difference(50.0, 100.0, scaling_factor=1800, lifetime_deduction=100)
        self.assertGreater(raw, 0)
        self.assertLessEqual(adjusted, raw)

    def test_lifetime_deduction_exact_amount_dedicated(self):
        """Lifetime deduction of $100 for dedicated (scaling 1800)."""
        scaling = 1800
        adjusted = calculate_adjusted_curve_difference(0.0, 100.0, scaling_factor=scaling, lifetime_deduction=100)
        unadjusted = calculate_curve_difference(0.0, 100.0)
        lifetime_diff = (unadjusted - adjusted) * scaling
        self.assertAlmostEqual(lifetime_diff, 100.0, places=6)

    def test_lifetime_deduction_exact_amount_ad_read(self):
        """Lifetime deduction of $25 for ad-read (scaling 400)."""
        scaling = 400
        adjusted = calculate_adjusted_curve_difference(0.0, 100.0, scaling_factor=scaling, lifetime_deduction=25)
        unadjusted = calculate_curve_difference(0.0, 100.0)
        lifetime_diff = (unadjusted - adjusted) * scaling
        self.assertAlmostEqual(lifetime_diff, 25.0, places=6)

    def test_both_above_threshold_cancels(self):
        """When both curve values are above the threshold, deduction has no further effect."""
        scaling = 1800
        raw = calculate_curve_difference(100.0, 200.0)
        adjusted = calculate_adjusted_curve_difference(100.0, 200.0, scaling_factor=scaling, lifetime_deduction=100)
        self.assertAlmostEqual(raw, adjusted, places=6)

    def test_zero_deduction_matches_raw(self):
        """With zero deduction, adjusted should match raw curve difference."""
        raw = calculate_curve_difference(50.0, 100.0)
        adjusted = calculate_adjusted_curve_difference(50.0, 100.0, scaling_factor=1800, lifetime_deduction=0)
        self.assertAlmostEqual(raw, adjusted, places=6)

    def test_zero_inputs(self):
        """Both inputs zero should return zero."""
        result = calculate_adjusted_curve_difference(0.0, 0.0, scaling_factor=1800, lifetime_deduction=100)
        self.assertAlmostEqual(result, 0.0, places=6)

    def test_different_deductions_produce_different_results(self):
        """Dedicated ($100) and ad-read ($25) deductions should produce different adjusted scores."""
        dedicated = calculate_adjusted_curve_difference(0.0, 100.0, scaling_factor=1800, lifetime_deduction=100)
        ad_read = calculate_adjusted_curve_difference(0.0, 100.0, scaling_factor=400, lifetime_deduction=25)
        # Both are adjusted but by different amounts relative to their scaling
        self.assertGreater(dedicated, 0)
        self.assertGreater(ad_read, 0)
        self.assertNotAlmostEqual(dedicated, ad_read, places=6)


if __name__ == '__main__':
    unittest.main()