"""
Scoring logic for YouTube video evaluation.

This module contains functions for calculating video scores based on analytics data.
"""

from datetime import datetime, timedelta
from typing import Optional

import bittensor as bt

from bitcast.validator.platforms.youtube.api.video import get_video_analytics
from bitcast.validator.platforms.youtube.config import get_youtube_metrics
from bitcast.validator.utils.config import ECO_MODE, YT_REWARD_DELAY, YT_ROLLING_WINDOW

from .curve_based_scoring import calculate_curve_based_score


def calculate_video_score(video_id, youtube_analytics_client, video_publish_date, 
                         existing_analytics, is_ypp_account: bool = True, 
                         channel_analytics: Optional[dict] = None):
    """
    Calculate the score for a video using curve-based scoring strategy.
    
    Args:
        video_id (str): Video ID to calculate score for
        youtube_analytics_client: YouTube Analytics API client
        video_publish_date (str): Video publish date in ISO format
        existing_analytics (dict): Existing analytics data
        is_ypp_account (bool): Whether this is a YPP account
        channel_analytics (Optional[dict]): Channel analytics for median cap calculation
        
    Returns:
        dict: Dictionary containing score, daily_analytics, scoring_method, and cap info
    """
    # Use video publish date as query start date if provided, otherwise use default
    try:
        publish_datetime = datetime.strptime(video_publish_date, '%Y-%m-%dT%H:%M:%SZ')
        query_start_date = publish_datetime.strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        bt.logging.warning(f"Failed to parse video publish date: {video_publish_date}, using default")
        query_start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    
    start_date = (datetime.now() - timedelta(days=YT_REWARD_DELAY + YT_ROLLING_WINDOW - 1)).strftime('%Y-%m-%d')
    end_date = (datetime.now() - timedelta(days=YT_REWARD_DELAY)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')

    # Get daily metrics from config, excluding revenue metrics for Non-YPP accounts
    metric_dims = get_youtube_metrics(eco_mode=ECO_MODE, for_daily=True, is_ypp_account=is_ypp_account)    
    analytics_result = get_video_analytics(
        youtube_analytics_client, 
        video_id, 
        query_start_date,
        today, 
        metric_dims=metric_dims
    )
    
    daily_analytics = sorted(analytics_result.get("day_metrics", {}).values(), key=lambda x: x.get("day", ""))
    
    # Calculate score using curve-based scoring with integrated median capping
    return calculate_curve_based_score(daily_analytics, start_date, end_date, is_ypp_account, channel_analytics) 