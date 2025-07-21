"""
Video validation checks for YouTube evaluation.

This module contains functions for validating YouTube videos against basic criteria
including privacy status, publish date, retention rates, and manual captions.
"""

from datetime import datetime, timedelta

import bittensor as bt

from bitcast.validator.utils.config import (
    YT_MIN_VIDEO_RETENTION,
    YT_VIDEO_RELEASE_BUFFER,
)


def initialize_decision_details():
    """
    Initialize the decision details structure.
    
    Returns:
        dict: Empty decision details structure
    """
    return {
        "averageViewPercentageCheck": None,
        "manualCaptionsCheck": None,
        "promptInjectionCheck": None,
        "preScreeningCheck": [],
        "contentAgainstBriefCheck": [],
        "publicVideo": None,
        "publishDateCheck": None,
        "video_vet_result": True
    }


def check_video_privacy(video_data, decision_details):
    """
    Check if the video is public.
    
    Args:
        video_data (dict): Video metadata
        decision_details (dict): Decision details to update
        
    Returns:
        bool: True if video is public, False otherwise
    """
    if video_data.get("privacyStatus") != "public":
        bt.logging.warning(f"Video is not public")
        decision_details["publicVideo"] = False
        return False
    else:
        decision_details["publicVideo"] = True
        return True


def check_video_publish_date(video_data, briefs, decision_details):
    """
    Check if the video was published after the earliest brief's start date (minus buffer days).
    
    Args:
        video_data (dict): Video metadata containing publishedAt
        briefs (list): List of brief dictionaries with start_date
        decision_details (dict): Decision details to update
        
    Returns:
        bool: True if publish date is valid, False otherwise
    """
    try:
        # Find the earliest start date among all briefs
        if not briefs:
            # No briefs means no date restrictions
            decision_details["publishDateCheck"] = True
            return True
            
        brief_start_dates = [datetime.fromisoformat(brief["start_date"]) for brief in briefs]
        earliest_start_date = min(brief_start_dates)
        
        # Account for buffer days before the earliest start date
        allowed_publish_date = earliest_start_date - timedelta(days=YT_VIDEO_RELEASE_BUFFER)
        
        # Parse video publish date (remove timezone for comparison)
        video_publish_date = datetime.fromisoformat(video_data["publishedAt"].replace('Z', '+00:00')).replace(tzinfo=None)
        
        if video_publish_date < allowed_publish_date:
            bt.logging.warning(f"Video published before allowed date")
            decision_details["publishDateCheck"] = False
            return False
        else:
            decision_details["publishDateCheck"] = True
            return True
            
    except (KeyError, ValueError, TypeError) as e:
        from bitcast.validator.utils.error_handling import log_and_raise_processing_error
        log_and_raise_processing_error(
            error=e,
            operation="video publish date validation",
            context={"video_id": video_data.get("bitcastVideoId", "unknown")}
        )


def check_video_retention(video_data, video_analytics, decision_details):
    """
    Check if the video meets minimum retention requirements.
    
    Args:
        video_data (dict): Video metadata
        video_analytics (dict): Video analytics data
        decision_details (dict): Decision details to update
        
    Returns:
        bool: True if retention is acceptable, False otherwise
    """
    average_view_percentage = video_analytics.get("averageViewPercentage", 0)
    
    if average_view_percentage < YT_MIN_VIDEO_RETENTION:
        bt.logging.warning(f"Video retention too low: {average_view_percentage}% < {YT_MIN_VIDEO_RETENTION}%")
        decision_details["averageViewPercentageCheck"] = False
        return False
    else:
        decision_details["averageViewPercentageCheck"] = True
        return True


def check_manual_captions(video_id, video_data, decision_details):
    """
    Check if the video has manual captions.
    
    Args:
        video_id (str): Video ID
        video_data (dict): Video metadata
        decision_details (dict): Decision details to update
        
    Returns:
        bool: True if no manual captions (passes check), False if has manual captions
    """
    caption_status = video_data.get("caption", "false")
    
    if caption_status == "true":
        bt.logging.warning(f"Video has manual captions which are not allowed")
        decision_details["manualCaptionsCheck"] = False
        return False
    else:
        decision_details["manualCaptionsCheck"] = True
        return True 