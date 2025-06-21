import bittensor as bt
import hashlib
from datetime import datetime, timedelta
from tenacity import retry, stop_after_attempt, wait_fixed

# Import global state from the main module
from bitcast.validator.socials.youtube import youtube_utils
from bitcast.validator.socials.youtube.utils import _format_error

# Retry configuration for YouTube API calls
YT_API_RETRY_CONFIG = {
    'stop': stop_after_attempt(3),
    'wait': wait_fixed(0.5),
    'reraise': True
}

# _format_error function now imported from utils.helpers

@retry(**YT_API_RETRY_CONFIG)
def _query(client, start_date, end_date, metric, dimensions=None, filters=None, max_results=None, sort=None):
    """Execute a single metric query against YouTube Analytics API.
    
    Args:
        client: YouTube Analytics API client
        start_date: Start date for query (YYYY-MM-DD)
        end_date: End date for query (YYYY-MM-DD) 
        metric: Single metric name to fetch
        dimensions: Optional dimensions for grouping
        filters: Optional filters for the query
        max_results: Optional maximum number of results
        sort: Optional sort parameter
        
    Returns:
        Query result - list for non-dimensional, dict for dimensional queries
    """
    youtube_utils.analytics_api_call_count += 1
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
    youtube_utils.analytics_api_call_count += 1
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
    """Get basic channel information.
    
    Args:
        youtube_data_client: YouTube Data API client
        discrete_mode: Whether to use discrete channel IDs for privacy
        
    Returns:
        Dictionary containing channel information
    """
    youtube_utils.data_api_call_count += 1
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
    """Helper to parse analytics response into structured data.
    
    Args:
        resp: API response object
        metrics_list: List of metric names that were queried
        dimensions: Dimensions string that was used in query
        
    Returns:
        Parsed response data - dict for single row, list of dicts for multiple rows
    """
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
    """Get comprehensive channel analytics including traffic sources.
    
    Args:
        youtube_analytics_client: YouTube Analytics API client
        start_date: Start date for analytics (YYYY-MM-DD)
        end_date: End date for analytics (YYYY-MM-DD), defaults to today
        dimensions: Optional dimensions for grouping data
        
    Returns:
        Dictionary containing comprehensive channel analytics
    """
    youtube_utils.analytics_api_call_count += 1
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
        youtube_utils.analytics_api_call_count += 1
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