"""
YouTube analytics metrics and configuration.

This file contains configurations for different types of YouTube analytics metrics
used for evaluating and scoring videos.

Metric format: (metric_name, dimensions, filter, maxResults, sort)
- metric_name: The YouTube Analytics API metric
- dimensions: Comma-separated dimensions for grouping
- filter: Optional filter to apply to this specific metric (None if no filter)
- maxResults: Optional maximum number of results to return (None for default)
- sort: Optional sort parameter for ordering results (None for default)

Example usage:
    # Basic usage with additional filter
    metrics = get_youtube_metrics(eco_mode=False, for_daily=True)
    analytics = get_video_analytics(
        client, video_id, 
        metric_dims=metrics,
        filters="country==US"  # Only get data for US
    )
    
    # Multiple filters
    analytics = get_video_analytics(
        client, video_id,
        metric_dims=metrics, 
        filters="country==US;deviceType==MOBILE"
    )
"""

# Core metrics for general analytics
CORE_METRICS = {
    "averageViewPercentage": ("averageViewPercentage", "", None, None, None),
    "estimatedMinutesWatched": ("estimatedMinutesWatched", "", None, None, None),
    "trafficSourceMinutes": ("estimatedMinutesWatched", "insightTrafficSourceType", None, None, None),
    "insightTrafficSourceDetail_EXT_URL": ("estimatedMinutesWatched", "insightTrafficSourceDetail", "insightTrafficSourceType==EXT_URL", 10, "-estimatedMinutesWatched"),
}

# Additional metrics for full analytics (when not in ECO_MODE)
ADDITIONAL_METRICS = {
    "views": ("views", "", None, None, None),
    "comments": ("comments", "", None, None, None),
    "likes": ("likes", "", None, None, None),
    "dislikes": ("dislikes", "", None, None, None),
    "shares": ("shares", "", None, None, None),
    "averageViewDuration": ("averageViewDuration", "", None, None, None),
    "countryMinutes": ("estimatedMinutesWatched", "country", None, None, "-estimatedMinutesWatched"),
    "ageGroupViewerPercentage": ("viewerPercentage", "ageGroup,gender", None, None, None),
    "elapsedVideoTimeRatioAudienceWatchRatio": ("audienceWatchRatio", "elapsedVideoTimeRatio", None, None, None),
    "sharingServiceShares": ("shares", "sharingService", None, None, "-shares"),
    "relativeRetentionPerformance": ("relativeRetentionPerformance", "elapsedVideoTimeRatio", None, None, None),
    "creatorContentTypeMinutes": ("estimatedMinutesWatched", "creatorContentType", None, None, None),
    "subscribedStatusMinutes": ("averageViewPercentage", "subscribedStatus", None, None, None),
}

# Slow API calls that we only use in non eco mode on videos of interest
ADVANCED_METRICS = {
    "insightTrafficSourceDetail_YT_SEARCH": ("estimatedMinutesWatched", "insightTrafficSourceDetail", "insightTrafficSourceType==YT_SEARCH", 10, "-estimatedMinutesWatched"),
    "insightTrafficSourceDetail_RELATED_VIDEO": ("estimatedMinutesWatched", "insightTrafficSourceDetail", "insightTrafficSourceType==RELATED_VIDEO", 10, "-estimatedMinutesWatched"),
    "insightTrafficSourceDetail_YT_CHANNEL": ("estimatedMinutesWatched", "insightTrafficSourceDetail", "insightTrafficSourceType==YT_CHANNEL", 10, "-estimatedMinutesWatched"),
}

# Core daily metrics - all metrics with day dimension
CORE_DAILY_METRICS = {
    "estimatedMinutesWatched": ("estimatedMinutesWatched", "day", None, None, "day"),
    "trafficSourceMinutes": ("estimatedMinutesWatched", "insightTrafficSourceType,day", None, None, "day"),
}

