"""
Global state management for YouTube evaluation.

This module handles:
- Tracking which videos have already been scored to prevent duplicates
- Counting API calls for YouTube Data and Analytics APIs
- Reset functions for clearing state between evaluations
"""

import bittensor as bt

# Global list to track which videos have already been scored
# This list is shared between youtube_scoring.py and youtube_evaluation.py
scored_video_ids = []

# API call counters to track usage of YouTube Data and Analytics APIs for each token
data_api_call_count = 0
analytics_api_call_count = 0


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


def reset_api_call_counts():
    """Reset the API call counters for YouTube Data and Analytics APIs."""
    global data_api_call_count, analytics_api_call_count
    data_api_call_count = 0
    analytics_api_call_count = 0 