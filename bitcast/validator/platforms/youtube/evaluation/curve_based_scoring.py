"""
Curve-based scoring implementation for YouTube video evaluation.

This module implements the core curve-based scoring algorithm that replaces
the simple average-based scoring with a diminishing returns curve approach.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import bittensor as bt

from bitcast.validator.utils.config import (
    YT_ROLLING_WINDOW,
    YT_REWARD_DELAY,
    YT_NON_YPP_REVENUE_MULTIPLIER
)
from .curve_scoring import calculate_curve_difference
from .data_processing import get_period_averages


def calculate_curve_based_score(
    daily_analytics: List[Dict[str, Any]], 
    start_date: str, 
    end_date: str,
    is_ypp_account: bool, 
    channel_analytics: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Calculate video score using curve-based methodology.
    
    This is the main entry point that replaces calculate_dual_score(). It implements
    the curve-based scoring algorithm using:
    1. Two consecutive 7-day periods for comparison
    2. Cumulative revenue/minutes watched calculations
    3. Curve formula application to both periods
    4. Score = difference between curve values
    
    Args:
        daily_analytics: List of daily analytics data
        start_date: Start date for scoring window (not used in curve calculation)
        end_date: End date for scoring window (not used in curve calculation)
        is_ypp_account: Whether this is a YPP account
        channel_analytics: Optional channel analytics for median capping
        
    Returns:
        Dict with score, daily_analytics, scoring_method, and debugging info
        
    Examples:
        >>> result = calculate_curve_based_score(
        ...     daily_data, "2023-01-01", "2023-01-07", 
        ...     is_ypp_account=True, channel_analytics=channel_data
        ... )
        >>> score = result["score"]
        >>> method = result["scoring_method"]
    """
    try:
        # Calculate the two periods needed for curve scoring
        # day 1 avg = (T - YT_REWARD_DELAY - YT_ROLLING_WINDOW - 1) to (T - YT_REWARD_DELAY - 1)
        # day 2 avg = (T - YT_REWARD_DELAY - YT_ROLLING_WINDOW) to (T - YT_REWARD_DELAY)
        
        today = datetime.now()
        
        # Day 1 period (earlier period): 7 days ending YT_REWARD_DELAY days ago
        # day 1 avg = (T - YT_REWARD_DELAY - YT_ROLLING_WINDOW + 1) to (T - YT_REWARD_DELAY)
        day1_start_offset = YT_REWARD_DELAY + YT_ROLLING_WINDOW - 1  # T - 3 - 7 + 1 = T - 9
        day1_end_offset = YT_REWARD_DELAY  # T - 3
        day1_start = (today - timedelta(days=day1_start_offset)).strftime('%Y-%m-%d')
        day1_end = (today - timedelta(days=day1_end_offset)).strftime('%Y-%m-%d')
        
        # Day 2 period (later period): 7 days ending (YT_REWARD_DELAY - 1) days ago
        # day 2 avg = (T - YT_REWARD_DELAY - YT_ROLLING_WINDOW + 2) to (T - YT_REWARD_DELAY + 1)
        day2_start_offset = YT_REWARD_DELAY + YT_ROLLING_WINDOW - 2  # T - 3 - 7 + 2 = T - 8
        day2_end_offset = YT_REWARD_DELAY - 1  # T - 3 + 1 = T - 2
        day2_start = (today - timedelta(days=day2_start_offset)).strftime('%Y-%m-%d')
        day2_end = (today - timedelta(days=day2_end_offset)).strftime('%Y-%m-%d')
        
        bt.logging.debug(
            f"Curve scoring periods: Day1={day1_start} to {day1_end}, "
            f"Day2={day2_start} to {day2_end}"
        )
        
        if is_ypp_account:
            return _calculate_ypp_curve_score(
                daily_analytics, day1_start, day1_end, day2_start, day2_end,
                channel_analytics
            )
        else:
            return _calculate_non_ypp_curve_score(
                daily_analytics, day1_start, day1_end, day2_start, day2_end,
                channel_analytics
            )
            
    except Exception as e:
        bt.logging.error(f"Error in curve-based scoring calculation: {e}")
        return {
            "score": 0.0,
            "daily_analytics": daily_analytics,
            "scoring_method": "curve_error_fallback",
            "error": str(e)
        }


