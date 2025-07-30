"""
Data processing utilities for curve-based video scoring.

This module provides functions for processing YouTube analytics data to support
curve-based scoring calculations, including filling missing dates, calculating
cumulative totals, and computing rolling averages.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

import bittensor as bt


def fill_missing_dates(
    daily_analytics: List[Dict[str, Any]], 
    start_date: str, 
    end_date: str
) -> List[Dict[str, Any]]:
    """
    Fill missing dates in daily analytics data with zero values.
    
    Ensures that every date in the specified range has an entry, filling gaps
    with zeros for all metrics. This is critical for accurate cumulative and
    rolling average calculations.
    
    Args:
        daily_analytics: List of daily analytics dictionaries
        start_date: Start date in 'YYYY-MM-DD' format
        end_date: End date in 'YYYY-MM-DD' format
        
    Returns:
        List of daily analytics with all dates filled
        
    Examples:
        >>> analytics = [{"day": "2023-01-01", "estimatedRedPartnerRevenue": 5.0}]
        >>> filled = fill_missing_dates(analytics, "2023-01-01", "2023-01-03")
        >>> len(filled)
        3
        >>> filled[1]["day"]
        "2023-01-02"
        >>> filled[1]["estimatedRedPartnerRevenue"]
        0.0
    """
    try:
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    except ValueError as e:
        bt.logging.error(f"Invalid date format: {e}")
        return daily_analytics
    
    # Create a mapping of existing data by date
    existing_data = {item.get("day", ""): item for item in daily_analytics if item.get("day")}
    
    # Determine what metrics exist in the data
    sample_metrics = set()
    for item in daily_analytics:
        for key in item.keys():
            if key != "day":
                sample_metrics.add(key)
    
    # Generate complete date range
    filled_analytics = []
    current_dt = start_dt
    
    while current_dt <= end_dt:
        current_date = current_dt.strftime('%Y-%m-%d')
        
        if current_date in existing_data:
            # Use existing data
            filled_analytics.append(existing_data[current_date])
        else:
            # Create zero-filled entry
            zero_entry = {"day": current_date}
            for metric in sample_metrics:
                zero_entry[metric] = 0.0
            filled_analytics.append(zero_entry)
        
        current_dt += timedelta(days=1)
    
    bt.logging.debug(f"Filled missing dates: {len(daily_analytics)} -> {len(filled_analytics)} entries")
    return filled_analytics


def calculate_cumulative_totals(
    daily_analytics: List[Dict[str, Any]], 
    metric_key: str
) -> List[Dict[str, Any]]:
    """
    Calculate cumulative totals for a specific metric across all days.
    
    Adds a new field with cumulative values, preserving all original data.
    Essential for curve-based scoring which uses cumulative revenue/minutes watched.
    
    Args:
        daily_analytics: List of daily analytics (should be sorted by date)
        metric_key: The metric to calculate cumulative totals for
        
    Returns:
        List with added cumulative total field
        
    Examples:
        >>> analytics = [
        ...     {"day": "2023-01-01", "estimatedRedPartnerRevenue": 5.0},
        ...     {"day": "2023-01-02", "estimatedRedPartnerRevenue": 3.0}
        ... ]
        >>> result = calculate_cumulative_totals(analytics, "estimatedRedPartnerRevenue")
        >>> result[0]["cumulative_estimatedRedPartnerRevenue"]
        5.0
        >>> result[1]["cumulative_estimatedRedPartnerRevenue"]
        8.0
    """
    if not daily_analytics:
        return []
    
    cumulative_field = f"cumulative_{metric_key}"
    running_total = 0.0
    
    result = []
    for item in daily_analytics:
        # Create a copy to avoid modifying original data
        new_item = item.copy()
        
        # Add current value to running total
        current_value = item.get(metric_key, 0.0)
        if isinstance(current_value, (int, float)):
            running_total += current_value
        else:
            bt.logging.warning(f"Non-numeric value for {metric_key}: {current_value}")
        
        new_item[cumulative_field] = running_total
        result.append(new_item)
    
    bt.logging.debug(f"Calculated cumulative totals for {metric_key}: final total = {running_total}")
    return result


def calculate_rolling_average(
    data: List[Dict[str, Any]], 
    window_size: int, 
    value_key: str
) -> List[float]:
    """
    Calculate rolling averages for a specific metric over a sliding window.
    
    Computes the average value over a rolling window for each position in the data.
    Critical for the curve-based scoring which uses 7-day rolling averages.
    
    Args:
        data: List of data dictionaries (should be sorted by date)
        window_size: Size of the rolling window (e.g., 7 for weekly)
        value_key: Key for the value to average
        
    Returns:
        List of rolling averages (one per data point)
        
    Examples:
        >>> data = [
        ...     {"cumulative_revenue": 10.0},
        ...     {"cumulative_revenue": 15.0}, 
        ...     {"cumulative_revenue": 21.0}
        ... ]
        >>> averages = calculate_rolling_average(data, 2, "cumulative_revenue")
        >>> averages[1]  # Average of 10.0 and 15.0
        12.5
        >>> averages[2]  # Average of 15.0 and 21.0  
        18.0
    """
    if not data or window_size <= 0:
        return []
    
    averages = []
    
    for i in range(len(data)):
        # Determine window bounds
        start_idx = max(0, i - window_size + 1)
        end_idx = i + 1
        
        # Extract values for the window
        window_values = []
        for j in range(start_idx, end_idx):
            value = data[j].get(value_key, 0.0)
            if isinstance(value, (int, float)):
                window_values.append(value)
            else:
                bt.logging.warning(f"Non-numeric value in rolling average: {value}")
                window_values.append(0.0)
        
        # Calculate average
        if window_values:
            average = sum(window_values) / len(window_values)
        else:
            average = 0.0
        
        averages.append(average)
    
    bt.logging.debug(f"Calculated {len(averages)} rolling averages with window size {window_size}")
    return averages


def extract_date_range(
    daily_analytics: List[Dict[str, Any]], 
    start_date: str, 
    end_date: str
) -> List[Dict[str, Any]]:
    """
    Extract data for a specific date range from daily analytics.
    
    Filters the analytics data to include only entries within the specified
    date range. Essential for extracting the specific periods needed for
    curve-based scoring calculations.
    
    Args:
        daily_analytics: List of daily analytics
        start_date: Start date in 'YYYY-MM-DD' format (inclusive)
        end_date: End date in 'YYYY-MM-DD' format (inclusive)
        
    Returns:
        List containing only data within the specified range
        
    Examples:
        >>> analytics = [
        ...     {"day": "2023-01-01", "revenue": 5.0},
        ...     {"day": "2023-01-02", "revenue": 3.0},
        ...     {"day": "2023-01-03", "revenue": 2.0}
        ... ]
        >>> subset = extract_date_range(analytics, "2023-01-01", "2023-01-02")
        >>> len(subset)
        2
        >>> subset[0]["day"]
        "2023-01-01"
    """
    if not daily_analytics:
        return []
    
    try:
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    except ValueError as e:
        bt.logging.error(f"Invalid date format in extract_date_range: {e}")
        return []
    
    filtered_data = []
    
    for item in daily_analytics:
        day_str = item.get("day", "")
        if not day_str:
            continue
            
        try:
            day_dt = datetime.strptime(day_str, '%Y-%m-%d')
            if start_dt <= day_dt <= end_dt:
                filtered_data.append(item)
        except ValueError:
            bt.logging.warning(f"Invalid date format in data: {day_str}")
            continue
    
    bt.logging.debug(f"Extracted {len(filtered_data)} entries from date range {start_date} to {end_date}")
    return filtered_data


def get_period_averages(
    daily_analytics: List[Dict[str, Any]],
    metric_key: str,
    day1_start: str,
    day1_end: str, 
    day2_start: str,
    day2_end: str,
    window_size: int,
    channel_analytics: Optional[Dict[str, Any]] = None,
    is_ypp_account: bool = True
) -> tuple[float, float]:
    """
    Calculate rolling averages for two specific periods used in curve scoring.
    
    This is a convenience function that combines multiple data processing steps
    to calculate the two rolling averages needed for curve-based scoring:
    - Day 1 average: (T - YT_REWARD_DELAY - YT_ROLLING_WINDOW - 1) to (T - YT_REWARD_DELAY - 1)
    - Day 2 average: (T - YT_REWARD_DELAY - YT_ROLLING_WINDOW) to (T - YT_REWARD_DELAY)
    
    Includes median capping for anti-exploitation if channel analytics are provided.
    
    Args:
        daily_analytics: Raw daily analytics data
        metric_key: Metric to process ("estimatedRedPartnerRevenue" or "estimatedMinutesWatched")
        day1_start: Start date for period 1
        day1_end: End date for period 1
        day2_start: Start date for period 2  
        day2_end: End date for period 2
        window_size: Rolling window size (typically YT_ROLLING_WINDOW = 7)
        channel_analytics: Channel analytics for median capping (optional)
        is_ypp_account: Whether this is a YPP account (affects capping metric)
        
    Returns:
        Tuple of (day1_average, day2_average)
        
    Examples:
        >>> analytics = [...]  # Daily analytics data
        >>> day1_avg, day2_avg = get_period_averages(
        ...     analytics, "estimatedRedPartnerRevenue",
        ...     "2023-01-01", "2023-01-07", 
        ...     "2023-01-02", "2023-01-08", 
        ...     7, channel_analytics, True
        ... )
    """
    try:
        # Determine the full date range needed
        all_dates = [day1_start, day1_end, day2_start, day2_end]
        date_objs = [datetime.strptime(d, '%Y-%m-%d') for d in all_dates]
        overall_start = min(date_objs).strftime('%Y-%m-%d')
        overall_end = max(date_objs).strftime('%Y-%m-%d')
        
        # Fill missing dates
        filled_data = fill_missing_dates(daily_analytics, overall_start, overall_end)
        
        # Apply median capping if channel analytics are provided
        if channel_analytics is not None:
            # Import here to avoid circular dependency
            from .median_capping import apply_median_caps_to_analytics
            filled_data = apply_median_caps_to_analytics(filled_data, channel_analytics, is_ypp_account)
        
        # Calculate cumulative totals after capping
        cumulative_data = calculate_cumulative_totals(filled_data, metric_key)
        
        # Extract period 1 data and calculate rolling average
        period1_data = extract_date_range(cumulative_data, day1_start, day1_end)
        if period1_data:
            period1_averages = calculate_rolling_average(period1_data, window_size, f"cumulative_{metric_key}")
            day1_average = period1_averages[-1] if period1_averages else 0.0  # Use last average in period
        else:
            day1_average = 0.0
        
        # Extract period 2 data and calculate rolling average
        period2_data = extract_date_range(cumulative_data, day2_start, day2_end)
        if period2_data:
            period2_averages = calculate_rolling_average(period2_data, window_size, f"cumulative_{metric_key}")
            day2_average = period2_averages[-1] if period2_averages else 0.0  # Use last average in period
        else:
            day2_average = 0.0
        
        bt.logging.debug(f"Period averages: day1={day1_average:.4f}, day2={day2_average:.4f}")
        return day1_average, day2_average
        
    except Exception as e:
        bt.logging.error(f"Error calculating period averages: {e}")
        return 0.0, 0.0