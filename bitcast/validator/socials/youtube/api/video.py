import bittensor as bt
import time
from datetime import datetime, timedelta
import hashlib
from tenacity import retry, stop_after_attempt, wait_fixed
from googleapiclient.errors import HttpError

from bitcast.validator.utils.config import YOUTUBE_SEARCH_CACHE_EXPIRY, YT_MAX_VIDEOS
from ..cache.search import YouTubeSearchCache
from .channel import _query_multiple_metrics
from ..utils import _format_error

# Retry configuration for YouTube API calls
YT_API_RETRY_CONFIG = {
    'stop': stop_after_attempt(3),
    'wait': wait_fixed(0.5),
    'reraise': True
}

# ============================================================================
# Video Management
# ============================================================================

@retry(**YT_API_RETRY_CONFIG)
def _get_uploads_playlist_id(youtube):
    """Return the channel's 'uploads' playlist ID (1-unit call)."""
    from ..utils import state
    state.data_api_call_count += 1
    resp = youtube.channels().list(mine=True, part="contentDetails").execute()
    items = resp.get("items") or []
    if not items:
        raise RuntimeError("No channel found for the authenticated user")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def _fallback_via_search(youtube, channel_id, cutoff_iso):
    """Quota-heavy fallback path (100 units per request). Uses caching to reduce API calls."""
    from ..utils.state import data_api_call_count
    
    # Create cache key from channel_id and cutoff_iso
    cache_key = f"{channel_id}"
    cache = YouTubeSearchCache.get_cache()
    
    # Check cache first
    cached_vids = cache.get(cache_key)
    if cached_vids is not None:
        bt.logging.info(f"Found {len(cached_vids)} videos in search cache")
        return cached_vids
    
    # Cache miss - perform API search (limited to 3 calls, sorted by date)
    vids, token, call_count = [], None, 0
    max_calls = 2   # limit to most recent 100 videos because the search calls cost 100 credits
    
    while call_count < max_calls:
        from ..utils import state
        state.data_api_call_count += 100  # search.list() uses 100 credits per call
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
    
    # Limit to max videos per account and store in cache
    vids = vids[:YT_MAX_VIDEOS]
    cache.set(cache_key, vids, expire=YOUTUBE_SEARCH_CACHE_EXPIRY)
    
    return vids

@retry(**YT_API_RETRY_CONFIG)
def get_all_uploads(youtube, max_age_days: int = 365):
    """
    Return a list of video IDs uploaded within the last `max_age_days`.

    Strategy:
      1. Use playlistItems.list (cheap) and bail out early when items get old.
      2. If we hit the rare invalidPageToken bug, fall back to search.list.
    """
    from ..utils import state
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
            state.data_api_call_count += 1  # Count each req.execute() call (1 credit each)
            resp = req.execute()
        except HttpError as e:
            if e.resp.status == 404 and "playlistNotFound" in str(e):
                bt.logging.warning("Playlist not found - switching to search method")
                # Need channel ID for fallback
                state.data_api_call_count += 1  # channels.list() call for fallback
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

@retry(**YT_API_RETRY_CONFIG)
def get_video_data_batch(youtube_data_client, video_ids, discrete_mode=False):
    """Fetch basic video information for up to 50 IDs per API call, batching to reduce calls."""
    from ..utils import state
    result = {}
    # Batch in chunks of 50 IDs
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        state.data_api_call_count += 1
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