# Additional daily metrics for ECO_MODE
ADDITIONAL_DAILY_METRICS = {
    "views": ("views", "day", None, None, "day"),
    "comments": ("comments", "day", None, None, "day"),
    "likes": ("likes", "day", None, None, "day"),
    "shares": ("shares", "day", None, None, "day"),
    "averageViewDuration": ("averageViewDuration", "day", None, None, "day"),
    "AverageViewPercentage": ("averageViewPercentage", "day", None, None, "day"),
    "deviceTypeMinutes": ("estimatedMinutesWatched", "deviceType,day", None, None, "day"),
    "operatingSystemMinutes": ("estimatedMinutesWatched", "operatingSystem,day", None, None, "day"),
    "creatorContentTypeMinutes": ("estimatedMinutesWatched", "creatorContentType,day", None, None, "day"),
    "playbackLocationMinutes": ("estimatedMinutesWatched", "insightPlaybackLocationType,day", None, None, "day"),
    "avgViewPercentageByTrafficSource": ("averageViewPercentage", "insightTrafficSourceType,day", None, None, "day"),
    "liveOrOnDemandMinutes": ("estimatedMinutesWatched", "liveOrOnDemand,day", None, None, "day"),
    "youtubeProductMinutes": ("estimatedMinutesWatched", "youtubeProduct,day", None, None, "day"),
    "engagedViews": ("engagedViews", "day", None, None, "day"),
    "videosAddedToPlaylists": ("videosAddedToPlaylists", "day", None, None, "day"),
    "estimatedAdRevenue": ("estimatedAdRevenue", "day", None, None, "day"),
    "estimatedRedPartnerRevenue": ("estimatedRedPartnerRevenue", "day", None, None, "day"),
    "cpm": ("cpm", "day", None, None, "day"),
}

def get_youtube_metrics(eco_mode, for_daily=False):
    """
    Get the appropriate YouTube metrics configuration based on context.
    
    Args:
        for_daily: Whether to get daily metrics (True) or general metrics (False)
        eco_mode: Whether to use ECO_MODE metrics (reduced set)
        
    Returns:
        Dictionary of metric configurations in format: {key: (metric, dimensions, filter, maxResults, sort)}
        
    Example:
        metrics = get_youtube_metrics(eco_mode=False, for_daily=True)
        analytics = get_video_analytics(
            client, video_id,
            metric_dims=metrics,
            filters="country==US;deviceType==MOBILE"
        )
    """
    if for_daily and eco_mode:
        return CORE_DAILY_METRICS
    elif for_daily and not eco_mode:
        return {**CORE_DAILY_METRICS, **ADDITIONAL_DAILY_METRICS}
    elif not for_daily and eco_mode:
        return {**CORE_METRICS}
    else:
        return {**CORE_METRICS, **ADDITIONAL_METRICS}

# Channel metrics for channel-level analytics
CHANNEL_CORE_METRICS = {
    "averageViewPercentage": ("averageViewPercentage", "", None, None, None),
    "estimatedMinutesWatched": ("estimatedMinutesWatched", "", None, None, None),
    "cpm": ("cpm", "", None, None, None),
}

# Additional channel metrics for non-ECO mode
CHANNEL_ADDITIONAL_METRICS = {
    "comments": ("comments", "", None, None, None),
    "likes": ("likes", "", None, None, None),
    "shares": ("shares", "", None, None, None),
    "subscribersGained": ("subscribersGained", "day", None, None, "day"),
    "subscribersLost": ("subscribersLost", "", None, None, None),
    "monetizedPlaybacks": ("monetizedPlaybacks", "", None, None, None),
    "estimatedAdRevenue": ("estimatedAdRevenue", "day", None, None, "day"),
    "trafficSourceViews": ("views", "insightTrafficSourceType", None, None, None),
    "trafficSourceMinutes": ("estimatedMinutesWatched", "insightTrafficSourceType", None, None, None),
    "countryViews": ("views", "country", None, None, None),
    "countryMinutes": ("estimatedMinutesWatched", "country", None, None, None),
}

# Revenue metrics that commonly fail for accounts without monetization
REVENUE_METRICS = {"estimatedAdRevenue", "cpm", "estimatedRedPartnerRevenue", "monetizedPlaybacks"}

def get_channel_metrics(eco_mode=False):
    """
    Get the appropriate channel metrics configuration based on ECO_MODE.
    
    Args:
        eco_mode: Whether to use ECO_MODE metrics (reduced set)
        
    Returns:
        Dictionary of metric configurations in format: {key: (metric, dimensions, filter, maxResults, sort)}
        
    Example:
        metrics = get_channel_metrics(eco_mode=True)
        analytics = get_channel_analytics(client, start_date, end_date, metric_dims=metrics)
    """
    if eco_mode:
        return CHANNEL_CORE_METRICS
    else:
        return {**CHANNEL_CORE_METRICS, **CHANNEL_ADDITIONAL_METRICS}

def get_advanced_metrics():
    """
    Get only the advanced YouTube metrics configuration.
    """
    return ADVANCED_METRICS