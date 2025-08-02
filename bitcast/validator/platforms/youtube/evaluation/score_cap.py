"""
Score capping.

This module provides functions for calculating median values from account-level
daily analytics data to implement scoring caps based on T-60 to T-30 day periods.
"""

from datetime import datetime, timedelta
import statistics
from typing import Any, Dict, Tuple

import bittensor as bt

from bitcast.validator.utils.config import (
    YT_SCORE_CAP_END_DAYS,
    YT_SCORE_CAP_START_DAYS,
)


def get_cap_period_dates() -> Tuple[str, str]:
    """
    Calculate the T-60 to T-30 day score cap period dates.
    
    Returns:
        Tuple of (start_date, end_date) in YYYY-MM-DD format for the score cap period
    """
    today = datetime.now().date()
    
    # T-60 to T-30 means 60 days ago to 30 days ago
    start_date = (today - timedelta(days=YT_SCORE_CAP_START_DAYS)).strftime('%Y-%m-%d')
    end_date = (today - timedelta(days=YT_SCORE_CAP_END_DAYS)).strftime('%Y-%m-%d')
    
    return start_date, end_date


def pad_missing_days_with_zeros(daily_analytics: Dict[str, float], start_date: str, end_date: str) -> Dict[str, float]:
    """
    Pad missing days in the analytics data with zero values.
    
    Args:
        daily_analytics: Dictionary of {date: value} from channel analytics
        start_date: Start date of the period (YYYY-MM-DD)
        end_date: End date of the period (YYYY-MM-DD)
        
    Returns:
        Dictionary with all days in the period, missing days filled with zeros
    """
    if not daily_analytics:
        daily_analytics = {}
    
    # Convert string dates to datetime objects
    start = datetime.strptime(start_date, '%Y-%m-%d').date()
    end = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Create complete date range
    padded_data = {}
    current_date = start
    
    while current_date <= end:
        date_str = current_date.strftime('%Y-%m-%d')
        # Use existing value or default to 0
        padded_data[date_str] = daily_analytics.get(date_str, 0.0)
        current_date += timedelta(days=1)
    
    return padded_data


def calculate_median_from_analytics(channel_analytics: Dict[str, Any], metric_key: str) -> float:
    """
    Calculate median daily values for a specific metric from channel analytics for the T-60 to T-30 period.
    
    Args:
        channel_analytics: Channel analytics dictionary from get_channel_analytics()
        metric_key: The metric key to extract ('estimatedRedPartnerRevenue', 'views', etc.)
        
    Returns:
        Median daily value for the specified metric over the score cap period
    """
    try:
        # Get the score cap period dates
        start_date, end_date = get_cap_period_dates()
        
        # Extract daily metric data
        daily_data = channel_analytics.get(metric_key, {})
        
        # Pad missing days with zeros as per BA guidance
        padded_data = pad_missing_days_with_zeros(daily_data, start_date, end_date)
        
        # Calculate median (include all values including zeros)
        values = list(padded_data.values())
        
        if not values:
            bt.logging.warning(f"No {metric_key} data found for median calculation, returning 0")
            return 0.0
        
        median_value = statistics.median(values)
        
        # Calculated median value for capping
        
        return float(median_value)
        
    except Exception as e:
        bt.logging.error(f"Error calculating {metric_key} median: {e}")
        return 0.0


 