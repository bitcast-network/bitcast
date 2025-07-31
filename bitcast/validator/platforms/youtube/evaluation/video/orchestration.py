"""
Video evaluation orchestration and workflow coordination.

This module contains the main orchestration functions for video evaluation,
including batch processing, workflow coordination, and helper functions.
"""

import time

import bittensor as bt

from bitcast.validator.platforms.youtube.api.video import (
    get_video_analytics,
    get_video_data_batch,
)
from bitcast.validator.platforms.youtube.config import (
    get_youtube_metrics,
)
from bitcast.validator.platforms.youtube.utils import _format_error, state
from bitcast.validator.utils.config import DISCRETE_MODE, ECO_MODE
from bitcast.validator.utils.error_handling import log_and_raise_api_error

from .brief_matching import (
    evaluate_content_against_briefs,
    map_brief_results_to_original_order,
    prescreen_briefs_for_video,
)
from .transcript import check_prompt_injection, get_video_transcript
from .validation import (
    check_manual_captions,
    check_video_age_limit,
    check_video_privacy,
    check_video_publish_date,
    check_video_retention,
    initialize_decision_details,
)


def get_video_analytics_batch(youtube_analytics_client, video_ids, is_ypp_account=True):
    """
    Get analytics data for all videos in batch.
    
    Args:
        youtube_analytics_client: YouTube Analytics API client
        video_ids (list): List of video IDs
        is_ypp_account (bool): Whether this is a YPP account (affects revenue metrics)
        
    Returns:
        dict: Dictionary mapping video_id to analytics data
    """
    video_analytics_dict = {}
    
    for video_id in video_ids:
        try:
            # Get YouTube metrics for the video (already filtered for YPP status)
            all_metric_dims = get_youtube_metrics(ECO_MODE, is_ypp_account=is_ypp_account)
            
            # Get video analytics - no retry needed since metrics are pre-filtered
            video_analytics = get_video_analytics(youtube_analytics_client, video_id, metric_dims=all_metric_dims)
            
            video_analytics_dict[video_id] = video_analytics
        except Exception as e:
            # Don't log actual YouTube video ID for privacy
            log_and_raise_api_error(
                error=e,
                endpoint="youtube.analytics.reports.query",
                params={"batch_size": len(video_ids)},
                context="YouTube analytics batch fetch"
            )
    
    return video_analytics_dict



def _run_video_validation_checks(video_id, video_data, video_analytics, briefs, decision_details):
    """
    Run basic video validation checks (privacy, publish date, retention, captions).
    
    Args:
        video_id (str): Video ID
        video_data (dict): Video metadata
        video_analytics (dict): Video analytics data
        briefs (list): List of brief dictionaries
        decision_details (dict): Decision details to update
        
    Returns:
        bool: True if all checks passed, False otherwise
    """
    all_checks_passed = True
    
    # Helper function to handle check failures
    def handle_check_failure():
        decision_details["video_vet_result"] = False
        nonlocal all_checks_passed
        all_checks_passed = False
        if ECO_MODE:
            decision_details["contentAgainstBriefCheck"] = [None] * len(briefs)
            return True  # Return early
        return False  # Continue with other checks
    
    # Check if the video is public
    if not check_video_privacy(video_data, decision_details):
        if handle_check_failure():
            return False
    
    # Check if video was published after earliest brief start date
    try:
        if not check_video_publish_date(video_data, briefs, decision_details):
            if handle_check_failure():
                return False
    except RuntimeError as e:
        bt.logging.error(f"System error during publish date check: {e}")
        decision_details["video_vet_result"] = False
        decision_details["publishDateCheck"] = False
        return False
    
    # Check if video is not older than YT_SCORING_WINDOW + YT_REWARD_DELAY days
    try:
        if not check_video_age_limit(video_data, decision_details):
            if handle_check_failure():
                return False
    except RuntimeError as e:
        bt.logging.error(f"System error during video age limit check: {e}")
        decision_details["video_vet_result"] = False
        decision_details["publishDateCheck"] = False
        return False
    
    # Check video retention
    if not check_video_retention(video_data, video_analytics, decision_details):
        if handle_check_failure():
            return False
    
    # Check for manual captions
    if not check_manual_captions(video_id, video_data, decision_details):
        if handle_check_failure():
            return False
    
    return all_checks_passed


