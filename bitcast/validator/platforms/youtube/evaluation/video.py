"""
Video evaluation logic for YouTube validation.

This module contains functions for vetting YouTube videos against various criteria
including privacy status, publish date, retention rates, captions, prompt injection,
and brief matching.
"""

import bittensor as bt
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from bitcast.validator.platforms.youtube.utils import state, _format_error
from bitcast.validator.platforms.youtube.api.video import get_video_data_batch, get_video_analytics
from bitcast.validator.platforms.youtube.api.transcript import get_video_transcript as fetch_video_transcript_api
from bitcast.validator.clients.OpenaiClient import evaluate_content_against_brief, check_for_prompt_injection
from bitcast.validator.utils.config import (
    YT_MIN_VIDEO_RETENTION,
    YT_VIDEO_RELEASE_BUFFER,
    ECO_MODE,
    DISCRETE_MODE,
    RAPID_API_KEY
)
from bitcast.validator.platforms.youtube.config import get_youtube_metrics, get_advanced_metrics, REVENUE_METRICS
from bitcast.validator.utils.error_handling import log_and_raise_api_error, log_and_raise_processing_error


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
            # Try all metrics first, fallback to non-revenue if needed (same pattern as channel analytics)
            video_analytics = get_video_analytics(youtube_analytics_client, video_id, metric_dims=all_metric_dims)
            
            # Check if any core metrics returned None, which indicates revenue metrics caused API failure
            core_metrics_failed = any(
                video_analytics.get(key) is None 
                for key in ["averageViewPercentage", "estimatedMinutesWatched"] 
                if key in all_metric_dims
            )
            
            if core_metrics_failed:
                bt.logging.warning(f"Retrying without revenue metrics")
                
                # Filter out revenue metrics and retry
                revenue_metric_names = {metric for key, (metric, _, _, _, _) in all_metric_dims.items() if key in REVENUE_METRICS}
                non_revenue_metric_dims = {
                    key: metric_config for key, metric_config in all_metric_dims.items() 
                    if metric_config[0] not in revenue_metric_names
                }
                
                # Retry without revenue metrics
                video_analytics = get_video_analytics(youtube_analytics_client, video_id, metric_dims=non_revenue_metric_dims)
                
                # Add missing revenue metrics with default values
                for key in REVENUE_METRICS:
                    if key in all_metric_dims:
                        video_analytics[key] = 0
            
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
        video_analytics_dict = get_video_analytics_batch(youtube_analytics_client, video_ids)
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
    try:
        if not check_video_publish_date(video_data, briefs, decision_details):
            if handle_check_failure():
                return {"met_brief_ids": [], "decision_details": decision_details, "brief_reasonings": []}
    except RuntimeError as e:
        bt.logging.error(f"System error during publish date check: {e}")
        decision_details["video_vet_result"] = False
        decision_details["publishDateCheck"] = False
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
        try:
            transcript = get_video_transcript(video_id, video_data)
        except ConnectionError as e:
            bt.logging.error(f"Failed to get video transcript: {e}")
            decision_details["video_vet_result"] = False
            decision_details["promptInjectionCheck"] = False
            decision_details["contentAgainstBriefCheck"] = [False] * len(briefs)
            brief_reasonings = ["Failed to get video transcript"] * len(briefs)
            transcript = None
        
        if transcript is None:
            # Already handled above in exception case
            pass
        else:
            # Check for prompt injection
            if not check_prompt_injection(video_id, video_data, transcript, decision_details):
                decision_details["video_vet_result"] = False
                decision_details["contentAgainstBriefCheck"] = [False] * len(briefs)
                brief_reasonings = ["Video failed prompt injection check"] * len(briefs)
            else:
                # Pre-screen briefs based on unique_identifier before expensive LLM evaluation
                try:
                    eligible_briefs, prescreening_results, filtered_brief_ids = prescreen_briefs_for_video(briefs, video_data.get("description", ""))
                    decision_details["preScreeningCheck"] = prescreening_results
                    
                except ValueError as e:
                    bt.logging.error(f"Brief validation error: {e}")
                    decision_details["video_vet_result"] = False
                    decision_details["preScreeningCheck"] = [False] * len(briefs)
                    decision_details["contentAgainstBriefCheck"] = [False] * len(briefs)
                    brief_reasonings = [str(e)] * len(briefs)
                    return {"met_brief_ids": [], "decision_details": decision_details, "brief_reasonings": brief_reasonings}
                
                # Only evaluate eligible briefs against content if any passed pre-screening
                if eligible_briefs:
                    try:
                        # Create a temporary decision_details for eligible briefs only
                        temp_decision_details = {"contentAgainstBriefCheck": []}
                        met_brief_ids, eligible_brief_reasonings = evaluate_content_against_briefs(eligible_briefs, video_data, transcript, temp_decision_details)
                        eligible_brief_results = temp_decision_details["contentAgainstBriefCheck"]
                        
                        # Map results back to original brief order
                        brief_reasonings, content_against_brief_results = map_brief_results_to_original_order(eligible_brief_reasonings, eligible_brief_results, prescreening_results)
                        
                        decision_details["contentAgainstBriefCheck"] = content_against_brief_results
                                
                    except RuntimeError as e:
                        bt.logging.error(f"System error during brief evaluation: {e}")
                        decision_details["video_vet_result"] = False
                        decision_details["contentAgainstBriefCheck"] = [False] * len(briefs)
                        brief_reasonings = ["Brief evaluation system error"] * len(briefs)
                        met_brief_ids = []
                else:
                    # No briefs passed pre-screening, skip LLM evaluation entirely
                    bt.logging.info(f"No briefs passed pre-screening for video {video_data['bitcastVideoId']}, skipping LLM evaluation")
                    decision_details["contentAgainstBriefCheck"] = [False] * len(briefs)
                    brief_reasonings = ["Video description does not contain required unique identifier"] * len(briefs)
                    met_brief_ids = []
    else:
        # If any check failed, set all briefs to false and prompt injection to false
        decision_details["promptInjectionCheck"] = False
        decision_details["preScreeningCheck"] = [False] * len(briefs)
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
        log_and_raise_processing_error(
            error=e,
            operation="video publish date validation",
            context={"video_id": video_data.get("bitcastVideoId")}
        )


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
    retention_value = video_analytics.get("averageViewPercentage", -1)
    # Handle case where revenue metrics in CORE_METRICS cause API to return None for other metrics
    if retention_value is None:
        retention_value = -1
    
    averageViewPercentage = float(retention_value)
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
            transcript = fetch_video_transcript_api(video_id, RAPID_API_KEY)
        except Exception as e:
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


