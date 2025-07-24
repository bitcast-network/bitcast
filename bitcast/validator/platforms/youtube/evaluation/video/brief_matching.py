"""
Brief matching and evaluation logic for YouTube videos.

This module contains functions for evaluating video content against briefs,
including unique identifier checking, prescreening, concurrent evaluation,
and priority-based selection.
"""

from concurrent.futures import as_completed, ThreadPoolExecutor

import bittensor as bt

from bitcast.validator.clients.OpenaiClient import evaluate_content_against_brief
from bitcast.validator.utils.error_handling import log_and_raise_processing_error
from .validation import check_brief_publish_date_range


def check_brief_unique_identifier(brief, video_description):
    """
    Check if the video description contains the brief's unique identifier.
    
    Args:
        brief (dict): Brief dictionary with unique_identifier
        video_description (str): Video description text
        
    Returns:
        bool: True if unique identifier found, False otherwise
        
    Raises:
        ValueError: If unique_identifier field is missing or empty
    """
    # Check if unique_identifier field exists
    if "unique_identifier" not in brief:
        raise ValueError(f"Brief '{brief.get('id', 'unknown')}' is missing required unique_identifier field")
    
    unique_identifier = brief["unique_identifier"].strip()
    
    # Check if unique_identifier field is empty
    if not unique_identifier:
        raise ValueError(f"Brief '{brief.get('id', 'unknown')}' has empty unique_identifier field")
    
    # Handle None video description
    if video_description is None:
        return False
    
    # Check if the unique identifier appears in the video description (case-insensitive)
    if unique_identifier.lower() in video_description.lower():
        return True
    else:
        return False


def prescreen_briefs_for_video(briefs, video_description, video_data):
    """
    Pre-screen briefs based on unique identifier and publish date before expensive LLM evaluation.
    
    Args:
        briefs (list): List of brief dictionaries
        video_description (str): Video description text
        video_data (dict): Video metadata containing publishedAt
        
    Returns:
        tuple: (eligible_briefs, prescreening_results, filtered_brief_ids)
    """
    eligible_briefs = []
    prescreening_results = []
    filtered_brief_ids = []
    
    for brief in briefs:
        passes_prescreen = False
        reason = ""
        
        try:
            # Check unique identifier first
            passes_unique_id = check_brief_unique_identifier(brief, video_description)
            if not passes_unique_id:
                reason = "unique identifier"
            else:
                # Check publish date if unique ID passes
                passes_date_validation = check_brief_publish_date_range(video_data, brief)
                if not passes_date_validation:
                    reason = "publish date"
                else:
                    passes_prescreen = True
                    
        except ValueError as e:
            bt.logging.warning(f"Brief validation error during prescreening: {e}")
            passes_prescreen = False
            reason = "validation error"
        
        prescreening_results.append(passes_prescreen)
        
        if passes_prescreen:
            eligible_briefs.append(brief)
        else:
            filtered_brief_ids.append(brief["id"])
            bt.logging.info(f"Meets brief '{brief['id']}': False ❌ (pre-screen: {reason})")
        
    return eligible_briefs, prescreening_results, filtered_brief_ids


def map_brief_results_to_original_order(eligible_brief_reasonings, eligible_brief_results, prescreening_results):
    """
    Map brief evaluation results back to the original brief order.
    
    Args:
        eligible_brief_reasonings (list): Reasonings for eligible briefs only
        eligible_brief_results (list): Results for eligible briefs only
        prescreening_results (list): Prescreening results for all briefs
        
    Returns:
        tuple: (brief_reasonings, content_against_brief_results) in original order
    """
    brief_reasonings = []
    content_against_brief_results = []
    eligible_index = 0
    
    for passed_prescreen in prescreening_results:
        if passed_prescreen:
            # This brief was eligible, use the result from evaluation
            if eligible_index < len(eligible_brief_reasonings):
                brief_reasonings.append(eligible_brief_reasonings[eligible_index])
                content_against_brief_results.append(eligible_brief_results[eligible_index])
                eligible_index += 1
            else:
                # Fallback if there's a mismatch
                brief_reasonings.append("Evaluation result missing")
                content_against_brief_results.append(False)
        else:
            # This brief was filtered out by prescreening
            brief_reasonings.append("Video description does not contain required unique identifier")
            content_against_brief_results.append(False)
    
    return brief_reasonings, content_against_brief_results


def select_highest_priority_brief(matching_briefs, brief_results):
    """
    Select the highest priority brief from matching briefs using weight * boost.
    
    Args:
        matching_briefs (list): List of brief dictionaries
        brief_results (list): List of boolean results indicating which briefs matched
        
    Returns:
        tuple: (selected_index, selected_brief) or (None, None) if no matches
    """
    if not any(brief_results):
        return None, None
    
    best_brief = None
    best_index = None
    best_priority = -1
    
    for i, (brief, matched) in enumerate(zip(matching_briefs, brief_results)):
        if matched:
            weight = brief.get("weight", 0)
            boost = brief.get("boost", 1.0)
            priority = weight * boost
            
            if priority > best_priority:
                best_priority = priority
                best_brief = brief
                best_index = i
    
    return best_index, best_brief


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
    
    # Apply single brief matching limitation using weight-based priority
    selected_index, selected_brief = select_highest_priority_brief(briefs, brief_results)
    
    # Reset all results and only set the selected brief to True
    final_brief_results = [False] * len(briefs)
    final_met_brief_ids = []
    
    if selected_index is not None and selected_brief is not None:
        final_brief_results[selected_index] = True
        final_met_brief_ids.append(selected_brief["id"])
        
        # Log the selection with weight and boost information
        total_matches = sum(brief_results)
        selected_weight = selected_brief.get("weight", 0)
        selected_boost = selected_brief.get("boost", 1.0)
        priority_value = selected_weight * selected_boost
        bt.logging.info(
            f"Selected brief '{selected_brief['id']}' (weight: {selected_weight}, boost: {selected_boost}, priority: {priority_value}) "
            f"from {total_matches} matching briefs for video: {video_data.get('bitcastVideoId')}"
        )
    else:
        bt.logging.info(f"No briefs matched for video: {video_data.get('bitcastVideoId')}")
    
    # Update decision_details with final results
    decision_details["contentAgainstBriefCheck"].extend(final_brief_results)
    reasonings = brief_reasonings
            
    return final_met_brief_ids, reasonings 