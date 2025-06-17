import bittensor as bt
import requests
import time
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from bitcast.validator.utils.config import TRANSCRIPT_MAX_RETRY, CACHE_DIRS, YOUTUBE_SEARCH_CACHE_EXPIRY, YT_MAX_VIDEOS
import httpx
import hashlib
import asyncio
from tenacity import retry, stop_after_attempt, wait_fixed, RetryError
from googleapiclient.errors import HttpError
import os
import json
import re
from diskcache import Cache
from threading import Lock
import atexit

# Import SafeCacheManager for thread-safe cache operations
from bitcast.validator.utils.safe_cache import SafeCacheManager

# Thread lock for video scoring to ensure thread safety
_scored_videos_lock = Lock()
# Thread lock for API call counters
_api_count_lock = Lock()

class YouTubeSearchCache:
    _instance = None
    _cache: Cache = None
    _cache_dir = CACHE_DIRS["youtube_search"]
    _lock = Lock()

    @classmethod
    def initialize_cache(cls) -> None:
        """Initialize the cache if it hasn't been initialized yet."""
        if cls._cache is None:
            os.makedirs(cls._cache_dir, exist_ok=True)
            cls._cache = Cache(
                directory=cls._cache_dir,
                size_limit=1e8,  # 100MB - search results can be sizable
                disk_min_file_size=0,
                disk_pickle_protocol=4,
            )
            # Register cleanup on program exit
            atexit.register(cls.cleanup)

    @classmethod
    def cleanup(cls) -> None:
        """Clean up resources."""
        if cls._cache is not None:
            cls._cache.close()
            cls._cache = None

    @classmethod
    def get_cache(cls) -> Cache:
        """Thread-safe cache access."""
        if cls._cache is None:
            with cls._lock:
                if cls._cache is None:
                    cls.initialize_cache()
        return cls._cache

    def __del__(self):
        """Ensure cleanup on object destruction."""
        self.cleanup()

# Initialize cache
YouTubeSearchCache.initialize_cache()

# Global list to track which videos have already been scored
# This list is shared between youtube_scoring.py and youtube_evaluation.py
scored_video_ids = []

# Retry configuration for YouTube API calls
YT_API_RETRY_CONFIG = {
    'stop': stop_after_attempt(3),
    'wait': wait_fixed(0.5),
    'reraise': True
}

# API call counters to track usage of YouTube Data and Analytics APIs for each token
data_api_call_count = 0
analytics_api_call_count = 0

def reset_scored_videos():
    """Reset the global scored_video_ids list.
    
    This function is used by other modules to clear the list of scored videos.
    """
    global scored_video_ids
    with _scored_videos_lock:
        scored_video_ids = []
        bt.logging.info("Reset scored_video_ids")

def is_video_already_scored(video_id):
    """Check if a video has already been scored by another hotkey."""
    with _scored_videos_lock:
        if video_id in scored_video_ids:
            bt.logging.info("Video already scored")
            return True
        return False

def mark_video_as_scored(video_id):
    """Mark a video as scored to prevent duplicate processing."""
    with _scored_videos_lock:
        scored_video_ids.append(video_id)

def reset_api_call_counts():
    """Reset the API call counters for YouTube Data and Analytics APIs."""
    global data_api_call_count, analytics_api_call_count
    with _api_count_lock:
        data_api_call_count = 0
        analytics_api_call_count = 0

# ============================================================================
# Channel Analytics Functions
# ============================================================================

