"""
Proportional scaling implementation for curve-based video scoring.

This module provides functions for calculating and applying proportional scaling to daily 
analytics data based on 7-day averages to prevent exploitation while maintaining relative
distribution of daily values.
"""

from datetime import datetime, timedelta
import statistics
from typing import Any, Dict, List, Optional

import bittensor as bt

from bitcast.validator.utils.config import (
    YT_SCORE_CAP_START_DAYS,
    YT_SCORE_CAP_END_DAYS,
)
from .score_cap import calculate_median_from_analytics


def calculate_period_average(daily_data: List[Dict[str, Any]], metric_key: str) -> float:
    """
    Calculate the average daily value for a given period.
    
    Args:
        daily_data: List of daily analytics dictionaries for the period
        metric_key: The metric to calculate average for
        
    Returns:
        Average daily value for the specified metric
        
    Examples:
        >>> avg = calculate_period_average(period_data, "estimatedRedPartnerRevenue")
        >>> # Calculates average revenue for the period
    """
    if not daily_data:
        return 0.0
    
    values = [float(item.get(metric_key, 0.0)) for item in daily_data]
    return sum(values) / len(values) if values else 0.0


def calculate_scaling_factor(period_average: float, threshold: float) -> Optional[float]:
    """
    Calculate the scaling factor needed to bring period average to threshold.
    
    Args:
        period_average: Current average for the period
        threshold: Target threshold (median from historical data)
        
    Returns:
        Scaling factor (threshold / period_average) or None if no scaling needed
        
    Examples:
        >>> factor = calculate_scaling_factor(10.0, 5.0)
        >>> # Returns 0.5 (scale down by half)
        >>> factor = calculate_scaling_factor(3.0, 5.0)
        >>> # Returns None (no scaling needed)
    """
    # Handle edge cases per BA requirements
    if threshold < 0:
        bt.logging.warning(f"Negative threshold {threshold}, treating as 0")
        threshold = 0.0
    
    if threshold == 0.0:
        # Zero threshold, scaling all values to 0
        return 0.0
    
    if period_average <= threshold:
        # Period average within threshold, no scaling needed
        return None
    
    scaling_factor = threshold / period_average
    # Scaling factor calculated
    return scaling_factor


def apply_proportional_scaling(
    daily_data: List[Dict[str, Any]], 
    scaling_factor: float, 
    metric_key: str
) -> List[Dict[str, Any]]:
    """
    Apply proportional scaling to daily analytics data.
    
    Scales all daily values by the scaling factor while preserving relative
    distribution of values within the period.
    
    Args:
        daily_data: List of daily analytics dictionaries
        scaling_factor: Factor to scale values by
        metric_key: The metric to apply scaling to
        
    Returns:
        List with scaled values, original data preserved in copies
        
    Examples:
        >>> scaled = apply_proportional_scaling(
        ...     daily_data, 0.5, "estimatedRedPartnerRevenue"
        ... )
        >>> # Scales all revenue values by 50%
    """
    if not daily_data:
        return []
    
    scaled_data = []
    total_original = 0.0
    total_scaled = 0.0
    
    for item in daily_data:
        # Create a copy to avoid modifying original data
        new_item = item.copy()
        
        original_value = float(item.get(metric_key, 0.0))
        scaled_value = original_value * scaling_factor
        new_item[metric_key] = scaled_value
        
        total_original += original_value
        total_scaled += scaled_value
        
        # Scaled value for proportional adjustment
        
        scaled_data.append(new_item)
    
    bt.logging.info(
        f"Applied proportional scaling: metric={metric_key}, factor={scaling_factor:.4f}, "
        f"total_original={total_original:.4f}, total_scaled={total_scaled:.4f}"
    )
    
    return scaled_data


def get_median_threshold_for_metric(
    channel_analytics: Optional[Dict[str, Any]], 
    metric_key: str,
    is_ypp_account: bool
) -> Optional[float]:
    """
    Get the appropriate median threshold for a specific metric and account type.
    
    Uses the standard T-60 to T-30 period for anti-exploitation measures.
    
    Args:
        channel_analytics: Channel analytics dictionary (can be None)
        metric_key: The metric being evaluated
        is_ypp_account: Whether this is a YPP account
        
    Returns:
        Median threshold value or None if cannot be calculated
        
    Examples:
        >>> threshold = get_median_threshold_for_metric(analytics, "estimatedRedPartnerRevenue", True)
        >>> # Returns median revenue threshold for YPP account
    """
    if channel_analytics is None:
        # No channel analytics available for threshold calculation
        return None
    
    try:
        # Use existing median calculation infrastructure
        median_threshold = calculate_median_from_analytics(channel_analytics, metric_key)
        
        if median_threshold >= 0:
            # Calculated median threshold for proportional scaling
            return median_threshold
        else:
            bt.logging.warning(f"Negative median threshold calculated for {metric_key}: {median_threshold}")
            return 0.0
            
    except Exception as e:
        bt.logging.error(f"Error getting median threshold for {metric_key}: {e}")
        return None


def apply_proportional_scaling_to_period(
    period_data: List[Dict[str, Any]],
    channel_analytics: Optional[Dict[str, Any]],
    metric_key: str,
    is_ypp_account: bool
) -> List[Dict[str, Any]]:
    """
    Apply proportional scaling to a specific period's data based on its average.
    
    This is the main entry point for proportional scaling. It:
    1. Calculates the period average
    2. Gets the median threshold
    3. Determines if scaling is needed
    4. Applies proportional scaling if required
    
    Args:
        period_data: Daily analytics data for the specific period
        channel_analytics: Channel analytics for threshold calculation (can be None)
        metric_key: The metric to evaluate and scale
        is_ypp_account: Whether this is a YPP account
        
    Returns:
        Period data with proportional scaling applied if needed
        
    Examples:
        >>> scaled_period = apply_proportional_scaling_to_period(
        ...     period2_data, channel_data, "estimatedRedPartnerRevenue", True
        ... )
        >>> # Applies revenue scaling to period 2 for YPP account
    """
    if not period_data:
        # No period data provided for scaling
        return []
    
    if channel_analytics is None:
        # No channel analytics available, skipping proportional scaling
        return period_data
    
    try:
        # Calculate period average
        period_average = calculate_period_average(period_data, metric_key)
        
        # Get median threshold
        threshold = get_median_threshold_for_metric(channel_analytics, metric_key, is_ypp_account)
        
        if threshold is None:
            # No threshold available, skipping scaling
            return period_data
        
        # Calculate scaling factor
        scaling_factor = calculate_scaling_factor(period_average, threshold)
        
        if scaling_factor is None:
            # No scaling needed (average within threshold)
            return period_data
        
        # Apply proportional scaling
        return apply_proportional_scaling(period_data, scaling_factor, metric_key)
        
    except Exception as e:
        bt.logging.error(f"Error applying proportional scaling: {e}")
        return period_data


