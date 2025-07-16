"""
YouTube utilities package.

This package contains utility modules for:
- state: Global state management (scored videos, API call counters)
- filters: Brief filtering functions 
- helpers: General helper utility functions
"""

from .state import (
    scored_video_ids,
    data_api_call_count,
    analytics_api_call_count,
    reset_scored_videos,
    is_video_already_scored,
    mark_video_as_scored,
    reset_api_call_counts
)



from .helpers import (
    _format_error
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
    '_format_error'
] 