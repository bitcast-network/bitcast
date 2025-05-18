import bittensor as bt
import requests
import time
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from bitcast.validator.utils.config import TRANSCRIPT_MAX_RETRY
import httpx
import hashlib
import asyncio
from tenacity import retry, stop_after_attempt, wait_fixed, RetryError
import os
import json
import re

# Global list to track which videos have already been scored
# This list is shared between youtube_scoring.py and youtube_evaluation.py
scored_video_ids = []

# Retry configuration for YouTube API calls
YT_API_RETRY_CONFIG = {
    'stop': stop_after_attempt(3),
    'wait': wait_fixed(0.5),
    'reraise': True
}

def reset_scored_videos():
    """Reset the global scored_video_ids list.
    
    This function is used by other modules to clear the list of scored videos.
    """
    global scored_video_ids
    scored_video_ids = []
    bt.logging.info(f"Reset scored_video_ids list")

def is_video_already_scored(video_id):
    """Check if a video has already been scored by another hotkey."""
    if video_id in scored_video_ids:
        bt.logging.info(f"Video {video_id} already scored by another hotkey")
        return True
    return False

def mark_video_as_scored(video_id):
    """Mark a video as scored to prevent duplicate processing."""
    scored_video_ids.append(video_id)

# ============================================================================
# Channel Analytics Functions
# ============================================================================

@retry(**YT_API_RETRY_CONFIG)
def get_channel_data(youtube_data_client, discrete_mode=False):
    """Get basic channel information."""
    account_info = youtube_data_client.channels().list(
        part="snippet,contentDetails,statistics",
        mine=True
    ).execute()

    channel_id = account_info['items'][0]['id']
    if discrete_mode:
        bitcast_channel_id = "bitcast_" + hashlib.sha256(channel_id.encode()).hexdigest()[:8]
    else:
        bitcast_channel_id = channel_id

    channel_info = {
        "title": account_info['items'][0]['snippet']['title'],
        "id": channel_id,
        "bitcastChannelId": bitcast_channel_id,
        "channel_start": account_info['items'][0]['snippet']['publishedAt'],
        "viewCount": account_info['items'][0]['statistics']['viewCount'],
        "subCount": account_info['items'][0]['statistics']['subscriberCount'],
        "videoCount": account_info['items'][0]['statistics']['videoCount'],
        "url": f"https://www.youtube.com/channel/{channel_id}"
    }

    return channel_info

@retry(**YT_API_RETRY_CONFIG)
def get_channel_analytics(youtube_analytics_client, start_date, end_date=None, dimensions=""):
    """Get comprehensive channel analytics including traffic sources."""
    if end_date is None:
        end_date = datetime.today().strftime('%Y-%m-%d')
        
    # Define metrics in a consistent order
    metrics_list = "views,comments,likes,dislikes,shares,averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost,estimatedMinutesWatched"
    
    analytics_response = youtube_analytics_client.reports().query(
        ids="channel==MINE",
        startDate=start_date,
        endDate=end_date,
        dimensions=dimensions,
        metrics=metrics_list
        ).execute()

    if not analytics_response.get("rows"):
        raise Exception("No channel analytics data found.")

    # Define metric names in the same order as the metrics_list
    metric_names = [
        "views", "comments", "likes", "dislikes", "shares", 
        "averageViewDuration", "averageViewPercentage", 
        "subscribersGained", "subscribersLost", "estimatedMinutesWatched"
    ]

    if dimensions:
        # Handle the case where dimensions are present
        analytics_info = []
        for row in analytics_response.get("rows", []):
            dimension_values = row[:len(dimensions.split(','))]
            metrics = dict(zip(metric_names, row[len(dimension_values):]))
            for i, dimension in enumerate(dimensions.split(',')):
                metrics[dimension] = dimension_values[i]
            analytics_info.append(metrics)
    else:
        # Handle the case where no dimensions are present
        analytics_data = analytics_response["rows"][0]
        analytics_info = dict(zip(metric_names, analytics_data))

    # Get traffic source data for views
    traffic_source_views = get_traffic_source_views_analytics(youtube_analytics_client, start_date, end_date)
    # Get traffic source data for minutes watched
    traffic_source_minutes = get_traffic_source_minutes_analytics(youtube_analytics_client, start_date, end_date)
    # Get country data for views
    country_views = get_country_views_analytics(youtube_analytics_client, start_date, end_date)
    # Get country data for minutes watched
    country_minutes = get_country_minutes_analytics(youtube_analytics_client, start_date, end_date)
    
    # Get subscribers gained including 30 days prior if dimensions is "day"
    if dimensions == "day":
        past_date = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=30)).strftime('%Y-%m-%d')
    else:
        past_date = start_date
    subscribers_gained = get_subscribers_gained_analytics(youtube_analytics_client, past_date, end_date)
    
    if isinstance(analytics_info, dict):
        analytics_info["trafficSourceViews"] = traffic_source_views
        analytics_info["trafficSourceMinutes"] = traffic_source_minutes
        analytics_info["countryViews"] = country_views
        analytics_info["countryMinutes"] = country_minutes
        analytics_info["subscribersGained"] = subscribers_gained
    else:
        for entry in analytics_info:
            entry["trafficSourceViews"] = traffic_source_views
            entry["trafficSourceMinutes"] = traffic_source_minutes
            entry["countryViews"] = country_views
            entry["countryMinutes"] = country_minutes
            entry["subscribersGained"] = subscribers_gained

    return analytics_info

