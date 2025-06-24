import bittensor as bt
import hashlib
from datetime import datetime, timedelta
from tenacity import retry, stop_after_attempt, wait_fixed

# Import global state and helper functions from utils modules  
from bitcast.validator.socials.youtube.utils import state, _format_error
from bitcast.validator.utils.config import ECO_MODE
from bitcast.validator.socials.youtube.config import get_channel_metrics, REVENUE_METRICS

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
    state.analytics_api_call_count += 1
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
    state.analytics_api_call_count += 1
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
    state.data_api_call_count += 1
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
def get_channel_analytics(youtube_analytics_client, start_date, end_date=None):
    """Get comprehensive channel analytics using configurable metrics.
    
    Args:
        youtube_analytics_client: YouTube Analytics API client
        start_date: Start date for analytics (YYYY-MM-DD)
        end_date: End date for analytics (YYYY-MM-DD), defaults to today
        
    Returns:
        Dictionary containing comprehensive channel analytics
    """
    state.analytics_api_call_count += 1
    end = end_date or datetime.today().strftime('%Y-%m-%d')
    
    # Get core metrics from config
    metrics_config = get_channel_metrics(ECO_MODE)
    core_metrics = [metric for _, (metric, dims, _, _, _) in metrics_config.items() if not dims]
    daily_metrics = [metric for _, (metric, dims, _, _, _) in metrics_config.items() if dims == "day"]
    
    # Try all core metrics first, fallback to non-revenue if needed
    try:
        resp = youtube_analytics_client.reports().query(
            ids="channel==MINE", startDate=start_date, endDate=end,
            metrics=",".join(core_metrics)
        ).execute()
        info = _parse_analytics_response(resp, core_metrics)
    except Exception as e:
        bt.logging.warning(f"Revenue metrics failed, retrying without them: {_format_error(e)}")
        state.analytics_api_call_count += 1
        
        # Filter out revenue metrics and retry
        revenue_metric_names = {metric for key, (metric, _, _, _, _) in metrics_config.items() if key in REVENUE_METRICS}
        non_revenue_metrics = [m for m in core_metrics if m not in revenue_metric_names]
        
        resp = youtube_analytics_client.reports().query(
            ids="channel==MINE", startDate=start_date, endDate=end,
            metrics=",".join(non_revenue_metrics)
        ).execute()
        info = _parse_analytics_response(resp, non_revenue_metrics)
        
        # Add missing revenue metrics with default values
        for key in REVENUE_METRICS:
            if key in [k for k, _ in metrics_config.items()]:
                info[key] = 0
    
    if not info:
        raise Exception("No channel analytics data found.")

    # Handle daily metrics separately if they exist
    if daily_metrics:
        try:
            daily_data = _query_multiple_metrics(
                youtube_analytics_client, start_date, end,
                daily_metrics, "day"
            )
            # Add daily metrics to the main info dict
            for metric in daily_metrics:
                if metric in daily_data:
                    info[metric] = daily_data[metric]
        except Exception as e:
            bt.logging.warning(f"Daily metrics failed: {_format_error(e)}")
            # Add default values for failed daily metrics
            for metric in daily_metrics:
                info[metric] = {}

    # Add dimensional data if not in ECO_MODE
    if not ECO_MODE:
        # Traffic source data
        traffic_data = _query_multiple_metrics(
            youtube_analytics_client, start_date, end, 
            ["views", "estimatedMinutesWatched"], 
            "insightTrafficSourceType"
        )
        info.update({
            "trafficSourceViews": traffic_data["views"],
            "trafficSourceMinutes": traffic_data["estimatedMinutesWatched"]
        })
        
        # Country data
        country_data = _query_multiple_metrics(
            youtube_analytics_client, start_date, end,
            ["views", "estimatedMinutesWatched"],
            "country"
        )
        info.update({
            "countryViews": country_data["views"],
            "countryMinutes": country_data["estimatedMinutesWatched"]
        })
    
    return info 