def _calculate_ypp_curve_score(
    daily_analytics: List[Dict[str, Any]],
    day1_start: str,
    day1_end: str, 
    day2_start: str,
    day2_end: str,
    channel_analytics: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Calculate curve-based score for YPP accounts using actual revenue data.
    
    Args:
        daily_analytics: Daily analytics data
        day1_start: Start date for period 1
        day1_end: End date for period 1
        day2_start: Start date for period 2
        day2_end: End date for period 2
        channel_analytics: Channel analytics for median capping
        
    Returns:
        Scoring result dictionary
    """
    try:
        # Get period averages with median capping applied
        day1_avg, day2_avg = get_period_averages(
            daily_analytics,
            "estimatedRedPartnerRevenue",
            day1_start, day1_end,
            day2_start, day2_end,
            YT_ROLLING_WINDOW,
            channel_analytics=channel_analytics,
            is_ypp_account=True
        )
        
        # Calculate curve difference (this is the score)
        score = calculate_curve_difference(day1_avg, day2_avg)
        
        bt.logging.info(
            f"YPP curve score: day1_avg={day1_avg:.4f}, day2_avg={day2_avg:.4f}, "
            f"score_difference={score:.6f}"
        )
        
        return {
            "score": score,
            "daily_analytics": daily_analytics,
            "scoring_method": "ypp_curve_based",
            "day1_average": day1_avg,
            "day2_average": day2_avg,
            "median_capping_applied": channel_analytics is not None,
            "periods": {
                "day1": f"{day1_start} to {day1_end}",
                "day2": f"{day2_start} to {day2_end}"
            }
        }
        
    except Exception as e:
        bt.logging.error(f"Error calculating YPP curve score: {e}")
        return {
            "score": 0.0,
            "daily_analytics": daily_analytics,
            "scoring_method": "ypp_curve_error",
            "error": str(e)
        }


def _calculate_non_ypp_curve_score(
    daily_analytics: List[Dict[str, Any]],
    day1_start: str,
    day1_end: str,
    day2_start: str, 
    day2_end: str,
    channel_analytics: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Calculate curve-based score for Non-YPP accounts using estimated revenue.
    
    Uses hardcoded multiplier (YT_NON_YPP_REVENUE_MULTIPLIER) to convert 
    minutes watched to estimated revenue before curve calculations.
    
    Args:
        daily_analytics: Daily analytics data
        day1_start: Start date for period 1
        day1_end: End date for period 1
        day2_start: Start date for period 2
        day2_end: End date for period 2
        channel_analytics: Channel analytics for median capping
        
    Returns:
        Scoring result dictionary
    """
    try:
        # Get period averages for minutes watched with median capping applied
        day1_minutes_avg, day2_minutes_avg = get_period_averages(
            daily_analytics,
            "estimatedMinutesWatched",
            day1_start, day1_end,
            day2_start, day2_end,
            YT_ROLLING_WINDOW,
            channel_analytics=channel_analytics,
            is_ypp_account=False
        )
        
        # Convert minutes watched to estimated revenue using hardcoded multiplier
        day1_revenue_avg = day1_minutes_avg * YT_NON_YPP_REVENUE_MULTIPLIER
        day2_revenue_avg = day2_minutes_avg * YT_NON_YPP_REVENUE_MULTIPLIER
        
        # Calculate curve difference (this is the score)
        score = calculate_curve_difference(day1_revenue_avg, day2_revenue_avg)
        
        bt.logging.info(
            f"Non-YPP curve score: day1_minutes={day1_minutes_avg:.0f}, "
            f"day2_minutes={day2_minutes_avg:.0f}, "
            f"day1_revenue_est={day1_revenue_avg:.6f}, "
            f"day2_revenue_est={day2_revenue_avg:.6f}, "
            f"score_difference={score:.6f}"
        )
        
        return {
            "score": score,
            "daily_analytics": daily_analytics,
            "scoring_method": "non_ypp_curve_based",
            "day1_minutes_average": day1_minutes_avg,
            "day2_minutes_average": day2_minutes_avg,
            "day1_revenue_estimate": day1_revenue_avg,
            "day2_revenue_estimate": day2_revenue_avg,
            "revenue_multiplier": YT_NON_YPP_REVENUE_MULTIPLIER,
            "median_capping_applied": channel_analytics is not None,
            "periods": {
                "day1": f"{day1_start} to {day1_end}",
                "day2": f"{day2_start} to {day2_end}"
            }
        }
        
    except Exception as e:
        bt.logging.error(f"Error calculating Non-YPP curve score: {e}")
        return {
            "score": 0.0,
            "daily_analytics": daily_analytics,
            "scoring_method": "non_ypp_curve_error",
            "error": str(e)
        }