def _process_video_transcript_and_briefs(video_id, video_data, briefs, decision_details):
    """
    Process video transcript and evaluate against briefs.
    
    Args:
        video_id (str): Video ID
        video_data (dict): Video metadata
        briefs (list): List of brief dictionaries
        decision_details (dict): Decision details to update
        
    Returns:
        tuple: (met_brief_ids, brief_reasonings)
    """
    met_brief_ids = []
    brief_reasonings = []
    
    # Pre-screen briefs FIRST based on unique_identifier and publish date before expensive operations
    eligible_briefs, prescreening_results, filtered_brief_ids = prescreen_briefs_for_video(
        briefs, video_data.get("description", ""), video_data
    )
    decision_details["preScreeningCheck"] = prescreening_results
    
    # Update publishDateCheck based on individual brief validation results
    # If any brief passed prescreening (including date validation), then publishDateCheck = True
    decision_details["publishDateCheck"] = any(prescreening_results) if prescreening_results else False
    
    # If no briefs passed pre-screening, skip expensive transcript and LLM operations
    if not eligible_briefs:
        # Set default pass for checks that were skipped
        decision_details["promptInjectionCheck"] = True  
        decision_details["contentAgainstBriefCheck"] = [False] * len(briefs)
        brief_reasonings = [
            "Video description does not contain required unique identifier"
            for brief in briefs
        ]
        return [], brief_reasonings
    
    # Get transcript only when needed (briefs passed pre-screening)
    try:
        transcript = get_video_transcript(video_id, video_data)
    except ConnectionError as e:
        bt.logging.error(f"Failed to get video transcript: {e}")
        decision_details["video_vet_result"] = False
        decision_details["promptInjectionCheck"] = False
        decision_details["contentAgainstBriefCheck"] = [False] * len(briefs)
        return [], ["Failed to get video transcript"] * len(briefs)
    
    if transcript is None:
        return [], ["Failed to get video transcript"] * len(briefs)
    
    # Check for prompt injection (only when briefs passed pre-screening)
    if not check_prompt_injection(video_id, video_data, transcript, decision_details):
        decision_details["video_vet_result"] = False
        decision_details["contentAgainstBriefCheck"] = [False] * len(briefs)
        return [], ["Video failed prompt injection check"] * len(briefs)
    
    # Evaluate eligible briefs against content (all pre-screening and safety checks passed)
    if eligible_briefs:
        try:
            # Create a temporary decision_details for eligible briefs only
            temp_decision_details = {"contentAgainstBriefCheck": []}
            met_brief_ids, eligible_brief_reasonings = evaluate_content_against_briefs(
                eligible_briefs, video_data, transcript, temp_decision_details
            )
            eligible_brief_results = temp_decision_details["contentAgainstBriefCheck"]
            
            # Map results back to original brief order
            brief_reasonings, content_against_brief_results = map_brief_results_to_original_order(
                eligible_brief_reasonings, eligible_brief_results, prescreening_results
            )
            
            decision_details["contentAgainstBriefCheck"] = content_against_brief_results
                    
        except RuntimeError as e:
            bt.logging.error(f"System error during brief evaluation: {e}")
            decision_details["video_vet_result"] = False
            decision_details["contentAgainstBriefCheck"] = [False] * len(briefs)
            return [], ["Brief evaluation system error"] * len(briefs)
    
    return met_brief_ids, brief_reasonings


def _compile_evaluation_results(met_brief_ids, decision_details, brief_reasonings):
    """
    Compile final evaluation results.
    
    Args:
        met_brief_ids (list): List of brief IDs that were met
        decision_details (dict): Decision details structure
        brief_reasonings (list): List of reasoning strings for each brief
        
    Returns:
        dict: Final evaluation result
    """
    # Set anyBriefMatched based on whether any brief matched
    decision_details["anyBriefMatched"] = any(decision_details["contentAgainstBriefCheck"])
    
    return {
        "met_brief_ids": met_brief_ids, 
        "decision_details": decision_details, 
        "brief_reasonings": brief_reasonings
    }


def vet_video(video_id, briefs, video_data, video_analytics):
    """
    Vet a single video against all criteria and briefs.
    
    Args:
        video_id (str): Video ID
        briefs (list): List of brief dictionaries to evaluate against
        video_data (dict): Video metadata
        video_analytics (dict): Video analytics data
        
    Returns:
        dict: Dictionary containing met_brief_ids, decision_details, and brief_reasonings
    """
    bt.logging.info(f"=== Evaluating video: {video_data['bitcastVideoId']} ===")
    
    # Initialize decision details structure
    decision_details = initialize_decision_details()
    
    # Step 1: Run basic validation checks
    all_checks_passed = _run_video_validation_checks(video_id, video_data, video_analytics, briefs, decision_details)
    
    # Step 2: Process transcript and evaluate content (only if all checks passed)
    met_brief_ids = []
    brief_reasonings = []
    if all_checks_passed:
        met_brief_ids, brief_reasonings = _process_video_transcript_and_briefs(
            video_id, video_data, briefs, decision_details
        )
    else:
        # If any check failed, set all briefs to false and prompt injection to false
        # Only preserve arrays that were set by ECO_MODE (which sets [None] values)
        eco_mode_array = (decision_details.get("contentAgainstBriefCheck") and 
                          len(decision_details["contentAgainstBriefCheck"]) > 0 and
                          decision_details["contentAgainstBriefCheck"][0] is None)
        
        if not eco_mode_array:
            decision_details["promptInjectionCheck"] = False
            decision_details["preScreeningCheck"] = [False] * len(briefs)
            decision_details["contentAgainstBriefCheck"] = [False] * len(briefs)
            brief_reasonings = ["Video failed initial checks"] * len(briefs)
        else:
            # ECO_MODE already set the arrays, just set the reasonings
            brief_reasonings = ["Video failed initial checks"] * len(briefs)
    
    # Step 3: Compile final results
    return _compile_evaluation_results(met_brief_ids, decision_details, brief_reasonings)