@retry(**YT_API_RETRY_CONFIG)
def _query(client, start_date, end_date, metric, dimensions=None, filters=None, max_results=None, sort=None):
    global analytics_api_call_count
    with _api_count_lock:
        analytics_api_call_count += 1
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
    if max_results:
        params['maxResults'] = max_results
    if sort:
        params['sort'] = sort
    
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
def _query_multiple_metrics(client, start_date, end_date, metrics_list, dimensions=None, filters=None, max_results=None, sort=None):
    global analytics_api_call_count
    with _api_count_lock:
        analytics_api_call_count += 1
    """Query multiple metrics in a single API call and return split results.
    
    Args:
        client: YouTube Analytics client
        start_date: Start date for query
        end_date: End date for query
        metrics_list: List of metric names to fetch
        dimensions: Dimensions for the query
        filters: Filters for the query
        max_results: Maximum number of results to return
        sort: Sort parameter for ordering results
        
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
    if max_results:
        params['maxResults'] = max_results
    if sort:
        params['sort'] = sort
    
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
    global data_api_call_count
    with _api_count_lock:
        data_api_call_count += 1
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

def _parse_analytics_response(resp, metrics_list, dimensions=""):
    """Helper to parse analytics response into structured data."""
    rows = resp.get("rows")
    if not rows:
        return None
    
    if dimensions:
        dims_keys = dimensions.split(",")
        return [{**dict(zip(metrics_list, row[len(dims_keys):])), 
                 **{dims_keys[i]: row[i] for i in range(len(dims_keys))}} 
                for row in rows]
    return dict(zip(metrics_list, rows[0]))

@retry(**YT_API_RETRY_CONFIG) 
def get_channel_analytics(youtube_analytics_client, start_date, end_date=None, dimensions=""):
    global analytics_api_call_count
    with _api_count_lock:
        analytics_api_call_count += 1
    """Get comprehensive channel analytics including traffic sources."""
    end = end_date or datetime.today().strftime('%Y-%m-%d')
    
    all_metrics = ["views","comments","likes","dislikes","shares",
                   "averageViewDuration","averageViewPercentage", 
                   "subscribersGained","subscribersLost","estimatedMinutesWatched",
                   "estimatedAdRevenue","playbackBasedCpm"]
    
    # Try all metrics first, fallback to core metrics if revenue metrics fail
    try:
        resp = youtube_analytics_client.reports().query(
            ids="channel==MINE", startDate=start_date, endDate=end,
            dimensions=dimensions, metrics=",".join(all_metrics)
        ).execute()
        info = _parse_analytics_response(resp, all_metrics, dimensions)
    except Exception as e:
        bt.logging.warning(f"Revenue metrics failed, retrying without them: {_format_error(e)}")
        with _api_count_lock:
            analytics_api_call_count += 1
        core_metrics = all_metrics[:-2]  # Remove revenue metrics
        resp = youtube_analytics_client.reports().query(
            ids="channel==MINE", startDate=start_date, endDate=end,
            dimensions=dimensions, metrics=",".join(core_metrics)
        ).execute()
        info = _parse_analytics_response(resp, core_metrics, dimensions)
        # Add missing revenue metrics with default values
        revenue_defaults = {"estimatedAdRevenue": 0, "playbackBasedCpm": 0}
        if dimensions:
            for entry in info:
                entry.update(revenue_defaults)
        else:
            info.update(revenue_defaults)
    
    if not info:
        raise Exception("No channel analytics data found.")

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
# Video Management
# ============================================================================

@retry(**YT_API_RETRY_CONFIG)
def _get_uploads_playlist_id(youtube):
    """Return the channel's 'uploads' playlist ID (1-unit call)."""
    global data_api_call_count
    with _api_count_lock:
        data_api_call_count += 1
    resp = youtube.channels().list(mine=True, part="contentDetails").execute()
    items = resp.get("items") or []
    if not items:
        raise RuntimeError("No channel found for the authenticated user")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def _fallback_via_search(youtube, channel_id, cutoff_iso):
    """Quota-heavy fallback path (100 units per request). Uses caching to reduce API calls."""
    global data_api_call_count
    
    # Create cache key from channel_id and cutoff_iso
    cache_key = f"{channel_id}"
    cache = YouTubeSearchCache.get_cache()
    
    # Check cache first using SafeCacheManager
    cached_vids = SafeCacheManager.safe_get(cache, cache_key)
    if cached_vids is not None:
        bt.logging.info(f"Found {len(cached_vids)} videos in search cache")
        return cached_vids
    
    # Cache miss - perform API search (limited to 3 calls, sorted by date)
    vids, token, call_count = [], None, 0
    max_calls = 2   # limit to most recent 100 videos because the search calls cost 100 credits
    
    while call_count < max_calls:
        with _api_count_lock:
            data_api_call_count += 100  # search.list() uses 100 credits per call
        resp = youtube.search().list(
            part="id",
            type="video",
            channelId=channel_id,
            publishedAfter=cutoff_iso,
            maxResults=50,
            pageToken=token,
            order="date"  # Sort by publish time (newest first)
        ).execute()
        vids += [item["id"]["videoId"] for item in resp.get("items", [])]
        call_count += 1
        
        token = resp.get("nextPageToken")
        if not token:
            break
        time.sleep(0.25)  # courteous pause
    
    bt.logging.info(f"API search found {len(vids)} videos")
    
    # Limit to max videos per account and store in cache using SafeCacheManager
    vids = vids[:YT_MAX_VIDEOS]
    SafeCacheManager.safe_set(cache, cache_key, vids, expire=YOUTUBE_SEARCH_CACHE_EXPIRY)
    
    return vids

