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
    bt.logging.info("Reset scored_video_ids")

def is_video_already_scored(video_id):
    """Check if a video has already been scored by another hotkey."""
    if video_id in scored_video_ids:
        bt.logging.info("Video already scored")
        return True
    return False

def mark_video_as_scored(video_id):
    """Mark a video as scored to prevent duplicate processing."""
    scored_video_ids.append(video_id)

# ============================================================================
# Channel Analytics Functions
# ============================================================================

@retry(**YT_API_RETRY_CONFIG)
def _query(client, start_date, end_date, metric, dimensions=None, filters=None):
    params = {
        'ids': 'channel==MINE',
        'startDate': start_date,
        'endDate': end_date,
        'metrics': metric
    }
    if dimensions:
        params['dimensions'] = dimensions
    if filters:
        params['filters'] = filters
    resp = client.reports().query(**params).execute()
    rows = resp.get("rows") or []
    if not rows:
        return {} if dimensions else []
    
    if not dimensions:
        # Return the row directly for non-dimensional queries
        return rows[0]
        
    # For dimensional queries, create a dictionary
    data = {}
    for row in rows:
        dims, val = row[:-1], row[-1]
        key = "|".join(str(d) for d in dims) if len(dims) > 1 else str(dims[0])
        data[key] = val
    return data

@retry(**YT_API_RETRY_CONFIG)
def get_channel_data(youtube_data_client, discrete_mode=False):
    """Get basic channel information."""
    resp = youtube_data_client.channels().list(
        part="snippet,contentDetails,statistics",
        mine=True
    ).execute()
    item = resp['items'][0]
    cid = item['id']
    bcid = ("bitcast_" + hashlib.sha256(cid.encode()).hexdigest()[:8]) if discrete_mode else cid
    return {
        "title": item['snippet']['title'],
        "id": cid,
        "bitcastChannelId": bcid,
        "channel_start": item['snippet']['publishedAt'],
        "viewCount": item['statistics']['viewCount'],
        "subCount": item['statistics']['subscriberCount'],
        "videoCount": item['statistics']['videoCount'],
        "url": f"https://www.youtube.com/channel/{cid}"
    }

@retry(**YT_API_RETRY_CONFIG)
def get_channel_analytics(youtube_analytics_client, start_date, end_date=None, dimensions=""):
    """Get comprehensive channel analytics including traffic sources."""
    end = end_date or datetime.today().strftime('%Y-%m-%d')
    metrics = ",".join([
        "views","comments","likes","dislikes","shares",
        "averageViewDuration","averageViewPercentage",
        "subscribersGained","subscribersLost","estimatedMinutesWatched"
    ])
    resp = youtube_analytics_client.reports().query(
        ids="channel==MINE",
        startDate=start_date,
        endDate=end,
        dimensions=dimensions,
        metrics=metrics
    ).execute()
    rows = resp.get("rows")
    if not rows:
        raise Exception("No channel analytics data found.")
    names = metrics.split(",")
    if dimensions:
        info = []
        dims_keys = dimensions.split(",")
        for row in rows:
            dims, vals = row[:len(dims_keys)], row[len(dims_keys):]
            entry = dict(zip(names, vals))
            for i, d in enumerate(dims_keys):
                entry[d] = dims[i]
            info.append(entry)
    else:
        info = dict(zip(names, rows[0]))

    # extras
    traffic_views   = _query(youtube_analytics_client, start_date, end, "views", "insightTrafficSourceType")
    traffic_minutes = _query(youtube_analytics_client, start_date, end, "estimatedMinutesWatched", "insightTrafficSourceType")
    country_views   = _query(youtube_analytics_client, start_date, end, "views", "country")
    country_minutes = _query(youtube_analytics_client, start_date, end, "estimatedMinutesWatched", "country")
    past = (
        (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=30)).strftime('%Y-%m-%d')
        if dimensions == "day" else start_date
    )
    subs = _query(youtube_analytics_client, past, end, "subscribersGained", "day")

    extras = {
        "trafficSourceViews":   traffic_views,
        "trafficSourceMinutes": traffic_minutes,
        "countryViews":         country_views,
        "countryMinutes":       country_minutes,
        "subscribersGained":    subs
    }
    if isinstance(info, dict):
        info.update(extras)
    else:
        for entry in info:
            entry.update(extras)
    return info

