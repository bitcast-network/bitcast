"""
Dual scoring implementation for YPP and Non-YPP accounts.

This module provides functions for calculating video scores using different
methods based on account type and available data.
"""

from typing import Any, Dict, List, Optional

import bittensor as bt

from bitcast.validator.platforms.youtube.cache.ratio_cache import (
    MinutesToRevenueRatioCache,
)
from bitcast.validator.utils.config import YT_ROLLING_WINDOW


def _apply_median_cap(total_value: float, median_cap: Optional[float], metric_name: str) -> tuple[float, bool, float]:
    """Apply median cap and return (capped_value, applied_cap, original_value)."""
    original_value = total_value
    applied_cap = False
    
    if median_cap is not None:
        cap_limit = median_cap * YT_ROLLING_WINDOW
        if total_value > cap_limit:
            total_value = cap_limit
            applied_cap = True
            bt.logging.info(f"Applied {metric_name} cap: original={original_value:.0f}, capped={total_value:.0f}, median_cap={median_cap:.0f}")
    
    return total_value, applied_cap, original_value


def calculate_dual_score(daily_analytics: List[Dict[str, Any]], start_date: str, end_date: str, 
                        is_ypp_account: bool, cached_ratio: Optional[float] = None,
                        median_revenue_cap: Optional[float] = None,
                        median_minutes_watched_cap: Optional[float] = None) -> Dict[str, Any]:
    """
    Calculate video score using either YPP (revenue) or Non-YPP (predicted) scoring.
    
    Args:
        daily_analytics: List of daily analytics data
        start_date: Start date for scoring window  
        end_date: End date for scoring window
        is_ypp_account: Whether this is a YPP account
        cached_ratio: Global cached minutes-watched-to-revenue ratio for Non-YPP accounts
        median_revenue_cap: Optional median daily revenue cap (YPP only)
        median_minutes_watched_cap: Optional median daily minutes watched cap (Non-YPP only)
        
    Returns:
        Dict with score, daily_analytics, scoring_method, and cap debugging info
    """
    if is_ypp_account:
        # YPP: Use actual revenue data with optional median capping
        total_revenue = sum(
            item.get('estimatedRedPartnerRevenue', 0) 
            for item in daily_analytics 
            if start_date <= item.get('day', '') <= end_date
        )
        
        # Apply median revenue cap if provided (anti-exploitation measure)
        total_revenue, applied_cap, original_revenue = _apply_median_cap(total_revenue, median_revenue_cap, "revenue")
        
        score = total_revenue / YT_ROLLING_WINDOW
        scoring_method = "ypp"
        
        return {
            "score": score,
            "daily_analytics": daily_analytics,
            "scoring_method": scoring_method,
            "applied_cap": applied_cap,
            "original_revenue": original_revenue,
            "capped_revenue": total_revenue,
            "median_revenue_cap": median_revenue_cap
        }
        
    else:
        # Non-YPP: Use predicted revenue with optional minutes watched capping or fallback to 0
        if cached_ratio is not None:
            total_minutes_watched = sum(
                item.get('estimatedMinutesWatched', 0) 
                for item in daily_analytics 
                if start_date <= item.get('day', '') <= end_date
            )
            
            # Apply median minutes watched cap if provided (anti-exploitation measure)
            total_minutes_watched, applied_cap, original_minutes_watched = _apply_median_cap(total_minutes_watched, median_minutes_watched_cap, "minutes_watched")
            
            predicted_revenue = total_minutes_watched * cached_ratio
            score = predicted_revenue / YT_ROLLING_WINDOW
            scoring_method = "non_ypp_predicted"
            
            return {
                "score": score,
                "daily_analytics": daily_analytics,
                "scoring_method": scoring_method,
                "applied_cap": applied_cap,
                "original_minutes_watched": original_minutes_watched,
                "capped_minutes_watched": total_minutes_watched,
                "median_minutes_watched_cap": median_minutes_watched_cap,
                "predicted_revenue": predicted_revenue
            }
        else:
            # First cycle fallback
            score = 0.0
            scoring_method = "non_ypp_fallback"
            
            return {
                "score": score,
                "daily_analytics": daily_analytics,
                "scoring_method": scoring_method,
                "applied_cap": False,
                "original_minutes_watched": None,
                "capped_minutes_watched": None,
                "median_minutes_watched_cap": None,
                "predicted_revenue": None
            }


def calculate_global_ratio(evaluation_results) -> Optional[float]:
    """
    Calculate global minutes-watched-to-revenue ratio from all YPP videos in evaluation results.
    
    Args:
        evaluation_results: EvaluationResultCollection with all miner results
        
    Returns:
        Global ratio or None if insufficient data
    """
    total_minutes_watched = 0
    total_revenue = 0
    
    for uid, result in evaluation_results.results.items():
        if result.platform != "youtube":
            continue
            
        for account_id, account_result in result.account_results.items():
            # Check if this is a YPP account - FIXED: YPP is directly in platform_data.analytics
            analytics = account_result.platform_data.get("analytics", {})
            is_ypp = analytics.get("ypp", False)
            
            if not is_ypp:
                continue
                
            # Extract minutes watched and revenue from YPP videos
            for video_id, video_data in account_result.videos.items():
                if "daily_analytics" in video_data and video_data.get("score", 0) > 0:
                    # FIXED: Use video-level analytics instead of daily_analytics
                    video_analytics = video_data.get("analytics", {})
                    
                    video_minutes_watched = video_analytics.get("estimatedMinutesWatched", 0)
                    video_revenue = video_analytics.get("estimatedRedPartnerRevenue", 0)
                    
                    if video_minutes_watched > 0 and video_revenue >= 0:
                        total_minutes_watched += video_minutes_watched
                        total_revenue += video_revenue

    if total_minutes_watched == 0:
        bt.logging.warning("No valid YPP videos with minutes watched and revenue data found")
        return None
        
    ratio = total_revenue / total_minutes_watched
    bt.logging.info(f"Calculated global ratio: total_minutes_watched={total_minutes_watched}, total_revenue={total_revenue}, ratio={ratio}")
    return ratio


def update_cached_ratio(evaluation_results) -> None:
    """
    Calculate and cache new global ratio from evaluation results.
    
    Args:
        evaluation_results: EvaluationResultCollection with all miner results
    """
    ratio = calculate_global_ratio(evaluation_results)
    
    if ratio is not None:
        cache = MinutesToRevenueRatioCache()
        cache.store_ratio(ratio)
        bt.logging.info(f"Updated cached global ratio: {ratio}")
    else:
        bt.logging.warning("Could not calculate ratio - keeping existing cached value")


def get_cached_ratio() -> Optional[float]:
    """
    Get the current cached global ratio.
    
    Returns:
        Cached ratio or None if not available
    """
    cache = MinutesToRevenueRatioCache()
    return cache.get_current_ratio() 