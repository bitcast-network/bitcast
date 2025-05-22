"""
YouTube analytics metrics and configuration.

This file contains configurations for different types of YouTube analytics metrics
used for evaluating and scoring videos.
"""

# Core metrics for general analytics
CORE_METRICS = {
    "averageViewPercentage": ("averageViewPercentage", ""),
    "estimatedMinutesWatched": ("estimatedMinutesWatched", ""),
    "trafficSourceMinutes": ("estimatedMinutesWatched", "insightTrafficSourceType"),
}

# Additional metrics for full analytics (when not in ECO_MODE)
ADDITIONAL_METRICS = {
    "views": ("views", ""),
    "comments": ("comments", ""),
    "likes": ("likes", ""),
    "dislikes": ("dislikes", ""),
    "shares": ("shares", ""),
    "averageViewDuration": ("averageViewDuration", ""),
    "countryMinutes": ("estimatedMinutesWatched", "country"),
    "ageGroupViewerPercentage": ("viewerPercentage", "ageGroup,gender"),
    "elapsedVideoTimeRatioAudienceWatchRatio": ("audienceWatchRatio", "elapsedVideoTimeRatio"),
    "sharingServiceShares": ("shares", "sharingService")
}

# Core daily metrics - all metrics with day dimension
CORE_DAILY_METRICS = {
    "estimatedMinutesWatched": ("estimatedMinutesWatched", "day"),
}

# Additional daily metrics for ECO_MODE
ADDITIONAL_DAILY_METRICS = {
    "views": ("views", "day"),
    "comments": ("comments", "day"),
    "likes": ("likes", "day"),
    "shares": ("shares", "day"),
    "averageViewDuration": ("averageViewDuration", "day"),
    "AverageViewPercentage": ("averageViewPercentage", "day"),
    "trafficSourceMinutes": ("estimatedMinutesWatched", "insightTrafficSourceType,day"),
    "deviceTypeMinutes": ("estimatedMinutesWatched", "deviceType,day"),
    "operatingSystemMinutes": ("estimatedMinutesWatched", "operatingSystem,day"),
    "creatorContentTypeMinutes": ("estimatedMinutesWatched", "creatorContentType,day"),
    "playbackLocationMinutes": ("estimatedMinutesWatched", "insightPlaybackLocationType,day"),
    "avgViewPercentageByTrafficSource": ("averageViewPercentage", "insightTrafficSourceType,day"),
    "liveOrOnDemandMinutes": ("estimatedMinutesWatched", "liveOrOnDemand,day"),
    "youtubeProductMinutes": ("estimatedMinutesWatched", "youtubeProduct,day"),
}

def get_youtube_metrics(eco_mode, for_daily=False):
    """
    Get the appropriate YouTube metrics configuration based on context.
    
    Args:
        for_daily: Whether to get daily metrics (True) or general metrics (False)
        eco_mode: Whether to use ECO_MODE metrics (reduced set)
        
    Returns:
        Dictionary of metric dimensions for YouTube API calls
    """
    if for_daily and eco_mode:
        return CORE_DAILY_METRICS
    elif for_daily and not eco_mode:
        return {**CORE_DAILY_METRICS, **ADDITIONAL_DAILY_METRICS}
    elif not for_daily and eco_mode:
        return {**CORE_METRICS}
    else:
        return {**CORE_METRICS, **ADDITIONAL_METRICS}