@retry(**YT_API_RETRY_CONFIG)
def get_all_uploads(youtube, max_age_days: int = 365):
    """
    Return a list of video IDs uploaded within the last `max_age_days`.

    Strategy:
      1. Use playlistItems.list (cheap) and bail out early when items get old.
      2. If we hit the rare invalidPageToken bug, fall back to search.list.
    """
    global data_api_call_count
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1) cheap path ----------------------------------------------------------
    playlist_id = _get_uploads_playlist_id(youtube)
    req = youtube.playlistItems().list(
        playlistId=playlist_id,
        part="snippet,contentDetails",
        maxResults=50,
        fields="items(snippet/publishedAt,"
        "contentDetails/videoId),nextPageToken",
    )

    vids = []
    while req:
        try:
            with _api_count_lock:
                data_api_call_count += 1  # Count each req.execute() call (1 credit each)
            resp = req.execute()
        except HttpError as e:
            if e.resp.status == 404 and "playlistNotFound" in str(e):
                bt.logging.warning("Playlist not found - switching to search method")
                # Need channel ID for fallback
                with _api_count_lock:
                    data_api_call_count += 1  # channels.list() call for fallback
                channel_id = youtube.channels().list(mine=True, part="id").execute()[
                    "items"
                ][0]["id"]
                return _fallback_via_search(youtube, channel_id, cutoff_iso)
            raise  # other errors → retry via decorator

        for item in resp["items"]:
            pub = datetime.strptime(
                item["snippet"]["publishedAt"], "%Y-%m-%dT%H:%M:%SZ"
            )
            if pub < cutoff:
                bt.logging.info(
                    f"Found {len(vids)} uploads in last {max_age_days} days (playlist)"
                )
                return vids[:YT_MAX_VIDEOS]
            vids.append(item["contentDetails"]["videoId"])

        req = youtube.playlistItems().list_next(req, resp)

    bt.logging.info(f"Found {len(vids)} uploads in last {max_age_days} days (playlist)")
    return vids[:YT_MAX_VIDEOS]

# ============================================================================
# Video Analytics Functions
# ============================================================================

# @retry(**YT_API_RETRY_CONFIG)
# def get_video_data(youtube_data_client, video_id, discrete_mode=False):
#     """Get basic video information."""
#     resp = youtube_data_client.videos().list(
#         part="snippet,statistics,contentDetails,status",
#         id=video_id
#     ).execute()
#     items = resp.get("items") or []
#     if not items:
#         raise Exception("No video found with matching ID")
#     info = items[0]
#     bcid = ("bitcast_" + hashlib.sha256(video_id.encode()).hexdigest()[:8]) if discrete_mode else video_id
#     return {
#         "videoId": video_id,
#         "bitcastVideoId": bcid,
#         "title": info["snippet"]["title"],
#         "description": info["snippet"]["description"],
#         "publishedAt": info["snippet"]["publishedAt"],
#         "viewCount": info["statistics"].get("viewCount", 0),
#         "likeCount": info["statistics"].get("likeCount", 0),
#         "commentCount": info["statistics"].get("commentCount", 0),
#         "duration": info["contentDetails"]["duration"],
#         "caption": info["contentDetails"]["caption"].lower() == "true",
#         "privacyStatus": info["status"]["privacyStatus"]
#     }

@retry(**YT_API_RETRY_CONFIG)
def get_video_data_batch(youtube_data_client, video_ids, discrete_mode=False):
    """Fetch basic video information for up to 50 IDs per API call, batching to reduce calls."""
    global data_api_call_count
    result = {}
    # Batch in chunks of 50 IDs
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        with _api_count_lock:
            data_api_call_count += 1
        resp = youtube_data_client.videos().list(
            part="snippet,statistics,contentDetails,status",
            id=','.join(batch)
        ).execute()
        items = resp.get('items', []) or []
        for info in items:
            vid = info['id']
            bcid = ("bitcast_" + hashlib.sha256(vid.encode()).hexdigest()[:8]) if discrete_mode else vid
            result[vid] = {
                "videoId": vid,
                "bitcastVideoId": bcid,
                "title": info['snippet']['title'],
                "description": info['snippet']['description'],
                "publishedAt": info['snippet']['publishedAt'],
                "viewCount": info['statistics'].get('viewCount', 0),
                "likeCount": info['statistics'].get('likeCount', 0),
                "commentCount": info['statistics'].get('commentCount', 0),
                "duration": info['contentDetails'].get('duration', 'PT0S'),
                "caption": info['contentDetails'].get('caption', 'false').lower() == 'true',
                "privacyStatus": info['status'].get('privacyStatus', 'private')
            }
    return result