@retry(**YT_API_RETRY_CONFIG)
def get_traffic_source_views_analytics(youtube_analytics_client, start_date, end_date):
    """Get traffic source analytics for views."""
    try:
        traffic_response = youtube_analytics_client.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            dimensions="insightTrafficSourceType",
            metrics="views"
        ).execute()

        if not traffic_response.get("rows"):
            return {}

        traffic_sources = {}
        for row in traffic_response.get("rows", []):
            source_type = row[0]
            views = row[1]
            traffic_sources[source_type] = views

        return traffic_sources
    except Exception as e:
        bt.logging.warning(f"Error getting traffic source views analytics: {_format_error(e)}")
        return {}

@retry(**YT_API_RETRY_CONFIG)
def get_traffic_source_minutes_analytics(youtube_analytics_client, start_date, end_date):
    """Get traffic source analytics for minutes watched."""
    try:
        traffic_response = youtube_analytics_client.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            dimensions="insightTrafficSourceType",
            metrics="estimatedMinutesWatched"
        ).execute()

        if not traffic_response.get("rows"):
            return {}

        traffic_sources = {}
        for row in traffic_response.get("rows", []):
            source_type = row[0]
            minutes = row[1]
            traffic_sources[source_type] = minutes

        return traffic_sources
    except Exception as e:
        bt.logging.warning(f"Error getting traffic source minutes analytics: {_format_error(e)}")
        return {}

@retry(**YT_API_RETRY_CONFIG)
def get_country_views_analytics(youtube_analytics_client, start_date, end_date):
    """Get views analytics by country."""
    try:
        country_response = youtube_analytics_client.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            dimensions="country",
            metrics="views"
        ).execute()

        if not country_response.get("rows"):
            return {}

        country_data = {}
        for row in country_response.get("rows", []):
            country_code = row[0]
            views = row[1]
            country_data[country_code] = views

        return country_data
    except Exception as e:
        bt.logging.warning(f"Error getting country views analytics: {_format_error(e)}")
        return {}

@retry(**YT_API_RETRY_CONFIG)
def get_country_minutes_analytics(youtube_analytics_client, start_date, end_date):
    """Get minutes watched analytics by country."""
    try:
        country_response = youtube_analytics_client.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            dimensions="country",
            metrics="estimatedMinutesWatched"
        ).execute()

        if not country_response.get("rows"):
            return {}

        country_data = {}
        for row in country_response.get("rows", []):
            country_code = row[0]
            minutes = row[1]
            country_data[country_code] = minutes

        return country_data
    except Exception as e:
        bt.logging.warning(f"Error getting country minutes analytics: {_format_error(e)}")
        return {}

