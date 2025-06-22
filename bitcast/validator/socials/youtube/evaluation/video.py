"""
Video evaluation logic for YouTube validation.

This module contains functions for vetting YouTube videos against various criteria
including privacy status, publish date, retention rates, captions, prompt injection,
and brief matching.
"""

import bittensor as bt
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from bitcast.validator.socials.youtube.utils import state, _format_error
from bitcast.validator.socials.youtube.api.video import get_video_data_batch, get_video_analytics
from bitcast.validator.socials.youtube.api.transcript import get_video_transcript
from bitcast.validator.clients.OpenaiClient import evaluate_content_against_brief, check_for_prompt_injection
from bitcast.validator.utils.config import (
    YT_MIN_VIDEO_RETENTION,
    YT_VIDEO_RELEASE_BUFFER,
    ECO_MODE,
    DISCRETE_MODE,
    RAPID_API_KEY
)
from bitcast.validator.socials.youtube.config import get_youtube_metrics, get_advanced_metrics


def get_video_analytics_batch(youtube_analytics_client, video_ids):
    """
    Get analytics data for all videos in batch.
    
    Args:
        youtube_analytics_client: YouTube Analytics API client
        video_ids (list): List of video IDs to get analytics for
        
    Returns:
        dict: Dictionary mapping video_id to analytics data
    """
    video_analytics_dict = {}
    
    # Get all metrics from config using the helper function
    all_metric_dims = get_youtube_metrics(eco_mode=ECO_MODE, for_daily=False)
    
    for video_id in video_ids:
        try:
            # Get all analytics in a single call
            video_analytics = get_video_analytics(youtube_analytics_client, video_id, metric_dims=all_metric_dims)
            video_analytics_dict[video_id] = video_analytics
        except Exception as e:
            bt.logging.error(f"Error getting analytics for video {video_id}: {_format_error(e)}")
            video_analytics_dict[video_id] = {}
    
    return video_analytics_dict


def vet_videos(video_ids, briefs, youtube_data_client, youtube_analytics_client):
    """
    Vet multiple videos against briefs and return results.
    
    Args:
        video_ids (list): List of video IDs to evaluate
        briefs (list): List of brief dictionaries to evaluate against
        youtube_data_client: YouTube Data API client
        youtube_analytics_client: YouTube Analytics API client
        
    Returns:
        tuple: (results, video_data_dict, video_analytics_dict, video_decision_details)
    """
    results = {}
    video_data_dict = {}  # Store video data for all videos
    video_analytics_dict = {}  # Store video analytics for all videos
    video_decision_details = {}  # Store decision details for all videos

    import time
    
    start_time = time.time()
    video_data_dict = get_video_data_batch(youtube_data_client, video_ids, DISCRETE_MODE)
    bt.logging.info(f"Video data batch fetch took {time.time() - start_time:.2f} seconds")

    start_time = time.time()
    video_analytics_dict = get_video_analytics_batch(youtube_analytics_client, video_ids)
    bt.logging.info(f"Video analytics batch fetch took {time.time() - start_time:.2f} seconds")

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