# ============================================================================
# Video Playlist and List Management
# ============================================================================

@retry(**YT_API_RETRY_CONFIG)
def get_uploads_playlist_id(youtube):
    """Retrieve the channel's uploads playlist id."""
    resp = youtube.channels().list(mine=True, part="contentDetails").execute()
    items = resp.get("items") or []
    if not items:
        raise Exception("No channel found for the authenticated user.")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

@retry(**YT_API_RETRY_CONFIG)
def list_all_videos(youtube, uploads_playlist_id):
    """List all videos in the uploads playlist."""
    all_items, token = [], None
    while True:
        resp = youtube.playlistItems().list(
            playlistId=uploads_playlist_id,
            part="snippet",
            maxResults=50,
            pageToken=token
        ).execute()
        all_items.extend(resp.get("items", []))
        token = resp.get("nextPageToken")
        if not token:
            break
    return all_items

@retry(**YT_API_RETRY_CONFIG)
def get_all_uploads(youtube_data_client, max_age_days=365):
    """Get all video IDs uploaded within the specified time period."""
    pid = get_uploads_playlist_id(youtube_data_client)
    videos = list_all_videos(youtube_data_client, pid)
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    vids = []
    for v in videos:
        pub = datetime.strptime(v["snippet"]["publishedAt"], "%Y-%m-%dT%H:%M:%SZ")
        if pub >= cutoff:
            vids.append(v["snippet"]["resourceId"]["videoId"])
    bt.logging.info(f"Found {len(vids)} videos uploaded in the last {max_age_days} days")
    return vids

# ============================================================================
# Video Analytics Functions
# ============================================================================

@retry(**YT_API_RETRY_CONFIG)
def get_video_data(youtube_data_client, video_id, discrete_mode=False):
    """Get basic video information."""
    resp = youtube_data_client.videos().list(
        part="snippet,statistics,contentDetails,status",
        id=video_id
    ).execute()
    items = resp.get("items") or []
    if not items:
        raise Exception("No video found with matching ID")
    info = items[0]
    bcid = ("bitcast_" + hashlib.sha256(video_id.encode()).hexdigest()[:8]) if discrete_mode else video_id
    return {
        "videoId": video_id,
        "bitcastVideoId": bcid,
        "title": info["snippet"]["title"],
        "description": info["snippet"]["description"],
        "publishedAt": info["snippet"]["publishedAt"],
        "viewCount": info["statistics"].get("viewCount", 0),
        "likeCount": info["statistics"].get("likeCount", 0),
        "commentCount": info["statistics"].get("commentCount", 0),
        "duration": info["contentDetails"]["duration"],
        "caption": info["contentDetails"]["caption"].lower() == "true",
        "privacyStatus": info["status"]["privacyStatus"]
    }

@retry(**YT_API_RETRY_CONFIG)
def get_video_analytics(youtube_analytics_client, video_id, start_date=None, end_date=None, dimensions=""):
    """Get comprehensive video analytics including traffic sources."""
    end = end_date or datetime.today().strftime('%Y-%m-%d')
    start = start_date or (datetime.today() - timedelta(days=365)).strftime('%Y-%m-%d')
    metrics = ",".join([
        "views","comments","likes","dislikes","shares",
        "averageViewDuration","averageViewPercentage","estimatedMinutesWatched"
    ])
    resp = youtube_analytics_client.reports().query(
        ids="channel==MINE",
        startDate=start,
        endDate=end,
        dimensions=dimensions,
        metrics=metrics,
        filters=f"video=={video_id}"
    ).execute()
    rows = resp.get("rows")
    if not rows:
        bt.logging.warning("No analytics data found for video")
        return [] if dimensions else {}
    names = metrics.split(",")
    if dimensions:
        results = []
        dims_keys = dimensions.split(",")
        for r in rows:
            dims, vals = r[:len(dims_keys)], r[len(dims_keys):]
            d = dict(zip(names, vals))
            for i, dkey in enumerate(dims_keys):
                d[dkey] = dims[i]
            results.append(d)
        return results
    return dict(zip(names, rows[0]))

