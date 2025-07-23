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
    YT_SCORING_WINDOW,
    YT_REWARD_DELAY,
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


def check_brief_publish_date_range(video_data, brief):
    """
    Check if video publish date falls within brief's allowed date range.
    Buffer days applied only to start date, end date includes full day.
    
    Args:
        video_data (dict): Video metadata containing publishedAt
        brief (dict): Brief dictionary with start_date and end_date
        
    Returns:
        bool: True if publish date is within brief's allowed range, False otherwise
    """
    try:
        # Parse video publish date
        published_at = video_data["publishedAt"]
        if not published_at:
            return False
        video_publish_date = datetime.fromisoformat(
            published_at.replace('Z', '+00:00')
        ).replace(tzinfo=None)
        
        # Parse brief dates and apply buffer to start date only
        brief_start = datetime.fromisoformat(brief["start_date"])
        brief_end = datetime.fromisoformat(brief["end_date"])
        
        allowed_start = brief_start - timedelta(days=YT_VIDEO_RELEASE_BUFFER)
        allowed_end = brief_end.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Check if video is within allowed range
        return allowed_start <= video_publish_date <= allowed_end
        
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


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
            
        # Parse video publish date
        published_at = video_data["publishedAt"]
        video_publish_date = datetime.fromisoformat(
            published_at.replace('Z', '+00:00')
        ).replace(tzinfo=None)
        
        # Find earliest allowed date among all briefs
        earliest_allowed_date = None
        for brief in briefs:
            brief_start = datetime.fromisoformat(brief["start_date"])
            allowed_start = brief_start - timedelta(days=YT_VIDEO_RELEASE_BUFFER)
            if earliest_allowed_date is None or allowed_start < earliest_allowed_date:
                earliest_allowed_date = allowed_start
        
        if video_publish_date < earliest_allowed_date:
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


def check_video_age_limit(video_data, decision_details):
    """
    Check if the video is not older than YT_SCORING_WINDOW + YT_REWARD_DELAY days.
    
    Args:
        video_data (dict): Video metadata containing publishedAt
        decision_details (dict): Decision details to update
        
    Returns:
        bool: True if video is within age limit, False otherwise
    """
    try:
        # Parse video publish date
        published_at = video_data["publishedAt"]
        video_publish_date = datetime.fromisoformat(
            published_at.replace('Z', '+00:00')
        ).replace(tzinfo=None)
        
        # Calculate the cutoff date (start of day that is YT_SCORING_WINDOW + YT_REWARD_DELAY days ago)
        # This ensures videos published any time on the cutoff day are still considered valid
        cutoff_date = (datetime.now() - timedelta(days=YT_SCORING_WINDOW + YT_REWARD_DELAY)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        
        if video_publish_date < cutoff_date:
            bt.logging.warning(f"Video is too old: published {video_publish_date}, cutoff {cutoff_date}")
            decision_details["publishDateCheck"] = False
            return False
        else:
            # Don't override publishDateCheck if it's already False from another check
            if decision_details.get("publishDateCheck") is not False:
                decision_details["publishDateCheck"] = True
            return True
            
    except (KeyError, ValueError, TypeError) as e:
        from bitcast.validator.utils.error_handling import log_and_raise_processing_error
        log_and_raise_processing_error(
            error=e,
            operation="video age limit validation",
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