def process_video_vetting(video_id, briefs, youtube_data_client, youtube_analytics_client, 
                         results, video_data, video_analytics, video_decision_details):
    """
    Process the vetting of a single video.
    
    Args:
        video_id (str): Video ID to process
        briefs (list): List of brief dictionaries
        youtube_data_client: YouTube Data API client
        youtube_analytics_client: YouTube Analytics API client
        results (dict): Results dictionary to update
        video_data (dict): Video metadata
        video_analytics (dict): Video analytics data
        video_decision_details (dict): Decision details dictionary to update
    """
    # Get decision details for the video
    vet_result = vet_video(video_id, briefs, video_data, video_analytics)
    decision_details = vet_result["decision_details"]
    results[video_id] = decision_details["contentAgainstBriefCheck"]
    video_decision_details[video_id] = decision_details
    
    # Retrieve advanced metrics only for qualified videos when not in eco mode
    if not ECO_MODE and decision_details.get("anyBriefMatched", False):
        bt.logging.info(f"Fetching advanced metrics.")
        advanced_metrics = get_advanced_metrics()
        advanced_analytics = get_video_analytics(youtube_analytics_client, video_id, metric_dims=advanced_metrics)
        video_analytics.update(advanced_analytics)
    
    valid_checks = [check for check in decision_details["contentAgainstBriefCheck"] if check is not None]
    bt.logging.info(f"Video meets {sum(valid_checks)} briefs.")


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
    
    # Run all the validation checks sequentially
    
    # Check if the video is public
    if not check_video_privacy(video_data, decision_details):
        if handle_check_failure():
            return {"met_brief_ids": [], "decision_details": decision_details, "brief_reasonings": []}
    
    # Check if video was published after brief start date
    if not check_video_publish_date(video_data, briefs, decision_details):
        if handle_check_failure():
            return {"met_brief_ids": [], "decision_details": decision_details, "brief_reasonings": []}
    
    # Check video retention
    if not check_video_retention(video_data, video_analytics, decision_details):
        if handle_check_failure():
            return {"met_brief_ids": [], "decision_details": decision_details, "brief_reasonings": []}
    
    # Check for manual captions
    if not check_manual_captions(video_id, video_data, decision_details):
        if handle_check_failure():
            return {"met_brief_ids": [], "decision_details": decision_details, "brief_reasonings": []}
    
    # Only get transcript and run prompt injection/brief checks if all other checks passed
    met_brief_ids = []
    brief_reasonings = []
    if all_checks_passed:
        # Get transcript only when needed
        transcript = get_video_transcript(video_id, video_data)
        if transcript is None:
            decision_details["video_vet_result"] = False
            decision_details["promptInjectionCheck"] = False
            decision_details["contentAgainstBriefCheck"] = [False] * len(briefs)
            brief_reasonings = ["Failed to get video transcript"] * len(briefs)
        else:
            # Check for prompt injection
            if not check_prompt_injection(video_id, video_data, transcript, decision_details):
                decision_details["video_vet_result"] = False
                decision_details["contentAgainstBriefCheck"] = [False] * len(briefs)
                brief_reasonings = ["Video failed prompt injection check"] * len(briefs)
            else:
                # Evaluate content against briefs only if prompt injection check passed
                met_brief_ids, brief_reasonings = evaluate_content_against_briefs(briefs, video_data, transcript, decision_details)
    else:
        # If any check failed, set all briefs to false and prompt injection to false
        decision_details["promptInjectionCheck"] = False
        decision_details["contentAgainstBriefCheck"] = [False] * len(briefs)
        brief_reasonings = ["Video failed initial checks"] * len(briefs)
    
    # Set anyBriefMatched based on whether any brief matched
    decision_details["anyBriefMatched"] = any(decision_details["contentAgainstBriefCheck"])
    
    # Return the final result
    return {"met_brief_ids": met_brief_ids, "decision_details": decision_details, "brief_reasonings": brief_reasonings}


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
        video_publish_date = datetime.strptime(video_data["publishedAt"], '%Y-%m-%dT%H:%M:%SZ').date()

        # If no briefs, there are no date restrictions
        if not briefs:
            print("No briefs provided - no date restrictions")
            decision_details["publishDateCheck"] = True
            return True
        
        # Find the earliest start date among all briefs
        earliest_brief_date = min(
            datetime.strptime(brief["start_date"], "%Y-%m-%d").date()
            for brief in briefs
        )
        
        # Calculate the earliest allowed publish date by subtracting the buffer days
        earliest_allowed_date = earliest_brief_date - timedelta(days=YT_VIDEO_RELEASE_BUFFER)
        
        if video_publish_date < earliest_allowed_date:
            bt.logging.warning(f"Video was published before the allowed period")
            decision_details["publishDateCheck"] = False
            return False
        
        decision_details["publishDateCheck"] = True
        return True
    except Exception as e:
        bt.logging.error(f"Error checking video publish date: {e}")
        decision_details["publishDateCheck"] = False
        return False


