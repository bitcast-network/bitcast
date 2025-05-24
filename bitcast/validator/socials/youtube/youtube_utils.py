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
def _query_multiple_metrics(client, start_date, end_date, metrics_list, dimensions=None, filters=None):
    """Query multiple metrics in a single API call and return split results.
    
    Args:
        client: YouTube Analytics client
        start_date: Start date for query
        end_date: End date for query
        metrics_list: List of metric names to fetch
        dimensions: Dimensions for the query
        filters: Filters for the query
        
    Returns:
        Dictionary with metric names as keys and their respective results as values
    """
    metrics_str = ",".join(metrics_list)
    params = {
        'ids': 'channel==MINE',
        'startDate': start_date,
        'endDate': end_date,
        'metrics': metrics_str
    }
    if dimensions:
        params['dimensions'] = dimensions
    if filters:
        params['filters'] = filters
    
    resp = client.reports().query(**params).execute()
    rows = resp.get("rows") or []
    if not rows:
        return {metric: ({} if dimensions else []) for metric in metrics_list}
    
    results = {}
    
    if not dimensions:
        # For non-dimensional queries, return values by index
        for i, metric in enumerate(metrics_list):
            results[metric] = rows[0][i] if i < len(rows[0]) else 0
    else:
        # For dimensional queries, create dictionaries for each metric
        for metric in metrics_list:
            results[metric] = {}
        
        for row in rows:
            # Split dimensions and metric values
            num_dims = len(dimensions.split(",")) if dimensions else 0
            dims, vals = row[:num_dims], row[num_dims:]
            
            # Create dimension key
            key = "|".join(str(d) for d in dims) if len(dims) > 1 else str(dims[0])
            
            # Assign each metric value
            for i, metric in enumerate(metrics_list):
                if i < len(vals):
                    results[metric][key] = vals[i]
    
    return results

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

    # Consolidate API calls for traffic source data
    traffic_data = _query_multiple_metrics(
        youtube_analytics_client, start_date, end, 
        ["views", "estimatedMinutesWatched"], 
        "insightTrafficSourceType"
    )
    
    # Consolidate API calls for country data
    country_data = _query_multiple_metrics(
        youtube_analytics_client, start_date, end,
        ["views", "estimatedMinutesWatched"],
        "country"
    )
    
    # Keep subscriber data separate due to different date range
    past = (
        (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=30)).strftime('%Y-%m-%d')
        if dimensions == "day" else start_date
    )
    subs = _query(youtube_analytics_client, past, end, "subscribersGained", "day")

    extras = {
        "trafficSourceViews":   traffic_data["views"],
        "trafficSourceMinutes": traffic_data["estimatedMinutesWatched"],
        "countryViews":         country_data["views"],
        "countryMinutes":       country_data["estimatedMinutesWatched"],
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

def get_video_analytics(youtube_analytics_client, video_id, start_date=None, end_date=None, metric_dims=None):
    """Get video analytics based on specified metric-dimension combinations.
    
    Args:
        youtube_analytics_client: The YouTube Analytics API client
        video_id: The YouTube video ID
        start_date: Start date for analytics (defaults to 1 year ago)
        end_date: End date for analytics (defaults to today)
        metric_dims: Dictionary of {output_key: (metric, dimensions)} to fetch
                    If None, raises ValueError
    
    Returns:
        Dictionary of analytics results keyed by the provided output_keys
    """
    if metric_dims is None:
        raise ValueError("metric_dims parameter is required")
        
    end = end_date or datetime.today().strftime('%Y-%m-%d')
    start = start_date or (datetime.today() - timedelta(days=365)).strftime('%Y-%m-%d')
    
    # Group metrics by dimensions to consolidate API calls
    dimension_groups = {}
    key_to_metric_dim = {}
    
    for key, (metric, dims) in metric_dims.items():
        key_to_metric_dim[key] = (metric, dims)
        dims_key = dims or ""  # Use empty string for no dimensions
        
        if dims_key not in dimension_groups:
            dimension_groups[dims_key] = []
        dimension_groups[dims_key].append((key, metric))
    
    results = {}
    day_structured_data = {}
    day_metrics = {}
    has_day_dimension = False
    
    # Make consolidated API calls for each dimension group
    for dims_key, metrics_list in dimension_groups.items():
        if not metrics_list:
            continue
            
        # Extract just the metric names for the API call
        metric_names = [metric for _, metric in metrics_list]
        key_names = [key for key, _ in metrics_list]
        
        try:
            # Make consolidated API call
            consolidated_results = _query_multiple_metrics(
                youtube_analytics_client, start, end,
                metric_names, dims_key if dims_key else None,
                filters=f"video=={video_id}"
            )
            
            # Distribute results back to individual keys
            for i, (key, metric) in enumerate(metrics_list):
                dims = key_to_metric_dim[key][1]
                query_result = consolidated_results.get(metric, {} if dims else [])
                
                # Handle scalar values for metrics with no dimensions
                if not dims and isinstance(query_result, (int, float)):
                    results[key] = query_result
                elif not dims and isinstance(query_result, list) and query_result:
                    results[key] = query_result[0] if query_result else 0
                # Handle simple day dimension (just "day")
                elif dims == "day":
                    has_day_dimension = True
                    day_metrics[key] = query_result
                    results[key] = query_result
                # Handle multi-dimensional data that includes day
                elif dims and "day" in dims and "," in dims:
                    has_day_dimension = True
                    
                    # Skip empty results
                    if not query_result or not isinstance(query_result, dict):
                        results[key] = {}
                        continue
                        
                    # Create a nested structure where data is organized by day first
                    day_data = {}
                    for combined_key, value in query_result.items():
                        # Split the combined key (e.g., "DESKTOP|2025-05-12")
                        parts = combined_key.split('|')
                        if len(parts) == 2:
                            dimension_value = parts[0]
                            day = parts[1]
                            
                            # Initialize nested dictionaries
                            if day not in day_data:
                                day_data[day] = {}
                            
                            # Add data
                            day_data[day][dimension_value] = value
                    
                    # Store the day-structured data for later merge
                    day_structured_data[key] = day_data
                    
                    # Also store the original data
                    results[key] = query_result
                else:
                    # Standard result
                    results[key] = query_result
                    
        except Exception as e:
            bt.logging.warning(f"Failed to retrieve analytics for dimension '{dims_key}': {_format_error(e)}")
            # Set individual results to None for this dimension group
            for key, _ in metrics_list:
                results[key] = None
    
    # Consolidate day-structured data if there are any day dimensions
    if has_day_dimension:
        # Create a day_metrics entry for uniform access
        results["day_metrics"] = {}
        
        # Collect all days from both simple and complex day metrics
        all_days = set()
        
        # Add days from day_metrics (simple "day" dimension)
        for metric_data in day_metrics.values():
            if isinstance(metric_data, dict):
                all_days.update(metric_data.keys())
        
        # Add days from day_structured_data (complex dimensions with "day")
        for day_dict in day_structured_data.values():
            all_days.update(day_dict.keys())
        
        # Create entries for each day
        for day in sorted(all_days):
            day_entry = {"day": day}
            
            # Add simple metrics with day dimension
            for key, data in day_metrics.items():
                if isinstance(data, dict):
                    day_entry[key] = data.get(day, 0)
            
            # Add complex metrics
            for key, day_data in day_structured_data.items():
                if day in day_data:
                    day_entry[key] = day_data[day]
            
            results["day_metrics"][day] = day_entry
    
    return results

# ============================================================================
# Transcript Functions
# ============================================================================

@retry(stop=stop_after_attempt(TRANSCRIPT_MAX_RETRY), wait=wait_fixed(1), reraise=True)
def _fetch_transcript(video_id, rapid_api_key):
    """Internal function to fetch video transcript with retry logic."""
    url = "https://youtube-transcriptor.p.rapidapi.com/transcript"
    headers = {"x-rapidapi-key": rapid_api_key, "x-rapidapi-host": "youtube-transcriptor.p.rapidapi.com"}
    querystring = {"video_id": video_id}
    response = requests.get(url, headers=headers, params=querystring, timeout=5)
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
    et = type(e).__name__
    if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
        return f"{et} ({e.response.status_code})"
    if hasattr(e, 'error') and isinstance(e.error, dict):
        details = e.error.get('details', [{}])[0].get('message', 'unknown error')
        return f"{et} ({details})"
    msg = re.sub(r'https?://\S+', '', str(e)).split('\n')[0].strip()
    return f"{et} ({msg})"