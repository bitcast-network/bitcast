"""
Tests for score cap functions.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from bitcast.validator.platforms.youtube.evaluation.score_cap import (
    get_cap_period_dates,
    pad_missing_days_with_zeros,
    calculate_median_from_analytics
)


class TestGetCapPeriodDates:
    """Test cases for get_cap_period_dates function."""
    
    def test_get_cap_period_dates_calculation(self):
        """Test that score cap period dates are calculated correctly."""
        with patch('bitcast.validator.platforms.youtube.evaluation.score_cap.datetime') as mock_datetime:
            # Mock today as 2024-01-15
            mock_today = datetime(2024, 1, 15).date()
            mock_datetime.now.return_value.date.return_value = mock_today
            
            start_date, end_date = get_cap_period_dates()
            
            # T-60 to T-30: 60 days ago to 30 days ago from 2024-01-15
            # 60 days ago: 2023-11-16, 30 days ago: 2023-12-16
            assert start_date == "2023-11-16"
            assert end_date == "2023-12-16"
    
    def test_get_cap_period_dates_returns_strings(self):
        """Test that function returns properly formatted date strings."""
        start_date, end_date = get_cap_period_dates()
        
        # Should be in YYYY-MM-DD format
        assert isinstance(start_date, str)
        assert isinstance(end_date, str)
        assert len(start_date) == 10
        assert len(end_date) == 10
        assert start_date.count('-') == 2
        assert end_date.count('-') == 2


class TestPadMissingDaysWithZeros:
    """Test cases for pad_missing_days_with_zeros function."""
    
    def test_pad_missing_days_empty_input(self):
        """Test padding when input analytics is empty."""
        result = pad_missing_days_with_zeros({}, "2024-01-01", "2024-01-03")
        
        expected = {
            "2024-01-01": 0.0,
            "2024-01-02": 0.0,
            "2024-01-03": 0.0
        }
        assert result == expected
    
    def test_pad_missing_days_partial_data(self):
        """Test padding when some days are missing."""
        analytics = {
            "2024-01-01": 10.0,
            "2024-01-03": 30.0
        }
        
        result = pad_missing_days_with_zeros(analytics, "2024-01-01", "2024-01-03")
        
        expected = {
            "2024-01-01": 10.0,
            "2024-01-02": 0.0,  # Padded
            "2024-01-03": 30.0
        }
        assert result == expected
    
    def test_pad_missing_days_complete_data(self):
        """Test when no padding is needed."""
        analytics = {
            "2024-01-01": 10.0,
            "2024-01-02": 20.0,
            "2024-01-03": 30.0
        }
        
        result = pad_missing_days_with_zeros(analytics, "2024-01-01", "2024-01-03")
        
        assert result == analytics
    
    def test_pad_missing_days_single_day(self):
        """Test padding for a single day period."""
        result = pad_missing_days_with_zeros({}, "2024-01-01", "2024-01-01")
        
        expected = {"2024-01-01": 0.0}
        assert result == expected
    
    def test_pad_missing_days_none_input(self):
        """Test handling of None input."""
        result = pad_missing_days_with_zeros(None, "2024-01-01", "2024-01-02")
        
        expected = {
            "2024-01-01": 0.0,
            "2024-01-02": 0.0
        }
        assert result == expected


class TestCalculateMedianFromAnalytics:
    """Test cases for the generic calculate_median_from_analytics function."""
    
    def test_calculate_median_basic_revenue(self):
        """Test basic median calculation with revenue data."""
        with patch('bitcast.validator.platforms.youtube.evaluation.score_cap.get_cap_period_dates') as mock_dates:
            mock_dates.return_value = ("2024-01-01", "2024-01-05")
            
            channel_analytics = {
                'estimatedRedPartnerRevenue': {
                    "2024-01-01": 10.0,
                    "2024-01-02": 20.0,
                    "2024-01-03": 30.0,
                    "2024-01-04": 40.0,
                    "2024-01-05": 50.0
                }
            }
            
            result = calculate_median_from_analytics(channel_analytics, 'estimatedRedPartnerRevenue')
            
            # Median of [10, 20, 30, 40, 50] = 30.0
            assert result == 30.0
    
    def test_calculate_median_basic_views(self):
        """Test basic median calculation with views data."""
        with patch('bitcast.validator.platforms.youtube.evaluation.score_cap.get_cap_period_dates') as mock_dates:
            mock_dates.return_value = ("2024-01-01", "2024-01-05")
            
            channel_analytics = {
                'views': {
                    "2024-01-01": 100,
                    "2024-01-02": 200,
                    "2024-01-03": 300,
                    "2024-01-04": 400,
                    "2024-01-05": 500
                }
            }
            
            result = calculate_median_from_analytics(channel_analytics, 'views')
            
            # Median of [100, 200, 300, 400, 500] = 300.0
            assert result == 300.0
    
    def test_calculate_median_with_zeros(self):
        """Test median calculation including zero values."""
        with patch('bitcast.validator.platforms.youtube.evaluation.score_cap.get_cap_period_dates') as mock_dates:
            mock_dates.return_value = ("2024-01-01", "2024-01-05")
            
            channel_analytics = {
                'estimatedRedPartnerRevenue': {
                    "2024-01-01": 0.0,
                    "2024-01-02": 10.0,
                    "2024-01-03": 0.0,
                    "2024-01-04": 20.0,
                    "2024-01-05": 0.0
                }
            }
            
            result = calculate_median_from_analytics(channel_analytics, 'estimatedRedPartnerRevenue')
            
            # Median of [0, 10, 0, 20, 0] = 0.0
            assert result == 0.0
    
    def test_calculate_median_missing_days(self):
        """Test median calculation with missing days (should be padded with zeros)."""
        with patch('bitcast.validator.platforms.youtube.evaluation.score_cap.get_cap_period_dates') as mock_dates:
            mock_dates.return_value = ("2024-01-01", "2024-01-05")
            
            channel_analytics = {
                'views': {
                    "2024-01-02": 200,
                    "2024-01-04": 400
                    # Missing 2024-01-01, 2024-01-03, 2024-01-05
                }
            }
            
            result = calculate_median_from_analytics(channel_analytics, 'views')
            
            # Should be padded to [0, 200, 0, 400, 0], median = 0.0
            assert result == 0.0
    
    def test_calculate_median_no_data(self):
        """Test median calculation when no metric data exists."""
        with patch('bitcast.validator.platforms.youtube.evaluation.score_cap.get_cap_period_dates') as mock_dates:
            mock_dates.return_value = ("2024-01-01", "2024-01-03")
            
            channel_analytics = {}
            
            result = calculate_median_from_analytics(channel_analytics, 'estimatedRedPartnerRevenue')
            
            # Should return 0.0 when no data
            assert result == 0.0
    
    def test_calculate_median_empty_metric_dict(self):
        """Test median calculation when metric dict is empty."""
        with patch('bitcast.validator.platforms.youtube.evaluation.score_cap.get_cap_period_dates') as mock_dates:
            mock_dates.return_value = ("2024-01-01", "2024-01-03")
            
            channel_analytics = {
                'views': {}
            }
            
            result = calculate_median_from_analytics(channel_analytics, 'views')
            
            # Should be padded to [0, 0, 0], median = 0.0
            assert result == 0.0
    
    def test_calculate_median_custom_metric(self):
        """Test median calculation with a custom metric."""
        with patch('bitcast.validator.platforms.youtube.evaluation.score_cap.get_cap_period_dates') as mock_dates:
            mock_dates.return_value = ("2024-01-01", "2024-01-03")
            
            channel_analytics = {
                'customMetric': {
                    "2024-01-01": 5.0,
                    "2024-01-02": 15.0,
                    "2024-01-03": 25.0
                }
            }
            
            result = calculate_median_from_analytics(channel_analytics, 'customMetric')
            
            # Median of [5, 15, 25] = 15.0
            assert result == 15.0


class TestGenericFunctionUsage:
    """Test cases for using the generic function with different metrics."""
    
    def test_calculate_revenue_median_direct(self):
        """Test using generic function directly for revenue calculations."""
        with patch('bitcast.validator.platforms.youtube.evaluation.score_cap.get_cap_period_dates') as mock_dates:
            mock_dates.return_value = ("2024-01-01", "2024-01-03")
            
            channel_analytics = {
                'estimatedRedPartnerRevenue': {
                    "2024-01-01": 10.0,
                    "2024-01-02": 20.0,
                    "2024-01-03": 30.0
                }
            }
            
            result = calculate_median_from_analytics(channel_analytics, 'estimatedRedPartnerRevenue')
            assert result == 20.0
    
    def test_calculate_views_median_direct(self):
        """Test using generic function directly for views calculations."""
        with patch('bitcast.validator.platforms.youtube.evaluation.score_cap.get_cap_period_dates') as mock_dates:
            mock_dates.return_value = ("2024-01-01", "2024-01-03")
            
            channel_analytics = {
                'views': {
                    "2024-01-01": 100,
                    "2024-01-02": 200,
                    "2024-01-03": 300
                }
            }
            
            result = calculate_median_from_analytics(channel_analytics, 'views')
            assert result == 200.0


class TestErrorHandling:
    """Test error handling in score cap functions."""
    
    def test_calculate_median_exception_handling(self):
        """Test that median calculation handles exceptions gracefully."""
        with patch('bitcast.validator.platforms.youtube.evaluation.score_cap.get_cap_period_dates') as mock_dates:
            mock_dates.side_effect = Exception("Date calculation error")
            
            result = calculate_median_from_analytics({}, 'estimatedRedPartnerRevenue')
            
            # Should return 0.0 on exception
            assert result == 0.0
    
    def test_generic_function_exception_handling(self):
        """Test that generic function handles exceptions gracefully for different metrics."""
        with patch('bitcast.validator.platforms.youtube.evaluation.score_cap.get_cap_period_dates') as mock_dates:
            mock_dates.side_effect = Exception("Date calculation error")
            
            # Test with different metrics
            revenue_result = calculate_median_from_analytics({}, 'estimatedRedPartnerRevenue')
            views_result = calculate_median_from_analytics({}, 'views')
            
            # Both should return 0.0 on exception
            assert revenue_result == 0.0
            assert views_result == 0.0


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_median_calculation_even_number_of_values(self):
        """Test median calculation with even number of values."""
        with patch('bitcast.validator.platforms.youtube.evaluation.score_cap.get_cap_period_dates') as mock_dates:
            mock_dates.return_value = ("2024-01-01", "2024-01-04")
            
            channel_analytics = {
                'estimatedRedPartnerRevenue': {
                    "2024-01-01": 10.0,
                    "2024-01-02": 20.0,
                    "2024-01-03": 30.0,
                    "2024-01-04": 40.0
                }
            }
            
            result = calculate_median_from_analytics(channel_analytics, 'estimatedRedPartnerRevenue')
            
            # Median of [10, 20, 30, 40] = (20 + 30) / 2 = 25.0
            assert result == 25.0
    
    def test_median_calculation_single_value(self):
        """Test median calculation with single value."""
        with patch('bitcast.validator.platforms.youtube.evaluation.score_cap.get_cap_period_dates') as mock_dates:
            mock_dates.return_value = ("2024-01-01", "2024-01-01")
            
            channel_analytics = {
                'views': {
                    "2024-01-01": 500
                }
            }
            
            result = calculate_median_from_analytics(channel_analytics, 'views')
            
            # Median of [500] = 500.0
            assert result == 500.0
    
    def test_median_calculation_large_numbers(self):
        """Test median calculation with large numbers."""
        with patch('bitcast.validator.platforms.youtube.evaluation.score_cap.get_cap_period_dates') as mock_dates:
            mock_dates.return_value = ("2024-01-01", "2024-01-03")
            
            channel_analytics = {
                'views': {
                    "2024-01-01": 1000000,
                    "2024-01-02": 2000000,
                    "2024-01-03": 3000000
                }
            }
            
            result = calculate_median_from_analytics(channel_analytics, 'views')
            
            assert result == 2000000.0 