"""
Curve-based scoring calculation functions for YouTube video evaluation.

This module provides functions for calculating video scores using a diminishing 
returns curve to prevent linear scaling exploitation while fairly rewarding growth.
"""

import math

import bittensor as bt

from bitcast.validator.utils.config import YT_CURVE_DAMPENING_FACTOR


def calculate_curve_value(value: float) -> float:
    """
    Calculate the curve value using the diminishing returns formula.
    
    Formula: SQRT(value) / (1 + dampening_factor * SQRT(value))
    
    This creates a curve where:
    - Small values have near-linear growth
    - Large values experience diminishing returns
    - Prevents exploitation through linear scaling
    
    Args:
        value (float): The input value (revenue, estimated revenue, etc.)
        
    Returns:
        float: The calculated curve value
        
    Examples:
        >>> calculate_curve_value(0.0)
        0.0
        >>> calculate_curve_value(100.0)
        0.9090909090909091
        >>> calculate_curve_value(10000.0)
        0.9090909090909091
    """
    # Handle edge cases
    if value <= 0 or not math.isfinite(value):
        return 0.0
    
    try:
        sqrt_value = math.sqrt(value)
        
        # Additional safety check for infinite sqrt result
        if not math.isfinite(sqrt_value):
            bt.logging.error(f"Non-finite sqrt result for value {value}")
            return 0.0
            
        curve_value = sqrt_value / (1 + YT_CURVE_DAMPENING_FACTOR * sqrt_value)
        
        # Final safety check for the result
        if not math.isfinite(curve_value):
            bt.logging.error(f"Non-finite curve result for value {value}")
            return 0.0
        
        # Curve calculation completed
        return curve_value
        
    except (ValueError, ZeroDivisionError, OverflowError) as e:
        bt.logging.error(f"Error calculating curve value for {value}: {e}")
        return 0.0


def calculate_curve_difference(day1_avg: float, day2_avg: float) -> float:
    """
    Calculate the difference between two curve values representing scoring periods.
    
    This represents the "gain" along the curve between two consecutive 7-day periods,
    which becomes the video's score for the period.
    
    Args:
        day1_avg (float): Average value for the first period (T - YT_REWARD_DELAY - YT_ROLLING_WINDOW - 1) to (T - YT_REWARD_DELAY - 1)
        day2_avg (float): Average value for the second period (T - YT_REWARD_DELAY - YT_ROLLING_WINDOW) to (T - YT_REWARD_DELAY)
        
    Returns:
        float: The difference between the curve values (day2_curve - day1_curve)
        
    Examples:
        >>> calculate_curve_difference(0.0, 100.0)
        0.9090909090909091
        >>> calculate_curve_difference(100.0, 200.0)
        0.04132231404958677
        >>> calculate_curve_difference(200.0, 100.0)
        -0.04132231404958677
    """
    day1_curve = calculate_curve_value(day1_avg)
    day2_curve = calculate_curve_value(day2_avg)
    
    return day2_curve - day1_curve


def calculate_adjusted_curve_difference(
    day1_avg: float, day2_avg: float, scaling_factor: float, lifetime_deduction: float
) -> float:
    """
    Calculate curve difference with lifetime deduction threshold applied.
    
    Shifts the curve down by (lifetime_deduction / scaling_factor) and clamps
    at zero before differencing. This guarantees the lifetime sum of daily scores
    is reduced by exactly lifetime_deduction (in USD terms) via telescoping:
    
      sum(daily) = max(curve(final) - threshold, 0) * scaling * boost
                 = max(curve(final) * scaling - deduction, 0) * boost
    
    Args:
        day1_avg: Average value for the earlier period
        day2_avg: Average value for the later period
        scaling_factor: Brief-specific scaling factor (e.g. 1800 for dedicated)
        lifetime_deduction: USD amount to deduct from lifetime total (e.g. 100 for dedicated, 25 for ad-read)
        
    Returns:
        float: The adjusted curve difference
    """
    if scaling_factor <= 0 or lifetime_deduction <= 0:
        return calculate_curve_difference(day1_avg, day2_avg)

    threshold = lifetime_deduction / scaling_factor

    day1_curve = calculate_curve_value(day1_avg)
    day2_curve = calculate_curve_value(day2_avg)

    return max(day2_curve - threshold, 0) - max(day1_curve - threshold, 0)