def check_video_retention(video_data, video_analytics, decision_details):
    """
    Check if the video meets the minimum retention criteria.
    
    Args:
        video_data (dict): Video metadata
        video_analytics (dict): Video analytics data
        decision_details (dict): Decision details to update
        
    Returns:
        bool: True if retention is sufficient, False otherwise
    """
    averageViewPercentage = float(video_analytics.get("averageViewPercentage", -1))
    if averageViewPercentage < YT_MIN_VIDEO_RETENTION:
        bt.logging.info(f"Avg retention check failed for video: {video_data['bitcastVideoId']}. {averageViewPercentage} <= {YT_MIN_VIDEO_RETENTION}%.")
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
    if video_data.get("caption"):
        bt.logging.info(f"Manual captions detected for video: {video_data['bitcastVideoId']} - skipping eval")
        decision_details["manualCaptionsCheck"] = False
        return False
    else:
        decision_details["manualCaptionsCheck"] = True
        return True


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
            transcript = get_video_transcript(video_id, RAPID_API_KEY)
        except Exception as e:
            bt.logging.warning(f"Error retrieving transcript for video: {video_data['bitcastVideoId']} - {_format_error(e)}")
            transcript = None

    if transcript is None:
        bt.logging.warning(f"Transcript retrieval failed for video: {video_data['bitcastVideoId']}")
        return None
        
    return str(transcript)


def check_prompt_injection(video_id, video_data, transcript, decision_details):
    """
    Check if the video contains prompt injection.
    
    Args:
        video_id (str): Video ID
        video_data (dict): Video metadata
        transcript (str): Video transcript
        decision_details (dict): Decision details to update
        
    Returns:
        bool: True if no prompt injection detected, False otherwise
    """
    if check_for_prompt_injection(video_data["description"], transcript):
        bt.logging.warning(f"Prompt injection detected for video: {video_data['bitcastVideoId']} - skipping eval")
        decision_details["promptInjectionCheck"] = False
        return False
    else:
        decision_details["promptInjectionCheck"] = True
        return True


def evaluate_content_against_briefs(briefs, video_data, transcript, decision_details):
    """
    Evaluate the video content against each brief concurrently.
    
    Args:
        briefs (list): List of brief dictionaries
        video_data (dict): Video metadata
        transcript (str): Video transcript
        decision_details (dict): Decision details to update
        
    Returns:
        tuple: (met_brief_ids, reasonings)
    """
    met_brief_ids = []
    reasonings = []
    
    # Initialize results lists with the correct size
    brief_results = [False] * len(briefs)
    brief_reasonings = [""] * len(briefs)
    
    # Use ThreadPoolExecutor for concurrent brief evaluations
    max_workers = min(len(briefs), 5)  # Limit to 5 concurrent workers to avoid overwhelming the API
    
    bt.logging.info(f"Evaluating {len(briefs)} briefs concurrently with {max_workers} workers")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all brief evaluation tasks
        future_to_brief = {
            executor.submit(
                evaluate_content_against_brief, 
                brief, 
                video_data['duration'], 
                video_data['description'], 
                transcript
            ): (i, brief)
            for i, brief in enumerate(briefs)
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_brief):
            brief_index, brief = future_to_brief[future]
            try:
                match, reasoning = future.result()
                brief_results[brief_index] = match
                brief_reasonings[brief_index] = reasoning
                if match:
                    met_brief_ids.append(brief["id"])
                # Note: Individual brief completion logs will appear from OpenaiClient
            except Exception as e:
                bt.logging.error(f"Error evaluating brief {brief['id']} for video: {video_data['bitcastVideoId']}: {_format_error(e)}")
                brief_results[brief_index] = False
                brief_reasonings[brief_index] = f"Error during evaluation: {str(e)}"
    
    # Update decision_details with results in correct order
    decision_details["contentAgainstBriefCheck"].extend(brief_results)
    reasonings = brief_reasonings
            
    return met_brief_ids, reasonings 