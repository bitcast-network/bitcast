"""
YouTube utilities package.

This package contains utility modules for:
- state: Global state management (scored videos, API call counters)
- filters: Brief filtering functions 
- helpers: General helper utility functions
"""

from .error_handlers import (
    handle_analytics_processing_error,
    handle_authentication_error,
    handle_channel_data_error,
    handle_transcript_api_error,
    handle_video_data_validation_error,
    handle_youtube_api_error,
    safe_api_operation,
    with_retry_error_handling,
)
from .helpers import _format_error
from .state import (
    analytics_api_call_count,
    data_api_call_count,
    is_video_already_scored,
    mark_video_as_scored,
    reset_api_call_counts,
    reset_scored_videos,
    scored_video_ids,
)

__all__ = [
    # State management
    'scored_video_ids',
    'data_api_call_count', 
    'analytics_api_call_count',
    'reset_scored_videos',
    'is_video_already_scored',
    'mark_video_as_scored',
    'reset_api_call_counts',
    
    # Helpers
    '_format_error',
    
    # Error handlers
    'handle_youtube_api_error',
    'handle_transcript_api_error',
    'handle_video_data_validation_error',
    'handle_channel_data_error',
    'handle_authentication_error',
    'handle_analytics_processing_error',
    'safe_api_operation',
    'with_retry_error_handling'
] 