def process_video_vetting(video_id, briefs, youtube_data_client, youtube_analytics_client, 
                         results, video_data, video_analytics, video_decision_details):
    """
    Process vetting for a single video and update results.
    
    Args:
        video_id (str): Video ID
        briefs (list): List of brief dictionaries
        youtube_data_client: YouTube Data API client
        youtube_analytics_client: YouTube Analytics API client
        results (dict): Results dictionary to update
        video_data (dict): Video metadata
        video_analytics (dict): Video analytics data
        video_decision_details (dict): Video decision details to update
    """
    if video_data is None:
        bt.logging.warning(f"No video data for {video_id}, skipping")
        results[video_id] = [False] * len(briefs)
        return
        
    if not video_analytics:
        bt.logging.warning(f"No video analytics for {video_id}, skipping")
        results[video_id] = [False] * len(briefs)
        return
    
    try:
        # Vet the video against all briefs
        video_result = vet_video(video_id, briefs, video_data, video_analytics)
        
        # Extract the boolean results for each brief
        brief_results = video_result["decision_details"]["contentAgainstBriefCheck"]
        results[video_id] = brief_results
        
        # Store decision details for this video
        video_decision_details[video_id] = video_result["decision_details"]
        
    except Exception as e:
        bt.logging.error(f"Error during video vetting: {_format_error(e)}")
        results[video_id] = [False] * len(briefs)


def vet_videos(video_ids, briefs, youtube_data_client, youtube_analytics_client, is_ypp_account=True):
    """
    Vet multiple videos against briefs and return results.
    
    Args:
        video_ids (list): List of video IDs to evaluate
        briefs (list): List of brief dictionaries to evaluate against
        youtube_data_client: YouTube Data API client
        youtube_analytics_client: YouTube Analytics API client
        is_ypp_account (bool): Whether this is a YPP account (affects revenue metrics)
        
    Returns:
        tuple: (results, video_data_dict, video_analytics_dict, video_decision_details)
    """
    # For testing, overwrite video_ids with the specified test IDs
    # video_ids = ["0_zpe2WB3rQ", "tz1WO6sgMQY", "Vfud_OGbJxs"]

    results = {}
    video_data_dict = {}  # Store video data for all videos
    video_analytics_dict = {}  # Store video analytics for all videos
    video_decision_details = {}  # Store decision details for all videos
    
    start_time = time.time()
    video_data_dict = get_video_data_batch(youtube_data_client, video_ids, DISCRETE_MODE)
    bt.logging.info(f"Video data batch fetch took {time.time() - start_time:.2f} seconds")

    start_time = time.time()
    try:
        video_analytics_dict = get_video_analytics_batch(youtube_analytics_client, video_ids, is_ypp_account)
        bt.logging.info(f"Video analytics batch fetch took {time.time() - start_time:.2f} seconds")
    except ConnectionError as e:
        bt.logging.error(f"Failed to fetch video analytics batch: {e}")
        # Return results with all videos marked as failed
        return {video_id: [False] * len(briefs) for video_id in video_ids}, video_data_dict, {}, {}

    for video_id in video_ids:
        try:
            # Check if video has already been scored
            if state.is_video_already_scored(video_id):
                results[video_id] = [False] * len(briefs)
                continue
            
            # Get the video data and analytics for this specific video
            video_data = video_data_dict.get(video_id)
            video_analytics = video_analytics_dict.get(video_id, {})
                
            # Process the video
            process_video_vetting(
                video_id, 
                briefs, 
                youtube_data_client, 
                youtube_analytics_client, 
                results, 
                video_data,
                video_analytics,
                video_decision_details
            )
            
            # Only mark the video as scored if processing was successful
            state.mark_video_as_scored(video_id)
            
        except Exception as e:
            bt.logging.error(f"Error evaluating video {_format_error(e)}")
            # Mark this video as not matching any briefs
            results[video_id] = [False] * len(briefs)
            # Don't mark the video as scored if there was an error

    return results, video_data_dict, video_analytics_dict, video_decision_details 