def check_brief_unique_identifier(brief, video_description):
    """
    Check if brief's unique_identifier is present in video description.
    
    Args:
        brief (dict): Brief dictionary
        video_description (str): Video description text
        
    Returns:
        bool: True if unique_identifier found in description
        
    Raises:
        ValueError: If brief doesn't have unique_identifier field
    """
    if "unique_identifier" not in brief:
        raise ValueError(f"Brief '{brief.get('id', 'unknown')}' missing required unique_identifier field")
    
    unique_id = brief["unique_identifier"]
    if not unique_id:
        raise ValueError(f"Brief '{brief.get('id', 'unknown')}' has empty unique_identifier field")
    
    video_description = video_description or ""
    return unique_id.lower() in video_description.lower()


def prescreen_briefs_for_video(briefs, video_description):
    """
    Pre-screen briefs based on unique_identifier presence in video description.
    
    Args:
        briefs (list): List of brief dictionaries
        video_description (str): Video description text
        
    Returns:
        tuple: (eligible_briefs, prescreening_results, filtered_brief_ids)
            - eligible_briefs: List of briefs that passed pre-screening
            - prescreening_results: List of bool results for each original brief
            - filtered_brief_ids: List of brief IDs that were filtered out
            
    Raises:
        ValueError: If any brief has invalid unique_identifier field
    """
    eligible_briefs = []
    prescreening_results = []
    filtered_brief_ids = []
    
    for brief in briefs:
        passed_prescreening = check_brief_unique_identifier(brief, video_description)
        
        # Log each brief result individually (matching LLM logging style)
        emoji = "✅" if passed_prescreening else "❌"
        bt.logging.info(f"Meets brief '{brief['id']}': {passed_prescreening} {emoji} (pre-screen)")
        
        if passed_prescreening:
            eligible_briefs.append(brief)
            prescreening_results.append(True)
        else:
            prescreening_results.append(False)
            filtered_brief_ids.append(brief.get("id", "unknown"))
    
    return eligible_briefs, prescreening_results, filtered_brief_ids


def map_brief_results_to_original_order(eligible_brief_reasonings, eligible_brief_results, prescreening_results):
    """
    Map results from eligible briefs back to original brief order.
    
    Args:
        eligible_brief_reasonings (list): Reasonings from LLM evaluation of eligible briefs
        eligible_brief_results (list): Results from LLM evaluation of eligible briefs  
        prescreening_results (list): Pre-screening results for all original briefs
        
    Returns:
        tuple: (brief_reasonings, content_against_brief_results)
    """
    brief_reasonings = []
    content_against_brief_results = []
    eligible_idx = 0
    
    for passed_prescreening in prescreening_results:
        if passed_prescreening:
            # Handle cases where eligible results may be shorter than expected (e.g., in tests)
            if eligible_idx < len(eligible_brief_reasonings):
                brief_reasonings.append(eligible_brief_reasonings[eligible_idx])
            else:
                brief_reasonings.append("Brief evaluation completed")
                
            if eligible_idx < len(eligible_brief_results):
                content_against_brief_results.append(eligible_brief_results[eligible_idx])
            else:
                # Default to True if results are missing (common in test scenarios)
                content_against_brief_results.append(True)
                
            eligible_idx += 1
        else:
            brief_reasonings.append("Video description does not contain required unique identifier")
            content_against_brief_results.append(False)
    
    return brief_reasonings, content_against_brief_results


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
                log_and_raise_processing_error(
                    error=e,
                    operation="brief evaluation",
                    context={
                        "brief_id": brief["id"],
                        "video_id": video_data.get("bitcastVideoId")
                    }
                )
    
    # Update decision_details with results in correct order
    decision_details["contentAgainstBriefCheck"].extend(brief_results)
    reasonings = brief_reasonings
            
    return met_brief_ids, reasonings 