import bittensor as bt
from datetime import datetime, timedelta
import time

from bitcast.validator.platforms.youtube.utils import state
from bitcast.validator.platforms.youtube.api.video import get_all_uploads
from bitcast.validator.platforms.youtube.api import initialize_youtube_clients, get_channel_data, get_channel_analytics
from bitcast.validator.platforms.youtube.utils import _format_error
from bitcast.validator.platforms.youtube.evaluation import (
    vet_channel,
    vet_videos,
    calculate_video_score
)
from bitcast.validator.platforms.youtube.evaluation.dual_scoring import get_cached_ratio
from bitcast.validator.utils.config import (
    YT_MIN_SUBS, 
    YT_MIN_CHANNEL_AGE, 
    YT_MIN_CHANNEL_RETENTION, 
    YT_MIN_VIDEO_RETENTION, 
    YT_REWARD_DELAY, 
    YT_ROLLING_WINDOW,
    YT_MAX_VIDEOS_PER_DEDICATED_BRIEF,
    DISCRETE_MODE,
    YT_LOOKBACK,
    ECO_MODE,
    RAPID_API_KEY
)

import bitcast.validator.clients.OpenaiClient as openai_client_module

def eval_youtube(creds, briefs, min_stake=False):
    bt.logging.info(f"Scoring Youtube Content")
    
    # Initialize the result structure and get API clients
    result, youtube_data_client, youtube_analytics_client = initialize_youtube_evaluation(creds, briefs)
    # Reset API call counters for this token evaluation
    state.reset_api_call_counts()
    openai_client_module.reset_openai_request_count()
    start = time.perf_counter()
    
    # Get and process channel information
    channel_data, channel_analytics = get_channel_information(youtube_data_client, youtube_analytics_client)
    if channel_data is None or channel_analytics is None:
        # Attach API call counts on early exit
        elapsed = time.perf_counter() - start
        result["performance_stats"] = {
            "data_api_calls": state.data_api_call_count,
            "analytics_api_calls": state.analytics_api_call_count,
            "openai_requests": openai_client_module.openai_request_count,
            "evaluation_time_s": elapsed
        }
        return result
    
    # Store channel details in the result
    result["yt_account"]["details"] = channel_data
    result["yt_account"]["analytics"] = channel_analytics
    
    # Vet the channel and store the result
    channel_vet_result, is_blacklisted = vet_channel(channel_data, channel_analytics, min_stake)
    result["yt_account"]["channel_vet_result"] = channel_vet_result
    result["yt_account"]["blacklisted"] = is_blacklisted

    if not channel_vet_result and ECO_MODE:
        bt.logging.info("Channel vetting failed and ECO_MODE is enabled - exiting early")
        # Attach API call counts on early exit
        elapsed = time.perf_counter() - start
        result["performance_stats"] = {
            "data_api_calls": state.data_api_call_count,
            "analytics_api_calls": state.analytics_api_call_count,
            "openai_requests": openai_client_module.openai_request_count,
            "evaluation_time_s": elapsed
        }
        return result

    # Process videos and update the result
    result = process_videos(youtube_data_client, youtube_analytics_client, briefs, result)
    # Attach performance stats to result after full evaluation
    elapsed = time.perf_counter() - start
    result["performance_stats"] = {
        "data_api_calls": state.data_api_call_count,
        "analytics_api_calls": state.analytics_api_call_count,
        "openai_requests": openai_client_module.openai_request_count,
        "evaluation_time_s": elapsed
    }
    
    return result

def initialize_youtube_evaluation(creds, briefs):
    """Initialize the result structure and YouTube API clients."""
    # Initialize scores with brief IDs as keys
    scores = {brief["id"]: 0 for brief in briefs}
    
    # Initialize the comprehensive result structure
    result = {
        "yt_account": {
            "details": None,
            "analytics": None,
            "channel_vet_result": None
        },
        "videos": {},
        "scores": scores
    }
    
    youtube_data_client, youtube_analytics_client = initialize_youtube_clients(creds)
    return result, youtube_data_client, youtube_analytics_client

def get_channel_information(youtube_data_client, youtube_analytics_client):
    """Retrieve channel data and analytics."""
    try:
        channel_data = get_channel_data(youtube_data_client, DISCRETE_MODE)
        
        # Calculate date range for the last YT_LOOKBACK days
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=YT_LOOKBACK)).strftime('%Y-%m-%d')
        
        channel_analytics = get_channel_analytics(youtube_analytics_client, start_date=start_date, end_date=end_date)
        return channel_data, channel_analytics
    except Exception as e:
        bt.logging.warning(f"An error occurred while retrieving YouTube data: {_format_error(e)}")
        return None, None