@retry(**YT_API_RETRY_CONFIG)
def get_subscribers_gained_analytics(youtube_analytics_client, start_date, end_date):
    """Get subscribers gained analytics by day."""
    try:
        subscribers_response = youtube_analytics_client.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            dimensions="day",
            metrics="subscribersGained"
        ).execute()

        if not subscribers_response.get("rows"):
            return {}

        subscribers_data = {}
        for row in subscribers_response.get("rows", []):
            date = row[0]
            subscribers = row[1]
            subscribers_data[date] = subscribers

        return subscribers_data
    except Exception as e:
        bt.logging.warning(f"Error getting subscribers gained analytics: {_format_error(e)}")
        return {}

# ============================================================================
# Video Playlist and List Management
# ============================================================================

@retry(**YT_API_RETRY_CONFIG)
def get_uploads_playlist_id(youtube):
    """Retrieve the channel's uploads playlist id."""
    channels_response = youtube.channels().list(
        mine=True,
        part="contentDetails"
    ).execute()

    if not channels_response["items"]:
        raise Exception("No channel found for the authenticated user.")
        
    uploads_playlist_id = channels_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    return uploads_playlist_id

@retry(**YT_API_RETRY_CONFIG)
def list_all_videos(youtube, uploads_playlist_id):
    """List all videos in the uploads playlist."""
    videos = []
    nextPageToken = None

    while True:
        playlist_response = youtube.playlistItems().list(
            playlistId=uploads_playlist_id,
            part="snippet",
            maxResults=50,
            pageToken=nextPageToken
        ).execute()
        videos.extend(playlist_response.get("items", []))
        nextPageToken = playlist_response.get("nextPageToken")
        if not nextPageToken:
            break
    return videos

@retry(**YT_API_RETRY_CONFIG)
def get_all_uploads(youtube_data_client, max_age_days=365):
    """Get all video IDs uploaded within the specified time period."""
    uploads_playlist_id = get_uploads_playlist_id(youtube_data_client)
    videos = list_all_videos(youtube_data_client, uploads_playlist_id)

    cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)
    video_ids = []
    for video in videos:
        snippet = video["snippet"]
        published_at = datetime.strptime(
            snippet["publishedAt"], "%Y-%m-%dT%H:%M:%SZ"
        )
        if published_at >= cutoff_date:
            video_ids.append(snippet["resourceId"]["videoId"])

    bt.logging.info(f"Found {len(video_ids)} videos uploaded in the last {max_age_days} days")
    return video_ids

# ============================================================================
# Video Analytics Functions
# ============================================================================

@retry(**YT_API_RETRY_CONFIG)
def get_video_data(youtube_data_client, video_id, discrete_mode=False):
    """Get basic video information."""
    video_response = youtube_data_client.videos().list(
        part="snippet,statistics,contentDetails,status",
        id=video_id
    ).execute()

    if not video_response["items"]:
        raise Exception(f"No video found matching ID")

    if discrete_mode:
        bitcast_video_id = "bitcast_" + hashlib.sha256(video_id.encode()).hexdigest()[:8]
    else:
        bitcast_video_id = video_id

    video_info = video_response["items"][0]
    stats = {
        "videoId": video_id,
        "bitcastVideoId": bitcast_video_id,
        "title": video_info["snippet"]["title"],
        "description": video_info["snippet"]["description"],
        "publishedAt": video_info["snippet"]["publishedAt"],
        "viewCount": video_info["statistics"].get("viewCount", 0),
        "likeCount": video_info["statistics"].get("likeCount", 0),
        "commentCount": video_info["statistics"].get("commentCount", 0),
        "duration": video_info["contentDetails"]["duration"],
        "caption": video_info["contentDetails"]["caption"].lower() == "true",
        "privacyStatus": video_info["status"]["privacyStatus"]
    }

    return stats