@retry(**YT_API_RETRY_CONFIG)
def get_additional_video_analytics(youtube_analytics_client, video_id, start_date=None, end_date=None, ECO_MODE=False):
    """Get additional video analytics including traffic sources and country data."""
    end = end_date or datetime.today().strftime('%Y-%m-%d')
    start = start_date or (datetime.today() - timedelta(days=365)).strftime('%Y-%m-%d')
    out = {
        "trafficSourceMinutes": _query(
            youtube_analytics_client, start, end,
            "estimatedMinutesWatched", "insightTrafficSourceType,day",
            filters=f"video=={video_id}"
        )
    }
    if ECO_MODE:
        return out

    metric_dims = {
        "countryMinutes":                   ("estimatedMinutesWatched", "country"),
        "creatorContentTypeMinutes":        ("estimatedMinutesWatched", "creatorContentType"),
        "playbackLocationMinutes":          ("estimatedMinutesWatched", "insightPlaybackLocationType"),
        "avgViewPercentageByTrafficSource": ("averageViewPercentage", "insightTrafficSourceType"),
        "liveOrOnDemandMinutes":            ("estimatedMinutesWatched", "liveOrOnDemand"),
        "youtubeProductMinutes":            ("estimatedMinutesWatched", "youtubeProduct"),
        "deviceTypeMinutes":                ("estimatedMinutesWatched", "deviceType"),
        "operatingSystemMinutes":           ("estimatedMinutesWatched", "operatingSystem"),
        "ageGroupViewerPercentage":         ("viewerPercentage", "ageGroup,gender"),
        "elapsedVideoTimeRatioAudienceWatchRatio": ("audienceWatchRatio", "elapsedVideoTimeRatio"),
        "sharingServiceShares":             ("shares", "sharingService")
    }
    for key, (metric, dims) in metric_dims.items():
        out[key] = _query(
            youtube_analytics_client, start, end,
            metric, dims,
            filters=f"video=={video_id}"
        )
    return out

# ============================================================================
# Transcript Functions
# ============================================================================

@retry(stop=stop_after_attempt(TRANSCRIPT_MAX_RETRY), wait=wait_fixed(1), reraise=True)
def _fetch_transcript(video_id, rapid_api_key):
    """Internal function to fetch video transcript with retry logic."""
    url = "https://youtube-transcriptor.p.rapidapi.com/transcript"
    headers = {
        "x-rapidapi-key": rapid_api_key,
        "x-rapidapi-host": "youtube-transcriptor.p.rapidapi.com"
    }
    resp = requests.get(url, headers=headers, params={"video_id": video_id}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list) and data:
        bt.logging.info("Transcript fetched successfully")
        return data[0].get("transcription", [])
    if isinstance(data, dict) and data.get("error") == "This video has no subtitles.":
        bt.logging.warning("No subtitles available for video")
        raise Exception("No subtitles available")
    bt.logging.warning(f"Error retrieving transcript: {data}")
    raise Exception("Error retrieving transcript")

def get_video_transcript(video_id, rapid_api_key):
    """Get video transcript with error handling."""
    try:
        return _fetch_transcript(video_id, rapid_api_key)
    except RetryError:
        return None

def _format_error(e):
    """Format error message to include only error type and brief summary."""
    et = type(e).__name__
    if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
        return f"{et} ({e.response.status_code})"
    if hasattr(e, 'error') and isinstance(e.error, dict):
        details = e.error.get('details', [{}])[0].get('message', 'unknown error')
        return f"{et} ({details})"
    msg = re.sub(r'https?://\S+', '', str(e)).split('\n')[0].strip()
    return f"{et} ({msg})"