def apply_video_limits(briefs, result):
    """
    Apply video scoring limits for dedicated briefs.
    
    For each dedicated brief, limits the number of videos that can receive scores per account.
    Only the top N scoring videos keep their scores, the rest are set to 0.
    
    Args:
        briefs (list): List of brief dictionaries
        result (dict): Video evaluation result structure
    """
    for brief in briefs:
        brief_id = brief["id"]
        brief_format = brief.get("format", "dedicated")
        
        # Only apply limits to dedicated briefs
        if brief_format != "dedicated":
            continue
            
        # Find all videos that scored > 0 for this brief
        scored_videos = []
        for video_id, video_data in result["videos"].items():
            if video_data.get("matching_brief_ids") and brief_id in video_data["matching_brief_ids"]:
                video_score = video_data.get("score", 0)
                if video_score > 0:
                    scored_videos.append({
                        "video_id": video_id,
                        "score": video_score,
                        "bitcast_video_id": video_data["details"].get("bitcastVideoId", video_id)
                    })
        
        # Check if we need to apply limits
        if len(scored_videos) <= YT_MAX_VIDEOS_PER_DEDICATED_BRIEF:
            continue
            
        # Sort videos by score (descending) - ties handled by natural list order (doesn't matter which)
        scored_videos.sort(key=lambda x: x["score"], reverse=True)
        
        # Keep top N videos, zero out the rest
        videos_to_limit = scored_videos[YT_MAX_VIDEOS_PER_DEDICATED_BRIEF:]
        original_total_score = result["scores"][brief_id]
        score_reduction = 0
        
        for video_info in videos_to_limit:
            video_id = video_info["video_id"]
            original_score = video_info["score"]
            
            # Set video score to 0
            result["videos"][video_id]["score"] = 0
            
            # Add metadata to track this was limited
            if "score_limited" not in result["videos"][video_id]:
                result["videos"][video_id]["score_limited"] = {}
            result["videos"][video_id]["score_limited"][brief_id] = {
                "original_score": original_score,
                "reason": "exceeded_dedicated_brief_limit"
            }
            
            score_reduction += original_score
        
        # Update the total score for this brief
        result["scores"][brief_id] = original_total_score - score_reduction
        
        # Log the limiting action
        limited_video_ids = [v["bitcast_video_id"] for v in videos_to_limit]
        bt.logging.info(
            f"Applied video limit for dedicated brief '{brief_id}': "
            f"kept top {YT_MAX_VIDEOS_PER_DEDICATED_BRIEF} of {len(scored_videos)} videos, "
            f"limited {len(videos_to_limit)} videos: {limited_video_ids}, "
            f"score reduced by {score_reduction:.4f}"
        )

def process_videos(youtube_data_client, youtube_analytics_client, briefs, result):
    """Process videos, calculate scores, and update the result structure."""
    try:
        # Get YPP status from channel analytics
        is_ypp_account = result["yt_account"]["analytics"].get("ypp", False)
        
        # Get cached ratio for Non-YPP accounts
        cached_ratio = get_cached_ratio()
        
        bt.logging.info(f"Account YPP status: {is_ypp_account}, Cached ratio available: {cached_ratio is not None}")
        
        video_ids = get_all_uploads(youtube_data_client, YT_LOOKBACK)
        
        # Vet videos and store the results
        video_matches, video_data_dict, video_analytics_dict, video_decision_details = vet_videos(
            video_ids, briefs, youtube_data_client, youtube_analytics_client
        )
        
        # Get channel analytics for median cap calculation
        channel_analytics = result["yt_account"]["analytics"]
        
        # Process each video and update the result
        for video_id in video_ids:
            if video_id in video_data_dict and video_id in video_analytics_dict:
                process_single_video(
                    video_id, 
                    video_data_dict, 
                    video_analytics_dict, 
                    video_matches, 
                    video_decision_details, 
                    briefs, 
                    youtube_analytics_client, 
                    result,
                    is_ypp_account,
                    cached_ratio,
                    channel_analytics
                )
        
        # Apply video scoring limits for dedicated briefs
        apply_video_limits(briefs, result)
        
        # If channel vetting failed, set all scores to 0 but keep the video data
        if not result["yt_account"]["channel_vet_result"]:
            result["scores"] = {brief["id"]: 0 for brief in briefs}
            
    except Exception as e:
        bt.logging.error(f"Error during video evaluation: {_format_error(e)}")
    
    return result

