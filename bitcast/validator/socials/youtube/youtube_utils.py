import bittensor as bt
import requests
import time
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from bitcast.validator.config import TRANSCRIPT_MAX_RETRY
import httpx
import hashlib
import asyncio
from tenacity import retry, stop_after_attempt, wait_fixed, RetryError

# ============================================================================
# Channel Analytics Functions
# ============================================================================

def get_channel_data(youtube_data_client, discrete_mode=False):
    """Get basic channel information."""
    account_info = youtube_data_client.channels().list(
        part="snippet,contentDetails,statistics",
        mine=True
    ).execute()

    channel_id = account_info['items'][0]['id']
    if discrete_mode:
        channel_id = hashlib.sha256(channel_id.encode()).hexdigest()

    channel_info = {
        "title": account_info['items'][0]['snippet']['title'],
        "id": channel_id,
        "channel_start": account_info['items'][0]['snippet']['publishedAt'],
        "viewCount": account_info['items'][0]['statistics']['viewCount'],
        "subCount": account_info['items'][0]['statistics']['subscriberCount'],
        "videoCount": account_info['items'][0]['statistics']['videoCount']
    }

    return channel_info

def get_channel_analytics(youtube_analytics_client, start_date, end_date=None, dimensions=""):
    """Get comprehensive channel analytics including traffic sources."""
    if end_date is None:
        end_date = datetime.today().strftime('%Y-%m-%d')
        
    analytics_response = youtube_analytics_client.reports().query(
        ids="channel==MINE",
        startDate=start_date,
        endDate=end_date,
        dimensions=dimensions,
        metrics="views,comments,likes,dislikes,shares,averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost,estimatedMinutesWatched"
        ).execute()

    if not analytics_response.get("rows"):
        raise Exception("No channel analytics data found.")

    metric_names = [
        "views", "comments", "likes",
        "shares", "averageViewDuration", "averageViewPercentage",
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
        bt.logging.warning(f"Error getting traffic source views analytics: {e}")
        return {}

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
        bt.logging.warning(f"Error getting traffic source minutes analytics: {e}")
        return {}

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
        bt.logging.warning(f"Error getting country views analytics: {e}")
        return {}

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
        bt.logging.warning(f"Error getting country minutes analytics: {e}")
        return {}

# ============================================================================
# Video Playlist and List Management
# ============================================================================

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

def get_video_data(youtube_data_client, video_id, discrete_mode=False):
    """Get basic video information."""
    video_response = youtube_data_client.videos().list(
        part="snippet,statistics,contentDetails,status",
        id=video_id
    ).execute()

    if not video_response["items"]:
        raise Exception(f"No video found with ID: {video_id}")

    if discrete_mode:
        video_id = hashlib.sha256(video_id.encode()).hexdigest()

    video_info = video_response["items"][0]
    stats = {
        "videoId": video_id,
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

def get_video_analytics(youtube_analytics_client, video_id, start_date=None, end_date=None, dimensions=""):
    """Get comprehensive video analytics including traffic sources."""
    if end_date is None:
        end_date = datetime.today().strftime('%Y-%m-%d')

    if start_date is None:
        start_date = (datetime.today() - timedelta(days=365)).strftime('%Y-%m-%d')

    analytics_response = youtube_analytics_client.reports().query(
        ids="channel==MINE",
        startDate=start_date,
        endDate=end_date,
        dimensions=dimensions,
        metrics="views,comments,likes,shares,averageViewDuration,averageViewPercentage,estimatedMinutesWatched",
        filters=f"video=={video_id}"
    ).execute()

    if not analytics_response.get("rows"):
        bt.logging.warning(f"No analytics data found for video ID: {video_id}")
        return []

    metric_names = [
        "views", "comments", "likes",
        "shares", "averageViewDuration", "averageViewPercentage",
        "estimatedMinutesWatched"
    ]

    if dimensions:
        # Handle the case where dimensions are present
        analytics_info = []
        for row in analytics_response.get("rows", []):
            date = row[0]  # Assuming the first element is the date
            metrics = dict(zip(metric_names, row[1:]))
            metrics["date"] = date
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
        bt.logging.warning(f"Error getting traffic source views analytics for video {video_id}: {e}")
        return {}

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
        bt.logging.warning(f"Error getting traffic source minutes analytics for video {video_id}: {e}")
        return {}

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
        bt.logging.warning(f"Error getting country views analytics for video {video_id}: {e}")
        return {}

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
        bt.logging.warning(f"Error getting country minutes analytics for video {video_id}: {e}")
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
        bt.logging.warning(f"No subtitles available for video_id {video_id}")
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