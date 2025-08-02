"""
Video transcript handling and prompt injection detection.

This module contains functions for fetching video transcripts and checking for
prompt injection attempts in video content.
"""

import bittensor as bt

from bitcast.validator.clients.OpenaiClient import check_for_prompt_injection
from bitcast.validator.platforms.youtube.api.transcript import (
    get_video_transcript as fetch_video_transcript_api,
)
from bitcast.validator.platforms.youtube.utils import _format_error
from bitcast.validator.utils.config import RAPID_API_KEY
from bitcast.validator.utils.error_handling import log_and_raise_api_error


def get_video_transcript(video_id, video_data):
    """
    Get the video transcript.
    
    Args:
        video_id (str): Video ID
        video_data (dict): Video metadata
        
    Returns:
        str or None: Video transcript if available, None otherwise
    """
    transcript = video_data.get("transcript") # transcript will only be in video_data for test runs
    if transcript is None:
        try:
            transcript = fetch_video_transcript_api(video_id, RAPID_API_KEY)
        except Exception as e:
            # Using existing standardized error handling - this pattern is already correct
            log_and_raise_api_error(
                error=e,
                endpoint="rapid-api.transcript",
                params={"bitcast_video_id": video_data.get("bitcastVideoId", "unknown")},
                context="Video transcript fetch"
            )

    if transcript is None:
        log_and_raise_api_error(
            error=RuntimeError("Transcript API returned None"),
            endpoint="rapid-api.transcript",
            params={"bitcast_video_id": video_data.get("bitcastVideoId", "unknown")},
            context="Video transcript fetch"
        )
        
    return str(transcript)


def check_prompt_injection(video_id, video_data, transcript, decision_details):
    """
    Check if the video transcript contains prompt injection attempts.
    
    Args:
        video_id (str): Video ID
        video_data (dict): Video metadata
        transcript (str): Video transcript
        decision_details (dict): Decision details to update
        
    Returns:
        bool: True if no prompt injection detected, False otherwise
    """
    try:
        has_prompt_injection = check_for_prompt_injection(video_data.get("description", ""), transcript)
        
        if has_prompt_injection:
            bt.logging.warning(f"Prompt injection detected in video transcript")
            decision_details["promptInjectionCheck"] = False
            return False
        else:
            decision_details["promptInjectionCheck"] = True
            return True
            
    except Exception as e:
        bt.logging.error(f"Error during prompt injection check: {_format_error(e)}")
        # Fail safe - if we can't check, assume it's not safe
        decision_details["promptInjectionCheck"] = False
        return False 