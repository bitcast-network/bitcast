"""
Scoring logic for YouTube video evaluation.

This module contains functions for calculating video scores based on analytics data,
handling blacklisted traffic sources, and computing scorable minutes.
"""

import bittensor as bt
from datetime import datetime, timedelta

from bitcast.validator.socials.youtube import youtube_utils
from bitcast.validator.utils.config import (
    YT_REWARD_DELAY,
    YT_ROLLING_WINDOW,
    ECO_MODE
)
from bitcast.validator.socials.youtube.config import get_youtube_metrics
from bitcast.validator.utils.blacklist import get_blacklist_sources


def calculate_video_score(video_id, youtube_analytics_client, video_publish_date, existing_analytics):
    """
    Calculate the score for a video based on analytics data.
    
    Args:
        video_id (str): Video ID to calculate score for
        youtube_analytics_client: YouTube Analytics API client
        video_publish_date (str): Video publish date in ISO format
        existing_analytics (dict): Existing analytics data
        
    Returns:
        dict: Dictionary containing score, scorableHistoryMins, and daily_analytics
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
    analytics_result = youtube_utils.get_video_analytics(
        youtube_analytics_client, 
        video_id, 
        query_start_date,
        today, 
        metric_dims=metric_dims
    )
    
    daily_analytics = sorted(analytics_result.get("day_metrics", {}).values(), key=lambda x: x.get("day", ""))
    
    # Get blacklist sources once and reuse
    blacklisted_sources = get_blacklist_sources()
    
    # Get EXT_URL lifetime data from existing analytics and calculate the proportion
    ext_url_lifetime_data = existing_analytics.get("insightTrafficSourceDetail_EXT_URL", {})
    blacklisted_ext_url_proportion = calculate_blacklisted_ext_url_proportion(analytics_result, blacklisted_sources, ext_url_lifetime_data)

    # Compute scorableMins once per day
    for item in daily_analytics:
        item['scorableMins'] = get_scorable_minutes(item, blacklisted_sources, blacklisted_ext_url_proportion)

    # Calculate score and history using pre-computed scorableMins
    score = sum(item['scorableMins'] for item in daily_analytics if start_date <= item.get('day', '') <= end_date)
    scorableHistoryMins = sum(item['scorableMins'] for item in daily_analytics if item.get('day', '') <= end_date)

    return {
        "score": score,
        "scorableHistoryMins": scorableHistoryMins,
        "daily_analytics": daily_analytics
    }


def calculate_blacklisted_ext_url_proportion(analytics_result, blacklisted_sources, ext_url_lifetime_data):
    """
    Calculate what proportion of lifetime EXT_URL traffic comes from blacklisted sources.
    
    Args:
        analytics_result (dict): Analytics result containing traffic source data
        blacklisted_sources (list): List of blacklisted traffic sources
        ext_url_lifetime_data (dict): Lifetime external URL traffic data
        
    Returns:
        float: Proportion of EXT_URL traffic from blacklisted sources (0.0 to 1.0)
    """
    if not ext_url_lifetime_data:
        return 0.0

    # Sum up all EXT_URL minutes across all days from the daily traffic source data
    traffic_source_minutes = analytics_result.get("trafficSourceMinutes", {})
    total_ext_url_minutes = sum(
        minutes for key, minutes in traffic_source_minutes.items() 
        if key.startswith("EXT_URL|")
    )
    
    blacklisted_ext_url_minutes = sum(
        ext_url_lifetime_data.get(url, 0)
        for url in blacklisted_sources
    )
    
    blacklisted_ext_url_proportion = blacklisted_ext_url_minutes / total_ext_url_minutes if total_ext_url_minutes > 0 else 0.0

    if blacklisted_ext_url_proportion > 0:
        bt.logging.info(f"Blacklisted EXT_URL proportion: {blacklisted_ext_url_proportion}")
        
    return blacklisted_ext_url_proportion


def get_scorable_minutes(day_data, blacklisted_sources, blacklisted_ext_url_proportion):
    """
    Calculate minutes watched excluding blacklisted sources for a given day.
    
    Args:
        day_data (dict): Daily analytics data
        blacklisted_sources (list): List of blacklisted traffic sources
        blacklisted_ext_url_proportion (float): Proportion of EXT_URL traffic that's blacklisted
        
    Returns:
        float: Scorable minutes for the day (total minus blacklisted)
    """
    traffic_source_minutes = day_data.get('trafficSourceMinutes', {})
    
    if not traffic_source_minutes:
        return day_data.get('estimatedMinutesWatched', 0)
    
    total_minutes = sum(traffic_source_minutes.values())
    
    # Calculate minutes from blacklisted traffic sources (excluding EXT_URL for now)
    blacklisted_traffic_minutes = sum(
        traffic_source_minutes.get(source, 0) 
        for source in blacklisted_sources
        if source != "EXT_URL"  # Handle EXT_URL separately
    )
    
    # Handle EXT_URL traffic using the calculated proportion
    ext_url_daily_minutes = traffic_source_minutes.get('EXT_URL', 0)
    blacklisted_ext_url_daily_minutes = ext_url_daily_minutes * blacklisted_ext_url_proportion
    
    return max(0, total_minutes - blacklisted_traffic_minutes - blacklisted_ext_url_daily_minutes) 