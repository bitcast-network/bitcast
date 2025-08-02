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


def _has_zero_total_revenue(daily_analytics: List[Dict[str, Any]]) -> tuple[bool, float]:
    """
    Check if total revenue across all daily analytics equals zero.
    
    Args:
        daily_analytics: List of daily analytics data
        
    Returns:
        tuple: (is_zero_revenue, total_revenue)
        
    Examples:
        >>> analytics = [
        ...     {"estimatedRedPartnerRevenue": 0.0},
        ...     {"estimatedRedPartnerRevenue": 0.0}
        ... ]
        >>> is_zero, total = _has_zero_total_revenue(analytics)
        >>> is_zero
        True
        >>> total
        0.0
    """
    total_revenue = sum(
        item.get("estimatedRedPartnerRevenue", 0.0) 
        for item in daily_analytics
    )
    return total_revenue == 0.0, total_revenue


def calculate_curve_based_score(
    daily_analytics: List[Dict[str, Any]], 
    start_date: str, 
    end_date: str,
    is_ypp_account: bool, 
    channel_analytics: Optional[Dict[str, Any]] = None,
    video_id: Optional[str] = None,
    min_stake: bool = False
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
        video_id: Optional video ID for logging identification
        min_stake: Whether the miner meets minimum stake requirements
        
    Returns:
        Dict with score, daily_analytics, scoring_method, and debugging info
        
    Examples:
        >>> result = calculate_curve_based_score(
        ...     daily_data, "2023-01-01", "2023-01-07", 
        ...     is_ypp_account=True, channel_analytics=channel_data, video_id="abc123"
        ... )
        >>> score = result["score"]
        >>> method = result["scoring_method"]
    """
    video_info = f" [Video: {video_id}]" if video_id else ""
    bt.logging.info(f"=== CURVE-BASED SCORING START{video_info} ===")
    bt.logging.info(f"Input: YPP={is_ypp_account}, analytics_entries={len(daily_analytics)}, has_channel_analytics={channel_analytics is not None}")
    
    try:
        # Step 1: Calculate the two periods needed for curve scoring
        bt.logging.info("Step 1: Calculating scoring periods")
        bt.logging.info(f"Config: ROLLING_WINDOW={YT_ROLLING_WINDOW}, REWARD_DELAY={YT_REWARD_DELAY}")
        
        today = datetime.now()
        bt.logging.info(f"Current date: {today.strftime('%Y-%m-%d')}")
        
        # Day 1 period (earlier period): 7 days ending (YT_REWARD_DELAY + 1) days ago
        day1_start_offset = YT_REWARD_DELAY + 1 + YT_ROLLING_WINDOW - 1  # T - 4 - 7 + 1 = T - 10
        day1_end_offset = YT_REWARD_DELAY + 1  # T - 4
        day1_start = (today - timedelta(days=day1_start_offset)).strftime('%Y-%m-%d')
        day1_end = (today - timedelta(days=day1_end_offset)).strftime('%Y-%m-%d')
        
        # Day 2 period (later period): 7 days ending YT_REWARD_DELAY days ago  
        day2_start_offset = YT_REWARD_DELAY + YT_ROLLING_WINDOW - 1  # T - 3 - 7 + 1 = T - 9
        day2_end_offset = YT_REWARD_DELAY  # T - 3
        day2_start = (today - timedelta(days=day2_start_offset)).strftime('%Y-%m-%d')
        day2_end = (today - timedelta(days=day2_end_offset)).strftime('%Y-%m-%d')
        
        bt.logging.info(f"Period 1 (Day1): {day1_start} to {day1_end} (offset T-{day1_start_offset} to T-{day1_end_offset})")
        bt.logging.info(f"Period 2 (Day2): {day2_start} to {day2_end} (offset T-{day2_start_offset} to T-{day2_end_offset})")
        
        # Step 2: Route to appropriate scoring method
        if is_ypp_account:
            # Check for zero revenue scenario in YPP accounts
            is_zero_revenue, total_revenue = _has_zero_total_revenue(daily_analytics)
            
            if is_zero_revenue:
                if min_stake:
                    bt.logging.info(f"YPP account with zero revenue (total: {total_revenue}) and min_stake=True - routing to Non-YPP scoring")
                    result = _calculate_non_ypp_curve_score(
                        daily_analytics, day1_start, day1_end, day2_start, day2_end,
                        channel_analytics
                    )
                    result["scoring_method"] = "ypp_zero_revenue"
                else:
                    bt.logging.info(f"YPP account with zero revenue (total: {total_revenue}) but min_stake=False - scoring as 0")
                    return {
                        "score": 0.0,
                        "scoring_method": "ypp_zero_revenue_no_stake",
                        "daily_analytics": daily_analytics,
                        "zero_revenue_detected": True,
                        "min_stake_met": False
                    }
            else:
                bt.logging.info("Step 2: Routing to YPP curve scoring (using estimatedRedPartnerRevenue)")
                result = _calculate_ypp_curve_score(
                    daily_analytics, day1_start, day1_end, day2_start, day2_end,
                    channel_analytics
                )
        else:
            bt.logging.info(f"Step 2: Routing to Non-YPP curve scoring (using estimatedMinutesWatched * {YT_NON_YPP_REVENUE_MULTIPLIER})")
            result = _calculate_non_ypp_curve_score(
                daily_analytics, day1_start, day1_end, day2_start, day2_end,
                channel_analytics
            )
        
        bt.logging.info(f"=== CURVE-BASED SCORING COMPLETE{video_info}: Final score={result.get('score', 0):.6f} ===")
        return result
            
    except Exception as e:
        bt.logging.error(f"=== CURVE-BASED SCORING ERROR{video_info}: {e} ===")
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
    bt.logging.info("--- YPP Curve Scoring ---")
    try:
        # Step 3: Get period averages with median capping applied
        bt.logging.info(f"Step 3a: Processing data for metric 'estimatedRedPartnerRevenue'")
        bt.logging.info(f"Step 3b: Will apply median capping: {channel_analytics is not None}")
        
        day1_avg, day2_avg = get_period_averages(
            daily_analytics,
            "estimatedRedPartnerRevenue",
            day1_start, day1_end,
            day2_start, day2_end,
            YT_ROLLING_WINDOW,
            channel_analytics=channel_analytics,
            is_ypp_account=True
        )
        
        bt.logging.info(f"Step 3c: Data processing complete - Day1 avg: {day1_avg:.6f}, Day2 avg: {day2_avg:.6f}")
        
        # Step 4: Calculate curve difference (this is the score)
        bt.logging.info(f"Step 4a: Applying curve formula to averages")
        bt.logging.info(f"Step 4b: Formula: SQRT(day2_avg)/(1+0.1*SQRT(day2_avg)) - SQRT(day1_avg)/(1+0.1*SQRT(day1_avg))")
        
        score = calculate_curve_difference(day1_avg, day2_avg)
        
        bt.logging.info(f"Step 4c: Curve calculation complete - Final score: {score:.6f}")
        bt.logging.info(f"YPP Summary: day1_avg={day1_avg:.6f} -> day2_avg={day2_avg:.6f} = score_diff={score:.6f}")
        
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
        bt.logging.error(f"YPP Curve Scoring Error: {e}")
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
    bt.logging.info("--- Non-YPP Curve Scoring ---")
    try:
        # Step 3: Get period averages for minutes watched with median capping applied
        bt.logging.info(f"Step 3a: Processing data for metric 'estimatedMinutesWatched'")
        bt.logging.info(f"Step 3b: Will apply median capping: {channel_analytics is not None}")
        
        day1_minutes_avg, day2_minutes_avg = get_period_averages(
            daily_analytics,
            "estimatedMinutesWatched",
            day1_start, day1_end,
            day2_start, day2_end,
            YT_ROLLING_WINDOW,
            channel_analytics=channel_analytics,
            is_ypp_account=False
        )
        
        bt.logging.info(f"Step 3c: Minutes data processing complete - Day1 avg: {day1_minutes_avg:.2f}, Day2 avg: {day2_minutes_avg:.2f}")
        
        # Step 4: Convert minutes watched to estimated revenue using hardcoded multiplier
        bt.logging.info(f"Step 4a: Converting minutes to revenue using multiplier {YT_NON_YPP_REVENUE_MULTIPLIER}")
        
        day1_revenue_avg = day1_minutes_avg * YT_NON_YPP_REVENUE_MULTIPLIER
        day2_revenue_avg = day2_minutes_avg * YT_NON_YPP_REVENUE_MULTIPLIER
        
        bt.logging.info(f"Step 4b: Revenue conversion complete - Day1: {day1_minutes_avg:.2f}min -> ${day1_revenue_avg:.6f}")
        bt.logging.info(f"Step 4c: Revenue conversion complete - Day2: {day2_minutes_avg:.2f}min -> ${day2_revenue_avg:.6f}")
        
        # Step 5: Calculate curve difference (this is the score)
        bt.logging.info(f"Step 5a: Applying curve formula to revenue estimates")
        bt.logging.info(f"Step 5b: Formula: SQRT(day2_revenue)/(1+0.1*SQRT(day2_revenue)) - SQRT(day1_revenue)/(1+0.1*SQRT(day1_revenue))")
        
        score = calculate_curve_difference(day1_revenue_avg, day2_revenue_avg)
        
        bt.logging.info(f"Step 5c: Curve calculation complete - Final score: {score:.6f}")
        bt.logging.info(
            f"Non-YPP Summary: {day1_minutes_avg:.0f}min(${day1_revenue_avg:.6f}) -> "
            f"{day2_minutes_avg:.0f}min(${day2_revenue_avg:.6f}) = score_diff={score:.6f}"
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
        bt.logging.error(f"Non-YPP Curve Scoring Error: {e}")
        return {
            "score": 0.0,
            "daily_analytics": daily_analytics,
            "scoring_method": "non_ypp_curve_error",
            "error": str(e)
        }


