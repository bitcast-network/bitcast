"""
Median capping implementation for curve-based video scoring.

This module provides functions for calculating and applying median caps to daily 
analytics data to prevent exploitation while maintaining fair scoring.
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


def calculate_median_cap_period(
    channel_analytics: Dict[str, Any], 
    start_days: int, 
    end_days: int,
    metric_key: str
) -> float:
    """
    Calculate median cap value for a specific time period.
    
    Uses the existing median calculation infrastructure but allows for 
    flexible period specification for curve-based scoring.
    
    Args:
        channel_analytics: Channel analytics dictionary
        start_days: Days ago to start the period (e.g., 60 for T-60)
        end_days: Days ago to end the period (e.g., 30 for T-30)
        metric_key: The metric to calculate median for
        
    Returns:
        Median daily value for the specified period and metric
        
    Examples:
        >>> cap = calculate_median_cap_period(analytics, 60, 30, "estimatedRedPartnerRevenue")
        >>> # Calculates median revenue for T-60 to T-30 period
    """
    try:
        today = datetime.now().date()
        start_date = (today - timedelta(days=start_days)).strftime('%Y-%m-%d')
        end_date = (today - timedelta(days=end_days)).strftime('%Y-%m-%d')
        
        # Extract daily metric data
        daily_data = channel_analytics.get(metric_key, {})
        
        # Filter data to the specified period
        period_data = {}
        for date_str, value in daily_data.items():
            if start_date <= date_str <= end_date:
                period_data[date_str] = value
        
        # Pad missing days with zeros (following BA guidance)
        from .score_cap import pad_missing_days_with_zeros
        padded_data = pad_missing_days_with_zeros(period_data, start_date, end_date)
        
        # Calculate median
        values = list(padded_data.values())
        if not values:
            bt.logging.warning(f"No {metric_key} data found for period {start_date} to {end_date}")
            return 0.0
        
        median_value = statistics.median(values)
        
        bt.logging.debug(
            f"Median cap calculation: metric={metric_key}, period={start_date} to {end_date}, "
            f"days={len(values)}, median={median_value:.4f}"
        )
        
        return float(median_value)
        
    except Exception as e:
        bt.logging.error(f"Error calculating median cap for {metric_key}: {e}")
        return 0.0


def apply_median_cap_to_daily_data(
    daily_data: List[Dict[str, Any]], 
    median_cap: float, 
    metric_key: str,
    cap_multiplier: int = 1
) -> List[Dict[str, Any]]:
    """
    Apply median cap to daily analytics data.
    
    Caps individual daily values at median_cap * cap_multiplier to prevent
    exploitation while preserving legitimate high-performance days.
    
    Args:
        daily_data: List of daily analytics dictionaries
        median_cap: Median value calculated from historical period
        metric_key: The metric to apply capping to
        cap_multiplier: Multiplier for the cap (default 1 = cap at median)
        
    Returns:
        List with capped values, original data preserved
        
    Examples:
        >>> capped = apply_median_cap_to_daily_data(
        ...     daily_analytics, 5.0, "estimatedRedPartnerRevenue", 2
        ... )
        >>> # Caps revenue at 2x median (10.0)
    """
    if not daily_data or median_cap <= 0:
        return daily_data
    
    cap_limit = median_cap * cap_multiplier
    capped_data = []
    capped_count = 0
    total_reduction = 0.0
    
    for item in daily_data:
        # Create a copy to avoid modifying original data
        new_item = item.copy()
        
        original_value = item.get(metric_key, 0.0)
        if isinstance(original_value, (int, float)) and original_value > cap_limit:
            new_item[metric_key] = cap_limit
            capped_count += 1
            total_reduction += original_value - cap_limit
            
            bt.logging.debug(
                f"Applied cap: date={item.get('day', 'unknown')}, "
                f"original={original_value:.4f}, capped={cap_limit:.4f}"
            )
        
        capped_data.append(new_item)
    
    if capped_count > 0:
        bt.logging.info(
            f"Applied {metric_key} median cap: {capped_count} days capped, "
            f"total reduction={total_reduction:.4f}, cap_limit={cap_limit:.4f}"
        )
    
    return capped_data


def get_median_cap_for_metric(
    channel_analytics: Optional[Dict[str, Any]], 
    metric_key: str,
    is_ypp_account: bool
) -> Optional[float]:
    """
    Get the appropriate median cap for a specific metric and account type.
    
    Determines the correct metric and calculates median cap using the standard
    T-60 to T-30 period for anti-exploitation measures.
    
    Args:
        channel_analytics: Channel analytics dictionary (can be None)
        metric_key: The video-level metric being capped
        is_ypp_account: Whether this is a YPP account
        
    Returns:
        Median cap value or None if cannot be calculated
        
    Examples:
        >>> cap = get_median_cap_for_metric(analytics, "estimatedRedPartnerRevenue", True)
        >>> # Returns median revenue cap for YPP account
    """
    if channel_analytics is None:
        bt.logging.debug("No channel analytics available for median cap calculation")
        return None
    
    try:
        # For curve-based scoring, we use the standard T-60 to T-30 period
        median_cap = calculate_median_cap_period(
            channel_analytics,
            YT_SCORE_CAP_START_DAYS,  # 60 days
            YT_SCORE_CAP_END_DAYS,    # 30 days
            metric_key
        )
        
        if median_cap > 0:
            account_type = "YPP" if is_ypp_account else "Non-YPP"
            bt.logging.debug(
                f"Calculated median cap for {account_type} {metric_key}: {median_cap:.4f}"
            )
            return median_cap
        else:
            bt.logging.warning(f"Zero median cap calculated for {metric_key}")
            return None
            
    except Exception as e:
        bt.logging.error(f"Error getting median cap for {metric_key}: {e}")
        return None


def apply_median_caps_to_analytics(
    daily_analytics: List[Dict[str, Any]],
    channel_analytics: Optional[Dict[str, Any]],
    is_ypp_account: bool
) -> List[Dict[str, Any]]:
    """
    Apply appropriate median caps to daily analytics based on account type.
    
    This is the main entry point for median capping in curve-based scoring.
    Applies caps to the relevant metrics before cumulative calculations.
    
    Args:
        daily_analytics: List of daily analytics data
        channel_analytics: Channel analytics for median calculation (can be None)
        is_ypp_account: Whether this is a YPP account
        
    Returns:
        Daily analytics with median caps applied
        
    Examples:
        >>> capped_analytics = apply_median_caps_to_analytics(
        ...     daily_data, channel_data, is_ypp=True
        ... )
        >>> # Applies revenue caps for YPP or minutes watched caps for Non-YPP
    """
    if not daily_analytics:
        return []
    
    if channel_analytics is None:
        bt.logging.debug("No channel analytics available, skipping median capping")
        return daily_analytics
    
    try:
        if is_ypp_account:
            # YPP accounts: cap estimated red partner revenue
            metric_key = "estimatedRedPartnerRevenue"
            median_cap = get_median_cap_for_metric(channel_analytics, metric_key, True)
            
            if median_cap is not None:
                return apply_median_cap_to_daily_data(daily_analytics, median_cap, metric_key)
            else:
                bt.logging.debug("No median cap available for YPP revenue, skipping capping")
                return daily_analytics
                
        else:
            # Non-YPP accounts: cap estimated minutes watched
            metric_key = "estimatedMinutesWatched"
            median_cap = get_median_cap_for_metric(channel_analytics, metric_key, False)
            
            if median_cap is not None:
                return apply_median_cap_to_daily_data(daily_analytics, median_cap, metric_key)
            else:
                bt.logging.debug("No median cap available for Non-YPP minutes watched, skipping capping")
                return daily_analytics
                
    except Exception as e:
        bt.logging.error(f"Error applying median caps: {e}")
        return daily_analytics


def validate_median_cap_application(
    original_data: List[Dict[str, Any]],
    capped_data: List[Dict[str, Any]], 
    metric_key: str,
    expected_cap: float
) -> bool:
    """
    Validate that median capping was applied correctly.
    
    Testing and debugging utility to ensure caps are working as expected.
    
    Args:
        original_data: Original daily analytics
        capped_data: Data after median capping
        metric_key: The metric that was capped
        expected_cap: The cap value that should have been applied
        
    Returns:
        True if capping was applied correctly
    """
    try:
        if len(original_data) != len(capped_data):
            bt.logging.error("Data length mismatch after capping")
            return False
        
        violations_found = False
        
        for i, (orig, capped) in enumerate(zip(original_data, capped_data)):
            orig_value = orig.get(metric_key, 0.0)
            capped_value = capped.get(metric_key, 0.0)
            
            # Check that capping was applied correctly
            if orig_value > expected_cap and capped_value != expected_cap:
                bt.logging.error(
                    f"Cap violation at index {i}: original={orig_value}, "
                    f"capped={capped_value}, expected_cap={expected_cap}"
                )
                violations_found = True
            
            # Check that values below cap weren't modified
            if orig_value <= expected_cap and orig_value != capped_value:
                bt.logging.error(
                    f"Unexpected modification at index {i}: original={orig_value}, "
                    f"capped={capped_value} (should be unchanged)"
                )
                violations_found = True
        
        return not violations_found
        
    except Exception as e:
        bt.logging.error(f"Error validating median cap application: {e}")
        return False