# Provide single-video get_video_data for compatibility with tests
def get_video_data(youtube_data_client, video_id, discrete_mode=False):
    """Fetch basic video information for a single video by wrapping batch function."""
    return get_video_data_batch(youtube_data_client, [video_id], discrete_mode)[video_id]

def get_video_analytics(youtube_analytics_client, video_id, start_date=None, end_date=None, metric_dims=None, filters=None):
    """Get video analytics based on specified metric-dimension combinations.
    
    Args:
        youtube_analytics_client: The YouTube Analytics API client
        video_id: The YouTube video ID
        start_date: Start date for analytics (defaults to 1 year ago)
        end_date: End date for analytics (defaults to today)
        metric_dims: Dictionary of {output_key: (metric, dimensions, filter, maxResults, sort)} to fetch
                    If None, raises ValueError
        filters: Optional additional filters to combine with the video filter and per-metric filters
                Format: "filter1==value1;filter2==value2" 
    
    Returns:
        Dictionary of analytics results keyed by the provided output_keys
    """
    if metric_dims is None:
        raise ValueError("metric_dims parameter is required")
        
    end = end_date or datetime.today().strftime('%Y-%m-%d')
    start = start_date or (datetime.today() - timedelta(days=365)).strftime('%Y-%m-%d')
    
    # Build the base filters string - always include video filter
    base_filters = f"video=={video_id}"
    if filters:
        base_filters = f"{base_filters};{filters}"
    
    # Group metrics by dimensions, filters, maxResults AND sort to consolidate API calls
    dimension_filter_groups = {}
    key_to_metric_dim_filter_max_sort = {}
    
    for key, metric_config in metric_dims.items():
        # Expect 5-tuple format: (metric, dimensions, filter, maxResults, sort)
        if len(metric_config) != 5:
            raise ValueError(f"Invalid metric configuration for {key}: expected 5-tuple (metric, dimensions, filter, maxResults, sort), got {metric_config}")
            
        metric, dims, metric_filter, max_results, sort = metric_config
        key_to_metric_dim_filter_max_sort[key] = (metric, dims, metric_filter, max_results, sort)
        
        # Build the complete filter string for this metric
        complete_filters = base_filters
        if metric_filter:
            complete_filters = f"{complete_filters};{metric_filter}"
        
        # Group by dimensions, filter combination, maxResults AND sort
        dims_key = dims or ""  # Use empty string for no dimensions
        max_results_key = str(max_results) if max_results else ""
        sort_key = str(sort) if sort else ""
        group_key = f"{dims_key}|||{complete_filters}|||{max_results_key}|||{sort_key}"  # Use ||| as separator
        
        if group_key not in dimension_filter_groups:
            dimension_filter_groups[group_key] = []
        dimension_filter_groups[group_key].append((key, metric))
    
    results = {}
    day_structured_data = {}
    day_metrics = {}
    has_day_dimension = False
    
    # Make consolidated API calls for each dimension-filter-maxResults-sort group
    for group_key, metrics_list in dimension_filter_groups.items():
        if not metrics_list:
            continue
            
        # Parse the group key to get dimensions, filters, maxResults and sort
        parts = group_key.split("|||")
        dims_key = parts[0] if parts[0] else None
        complete_filters = parts[1] if len(parts) > 1 else None
        max_results_str = parts[2] if len(parts) > 2 and parts[2] else None
        sort_str = parts[3] if len(parts) > 3 and parts[3] else None
        max_results = int(max_results_str) if max_results_str else None
        sort = sort_str if sort_str else None
        
        # Extract just the metric names for the API call
        metric_names = [metric for _, metric in metrics_list]
        key_names = [key for key, _ in metrics_list]
        
        try:
            # Make consolidated API call
            consolidated_results = _query_multiple_metrics(
                youtube_analytics_client, start, end,
                metric_names, dims_key,
                filters=complete_filters,
                max_results=max_results,
                sort=sort
            )
            
            # Distribute results back to individual keys
            for i, (key, metric) in enumerate(metrics_list):
                dims = key_to_metric_dim_filter_max_sort[key][1]
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