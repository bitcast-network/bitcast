"""
Channel operation helpers using standardized error handling.

This module demonstrates how to use the standardized error handlers
for common channel operations while providing practical utility functions.
"""

from typing import Any, Dict, Optional, Tuple

import bittensor as bt

from ..api.channel import get_channel_analytics, get_channel_data
from .error_handlers import handle_channel_data_error, safe_api_operation


def safely_get_channel_data(youtube_data_client, discrete_mode: bool = False) -> Optional[Dict[str, Any]]:
    """
    Safely retrieve channel data with standardized error handling.
    
    Args:
        youtube_data_client: YouTube Data API client
        discrete_mode: Whether to use discrete mode
        
    Returns:
        Channel data dict if successful, None if failed
    """
    @safe_api_operation(
        operation_name="get_channel_data",
        error_handler=lambda e: handle_channel_data_error(e, "data retrieval"),
        default_return=None,
        log_success=True
    )
    def _get_data():
        return get_channel_data(youtube_data_client, discrete_mode)
    
    return _get_data()


def safely_get_channel_analytics(
    youtube_analytics_client, 
    start_date: str, 
    end_date: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Safely retrieve channel analytics with standardized error handling.
    
    Args:
        youtube_analytics_client: YouTube Analytics API client
        start_date: Start date for analytics (YYYY-MM-DD)
        end_date: End date for analytics (YYYY-MM-DD)
        
    Returns:
        Channel analytics dict if successful, None if failed
    """
    @safe_api_operation(
        operation_name="get_channel_analytics",
        error_handler=lambda e: handle_channel_data_error(e, "analytics retrieval"),
        default_return=None,
        log_success=True
    )
    def _get_analytics():
        return get_channel_analytics(youtube_analytics_client, start_date, end_date)
    
    return _get_analytics()


def safely_get_full_channel_info(
    youtube_data_client,
    youtube_analytics_client,
    start_date: str,
    end_date: Optional[str] = None,
    discrete_mode: bool = False
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Safely retrieve both channel data and analytics with consistent error handling.
    
    Args:
        youtube_data_client: YouTube Data API client
        youtube_analytics_client: YouTube Analytics API client
        start_date: Start date for analytics (YYYY-MM-DD)
        end_date: End date for analytics (YYYY-MM-DD)
        discrete_mode: Whether to use discrete mode
        
    Returns:
        Tuple of (channel_data, channel_analytics) - either may be None if failed
    """
    bt.logging.info("Retrieving full channel information")
    
    # Get channel data
    channel_data = safely_get_channel_data(youtube_data_client, discrete_mode)
    if channel_data is None:
        bt.logging.warning("Failed to retrieve channel data")
    
    # Get channel analytics
    channel_analytics = safely_get_channel_analytics(youtube_analytics_client, start_date, end_date)
    if channel_analytics is None:
        bt.logging.warning("Failed to retrieve channel analytics")
    
    # Log summary
    if channel_data and channel_analytics:
        bt.logging.info("Successfully retrieved both channel data and analytics")
    elif channel_data or channel_analytics:
        bt.logging.warning("Partially retrieved channel information")
    else:
        bt.logging.error("Failed to retrieve any channel information")
    
    return channel_data, channel_analytics 