def process_single_video(video_id, video_data_dict, video_analytics_dict, video_matches, 
                         video_decision_details, briefs, youtube_analytics_client, result,
                         is_ypp_account, cached_ratio, channel_analytics=None):
    """Process a single video and update the result structure."""
    video_data = video_data_dict[video_id]
    video_analytics = video_analytics_dict[video_id]
    
    # Check if this video matches any briefs
    matches_any_brief, matching_brief_ids = check_video_brief_matches(video_id, video_matches, briefs)
    
    # Store video details in the result
    result["videos"][video_id] = {
        "details": video_data,
        "analytics": video_analytics,
        "matches_brief": matches_any_brief,
        "matching_brief_ids": matching_brief_ids,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "vet_outcomes": video_matches.get(video_id, []),
        "decision_details": video_decision_details.get(video_id, {})
    }
    
    # Check the overall vetting result
    video_vet_result = video_decision_details.get(video_id, {}).get("video_vet_result", False)
    
    # Calculate and store the score if the video passes vetting and matches a brief
    if video_vet_result and matches_any_brief:
        update_video_score(video_id, youtube_analytics_client, video_matches, briefs, result, is_ypp_account, cached_ratio, channel_analytics)
    else:
        result["videos"][video_id]["score"] = 0

def check_video_brief_matches(video_id, video_matches, briefs):
    """Check if a video matches any briefs and return all matching brief IDs."""
    matches_any_brief = False
    matching_brief_ids = []
    
    for i, match in enumerate(video_matches.get(video_id, [])):
        if match:
            matches_any_brief = True
            matching_brief_ids.append(briefs[i]["id"])
    
    return matches_any_brief, matching_brief_ids

def update_video_score(video_id, youtube_analytics_client, video_matches, briefs, result, is_ypp_account, cached_ratio, channel_analytics=None):
    """Calculate and update the score for a video that matches a brief using dual scoring mechanism."""
    video_publish_date = result["videos"][video_id]["details"].get("publishedAt")
    existing_analytics = result["videos"][video_id]["analytics"]
    
    video_score_result = calculate_video_score(
        video_id, youtube_analytics_client, video_publish_date, existing_analytics,
        is_ypp_account=is_ypp_account, cached_ratio=cached_ratio, channel_analytics=channel_analytics
    )
    video_score = video_score_result["score"]
    scoring_method = video_score_result["scoring_method"]
    
    # Log scoring information including cap details
    cap_info = ""
    if video_score_result.get("applied_cap", False):
        if scoring_method == "ypp":
            cap_info = f" [REVENUE CAP: {video_score_result.get('original_revenue', 0):.4f} -> {video_score_result.get('capped_revenue', 0):.4f}]"
        elif scoring_method == "non_ypp_predicted":
            cap_info = f" [VIEWS CAP: {video_score_result.get('original_views', 0):.0f} -> {video_score_result.get('capped_views', 0):.0f}]"
    
    bt.logging.info(f"Raw video_score from calculate_video_score: {video_score} (method: {scoring_method}){cap_info}")
    
    result["videos"][video_id]["score"] = video_score
    result["videos"][video_id]["daily_analytics"] = video_score_result["daily_analytics"]
    result["videos"][video_id]["scoring_method"] = scoring_method
    
    # Store cap debugging information
    if "applied_cap" in video_score_result:
        cap_info_dict = {"applied_cap": video_score_result["applied_cap"]}
        
        # Add debugging fields based on account type  
        ypp_fields = ["original_revenue", "capped_revenue", "median_revenue_cap"]
        non_ypp_fields = ["original_views", "capped_views", "median_views_cap", "predicted_revenue"]
        
        fields = ypp_fields if scoring_method == "ypp" else non_ypp_fields
        cap_info_dict.update({field: video_score_result.get(field) for field in fields})
        
        result["videos"][video_id]["cap_info"] = cap_info_dict
    
    # Update the score for the matching brief
    for i, match in enumerate(video_matches.get(video_id, [])):
        if match:
            brief_id = briefs[i]["id"]
            result["scores"][brief_id] += video_score
            bt.logging.info(f"Brief: {brief_id}, Video: {result['videos'][video_id]['details']['bitcastVideoId']}, Score: {video_score}") 