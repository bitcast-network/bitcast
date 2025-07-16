"""
Scoring logic for YouTube video evaluation.

This module contains functions for calculating video scores based on analytics data.
"""

import bittensor as bt
from datetime import datetime, timedelta

from bitcast.validator.socials.youtube.api.video import get_video_analytics
from bitcast.validator.utils.config import (
    YT_REWARD_DELAY,
    YT_ROLLING_WINDOW,
    ECO_MODE
)
from bitcast.validator.socials.youtube.config import get_youtube_metrics


def calculate_video_score(video_id, youtube_analytics_client, video_publish_date, existing_analytics):
    """
    Calculate the score for a video based on analytics data.
    
    Args:
        video_id (str): Video ID to calculate score for
        youtube_analytics_client: YouTube Analytics API client
        video_publish_date (str): Video publish date in ISO format
        existing_analytics (dict): Existing analytics data
        
    Returns:
        dict: Dictionary containing score and daily_analytics
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

    # Get daily metrics from config
    metric_dims = get_youtube_metrics(eco_mode=ECO_MODE, for_daily=True)    
    analytics_result = get_video_analytics(
        youtube_analytics_client, 
        video_id, 
        query_start_date,
        today, 
        metric_dims=metric_dims
    )
    
    daily_analytics = sorted(analytics_result.get("day_metrics", {}).values(), key=lambda x: x.get("day", ""))
    
    # Calculate total revenue over the scoring time frame
    total_revenue = sum(
        item.get('estimatedRedPartnerRevenue', 0) 
        for item in daily_analytics 
        if start_date <= item.get('day', '') <= end_date
    )
    
    # Calculate daily average revenue by dividing by YT_ROLLING_WINDOW regardless of actual days present
    score = total_revenue / YT_ROLLING_WINDOW

    # Log the total_revenue and score values
    bt.logging.info(f"Video {video_id}: total_revenue={total_revenue}, score={score}")

    return {
        "score": score,
        "daily_analytics": daily_analytics
    } 