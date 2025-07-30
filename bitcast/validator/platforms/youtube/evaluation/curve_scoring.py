"""
Curve-based scoring calculation functions for YouTube video evaluation.

This module provides functions for calculating video scores using a diminishing 
returns curve to prevent linear scaling exploitation while fairly rewarding growth.
"""

import math
from typing import Optional

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
        
        bt.logging.debug(f"Curve calculation: value={value:.4f}, sqrt={sqrt_value:.4f}, curve={curve_value:.6f}")
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
    
    difference = day2_curve - day1_curve
    
    bt.logging.debug(
        f"Curve difference: day1_avg={day1_avg:.4f} -> curve={day1_curve:.6f}, "
        f"day2_avg={day2_avg:.4f} -> curve={day2_curve:.6f}, "
        f"difference={difference:.6f}"
    )
    
    return difference


def validate_curve_calculation(value: float, expected_curve: Optional[float] = None) -> bool:
    """
    Validate curve calculation for testing and debugging purposes.
    
    Args:
        value (float): Input value to test
        expected_curve (Optional[float]): Expected curve result for validation
        
    Returns:
        bool: True if calculation is valid and matches expected result (if provided)
    """
    try:
        calculated = calculate_curve_value(value)
        
        # Basic validation
        if value <= 0 and calculated != 0:
            bt.logging.warning(f"Invalid curve calculation: value={value}, calculated={calculated}")
            return False
            
        if value > 0 and calculated <= 0:
            bt.logging.warning(f"Invalid curve calculation: positive value yielded non-positive result")
            return False
        
        # Expected value validation if provided
        if expected_curve is not None:
            tolerance = 1e-10
            if abs(calculated - expected_curve) > tolerance:
                bt.logging.warning(
                    f"Curve calculation mismatch: expected={expected_curve}, calculated={calculated}"
                )
                return False
                
        return True
        
    except Exception as e:
        bt.logging.error(f"Error validating curve calculation: {e}")
        return False