@retry(**YT_API_RETRY_CONFIG)
def get_video_analytics(youtube_analytics_client, video_id, start_date=None, end_date=None, dimensions=""):
    """Get comprehensive video analytics including traffic sources."""
    if end_date is None:
        end_date = datetime.today().strftime('%Y-%m-%d')

    if start_date is None:
        start_date = (datetime.today() - timedelta(days=365)).strftime('%Y-%m-%d')

    # Define metrics in a consistent order
    metrics_list = "views,comments,likes,dislikes,shares,averageViewDuration,averageViewPercentage,estimatedMinutesWatched"

    analytics_response = youtube_analytics_client.reports().query(
        ids="channel==MINE",
        startDate=start_date,
        endDate=end_date,
        dimensions=dimensions,
        metrics=metrics_list,
        filters=f"video=={video_id}"
    ).execute()

    if not analytics_response.get("rows"):
        bt.logging.warning("No analytics data found for video")
        return []

    # Define metric names in the same order as the metrics_list
    metric_names = [
        "views", "comments", "likes", "dislikes", "shares", 
        "averageViewDuration", "averageViewPercentage", 
        "estimatedMinutesWatched"
    ]

    if dimensions:
        # Handle the case where dimensions are present
        analytics_info = []
        for row in analytics_response.get("rows", []):
            dimension_values = row[:len(dimensions.split(','))]
            metrics = dict(zip(metric_names, row[len(dimension_values):]))
            for i, dimension in enumerate(dimensions.split(',')):
                metrics[dimension] = dimension_values[i]
            analytics_info.append(metrics)
    else:
        # Handle the case where no dimensions are present
        analytics_data = analytics_response.get("rows", [])[0]
        analytics_info = dict(zip(metric_names, analytics_data))

    # Get traffic source data for views
    traffic_source_views = get_video_traffic_source_views_analytics(youtube_analytics_client, video_id, start_date, end_date)
    # Get traffic source data for minutes watched
    traffic_source_minutes = get_video_traffic_source_minutes_analytics(youtube_analytics_client, video_id, start_date, end_date)
    # Get country data for views
    country_views = get_video_country_views_analytics(youtube_analytics_client, video_id, start_date, end_date)
    # Get country data for minutes watched
    country_minutes = get_video_country_minutes_analytics(youtube_analytics_client, video_id, start_date, end_date)
    
    if isinstance(analytics_info, dict):
        analytics_info["trafficSourceViews"] = traffic_source_views
        analytics_info["trafficSourceMinutes"] = traffic_source_minutes
        analytics_info["countryViews"] = country_views
        analytics_info["countryMinutes"] = country_minutes
    else:
        for entry in analytics_info:
            entry["trafficSourceViews"] = traffic_source_views
            entry["trafficSourceMinutes"] = traffic_source_minutes
            entry["countryViews"] = country_views
            entry["countryMinutes"] = country_minutes

    return analytics_info

@retry(**YT_API_RETRY_CONFIG)
def get_video_traffic_source_views_analytics(youtube_analytics_client, video_id, start_date, end_date):
    """Get traffic source analytics for views for a specific video."""
    try:
        traffic_response = youtube_analytics_client.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            dimensions="insightTrafficSourceType",
            metrics="views",
            filters=f"video=={video_id}"
        ).execute()

        if not traffic_response.get("rows"):
            return {}

        traffic_sources = {}
        for row in traffic_response.get("rows", []):
            source_type = row[0]
            views = row[1]
            traffic_sources[source_type] = views

        return traffic_sources
    except Exception as e:
        bt.logging.warning(f"Error getting traffic source views analytics: {_format_error(e)}")
        return {}

@retry(**YT_API_RETRY_CONFIG)
def get_video_traffic_source_minutes_analytics(youtube_analytics_client, video_id, start_date, end_date):
    """Get traffic source analytics for minutes watched for a specific video."""
    try:
        traffic_response = youtube_analytics_client.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            dimensions="insightTrafficSourceType",
            metrics="estimatedMinutesWatched",
            filters=f"video=={video_id}"
        ).execute()

        if not traffic_response.get("rows"):
            return {}

        traffic_sources = {}
        for row in traffic_response.get("rows", []):
            source_type = row[0]
            minutes = row[1]
            traffic_sources[source_type] = minutes

        return traffic_sources
    except Exception as e:
        bt.logging.warning(f"Error getting traffic source minutes analytics: {_format_error(e)}")
        return {}

@retry(**YT_API_RETRY_CONFIG)
def get_video_country_views_analytics(youtube_analytics_client, video_id, start_date, end_date):
    """Get views analytics by country for a specific video."""
    try:
        country_response = youtube_analytics_client.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            dimensions="country",
            metrics="views",
            filters=f"video=={video_id}"
        ).execute()

        if not country_response.get("rows"):
            return {}

        country_data = {}
        for row in country_response.get("rows", []):
            country_code = row[0]
            views = row[1]
            country_data[country_code] = views

        return country_data
    except Exception as e:
        bt.logging.warning(f"Error getting country views analytics: {_format_error(e)}")
        return {}

@retry(**YT_API_RETRY_CONFIG)
def get_video_country_minutes_analytics(youtube_analytics_client, video_id, start_date, end_date):
    """Get minutes watched analytics by country for a specific video."""
    try:
        country_response = youtube_analytics_client.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            dimensions="country",
            metrics="estimatedMinutesWatched",
            filters=f"video=={video_id}"
        ).execute()

        if not country_response.get("rows"):
            return {}

        country_data = {}
        for row in country_response.get("rows", []):
            country_code = row[0]
            minutes = row[1]
            country_data[country_code] = minutes

        return country_data
    except Exception as e:
        bt.logging.warning(f"Error getting country minutes analytics: {_format_error(e)}")
        return {}

# ============================================================================
# Transcript Functions
# ============================================================================

@retry(stop=stop_after_attempt(TRANSCRIPT_MAX_RETRY), wait=wait_fixed(1), reraise=True)
def _fetch_transcript(video_id, rapid_api_key):
    """Internal function to fetch video transcript with retry logic."""
    url = "https://youtube-transcriptor.p.rapidapi.com/transcript"
    headers = {"x-rapidapi-key": rapid_api_key, "x-rapidapi-host": "youtube-transcriptor.p.rapidapi.com"}
    querystring = {"video_id": video_id}
    response = requests.get(url, headers=headers, params=querystring, timeout=10)
    response.raise_for_status()
    transcript_data = response.json()

    if isinstance(transcript_data, list) and transcript_data:
        bt.logging.info("Transcript fetched successfully")
        return transcript_data[0].get("transcription", [])
    elif isinstance(transcript_data, dict) and transcript_data.get("error") == "This video has no subtitles.":
        bt.logging.warning("No subtitles available for video")
        raise Exception("No subtitles available")
    else:
        bt.logging.warning(f"Error retrieving transcript: {transcript_data}")
        raise Exception("Error retrieving transcript")

def get_video_transcript(video_id, rapid_api_key):
    """Get video transcript with error handling."""
    try:
        return _fetch_transcript(video_id, rapid_api_key)
    except RetryError:
        return None

def _format_error(e):
    """Format error message to include only error type and brief summary."""
    error_type = type(e).__name__
    
    # For HTTP errors, try to extract status code and error message
    if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
        return f"{error_type} ({e.response.status_code})"
    
    # For API errors, try to extract error code and message
    if hasattr(e, 'error') and isinstance(e.error, dict):
        error_details = e.error.get('details', [{}])[0]
        error_message = error_details.get('message', 'unknown error')
        return f"{error_type} ({error_message})"
    
    # For other errors, return type and first line of message, excluding URLs
    error_msg = str(e)
    # Remove URLs from error message
    error_msg = re.sub(r'https?://\S+', '', error_msg)
    # Get first line and clean up
    error_msg = error_msg.split('\n')[0].strip()
    return f"{error_type} ({error_msg})"