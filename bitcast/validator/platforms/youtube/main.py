from datetime import datetime, timedelta
import time

import bittensor as bt

import bitcast.validator.clients.OpenaiClient as openai_client_module
from bitcast.validator.platforms.youtube.api import (
    get_channel_analytics,
    get_channel_data,
    initialize_youtube_clients,
)
from bitcast.validator.platforms.youtube.api.video import get_all_uploads
from bitcast.validator.platforms.youtube.evaluation import (
    calculate_video_score,
    vet_channel,
    vet_videos,
)
from bitcast.validator.platforms.youtube.utils import _format_error, state
from bitcast.validator.platforms.youtube.utils.historical_videos import (
    add_historical_videos_to_list,
    record_matching_video,
)
from bitcast.validator.utils.config import (
    DISCRETE_MODE,
    ECO_MODE,
    YT_LOOKBACK,
    YT_SCALING_FACTOR_DEDICATED,
    YT_SCALING_FACTOR_AD_READ,
)
from bitcast.validator.utils.token_pricing import get_bitcast_alpha_price, get_total_miner_emissions


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
    result = process_videos(youtube_data_client, youtube_analytics_client, briefs, result, min_stake)
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
        # Log warning but don't raise - this function is designed to return None on failure
        bt.logging.warning(f"An error occurred while retrieving YouTube data: {_format_error(e)}")
        return None, None

def apply_video_limits(briefs, result):
    """
    Apply video scoring limits for dedicated and ad-read briefs using FIFO selection.
    
    For each brief with limits, limits the number of videos that can receive scores per account.
    Only the oldest N videos (by publish date) keep their scores, the rest are set to 0.
    
    Args:
        briefs (list): List of brief dictionaries
        result (dict): Video evaluation result structure
    """
    for brief in briefs:
        brief_id = brief["id"]
        brief_format = brief.get("format", "dedicated")
        
        # Get the limit from brief payload, default to no limit if not specified
        max_count = brief.get("max_count")
        if max_count is None:
            continue # proceed with no limit
            
        max_videos = max(0, max_count)
        if max_videos == 0:
            # Zero or negative means no videos allowed for this brief
            continue
            
        # Find all videos that scored > 0 for this brief
        scored_videos = []
        for video_id, video_data in result["videos"].items():
            if video_data.get("matching_brief_ids") and brief_id in video_data["matching_brief_ids"]:
                # Use raw base score for this specific brief (not USD-scaled value)
                brief_metrics = video_data.get("brief_metrics", {}).get(brief_id, {})
                video_score = brief_metrics.get("base_score", 0)
                if video_score > 0:
                    scored_videos.append({
                        "video_id": video_id,
                        "score": video_score,
                        "bitcast_video_id": video_data["details"].get("bitcastVideoId", video_id)
                    })
        
        # Check if we need to apply limits
        if len(scored_videos) <= max_videos:
            continue
            
        bt.logging.info(f"Brief '{brief_id}' exceeded max_count limit of {max_videos}, limiting {len(scored_videos)} videos to {max_videos}")
            
        # Sort videos by publish date (ascending) - oldest videos get priority (FIFO)
        scored_videos.sort(key=lambda x: result["videos"][x["video_id"]]["details"]["publishedAt"])
        
        # Keep first N videos (oldest), zero out the rest (newest)
        videos_to_limit = scored_videos[max_videos:]
        original_total_score = result["scores"][brief_id]
        score_reduction = 0
        
        for video_info in videos_to_limit:
            video_id = video_info["video_id"]
            original_score = video_info["score"]
            
            # Update USD target for this brief to 0
            if "usd_targets" in result["videos"][video_id]:
                result["videos"][video_id]["usd_targets"][brief_id] = 0
                
            # Update per-video metrics to reflect limitation
            if "brief_metrics" in result["videos"][video_id] and brief_id in result["videos"][video_id]["brief_metrics"]:
                metrics = result["videos"][video_id]["brief_metrics"][brief_id]
                metrics["limitation_status"] = "limited_fifo"
                # Reset all metrics for limited videos
                metrics["usd_target"] = 0
                metrics["alpha_target"] = 0
                metrics["weight"] = 0
            
            # Update backward-compatible "score" field (highest remaining USD target)
            remaining_scores = [s for s in result["videos"][video_id].get("usd_targets", {}).values() if s > 0]
            result["videos"][video_id]["score"] = max(remaining_scores) if remaining_scores else 0
            
            # Add metadata to track this was limited
            if "score_limited" not in result["videos"][video_id]:
                result["videos"][video_id]["score_limited"] = {}
            result["videos"][video_id]["score_limited"][brief_id] = {
                "original_score": original_score,
                "reason": f"exceeded_{brief_format}_brief_limit_fifo"
            }
            
            score_reduction += original_score
        
        # Update the total score for this brief
        result["scores"][brief_id] = original_total_score - score_reduction
        
        # Log the limiting action
        limited_video_ids = [v["bitcast_video_id"] for v in videos_to_limit]
        bt.logging.info(
            f"Applied video limit for {brief_format} brief '{brief_id}': "
            f"kept oldest {max_videos} of {len(scored_videos)} videos (FIFO), "
            f"limited {len(videos_to_limit)} newest videos: {limited_video_ids}, "
            f"score reduced by {score_reduction:.4f}"
        )

def process_videos(youtube_data_client, youtube_analytics_client, briefs, result, min_stake=False):
    """Process videos, calculate scores, and update the result structure."""
    try:
        # Get YPP status from channel analytics
        is_ypp_account = result["yt_account"]["analytics"].get("ypp", False)
        
        # Note: Using hardcoded multiplier for Non-YPP accounts (YT_NON_YPP_REVENUE_MULTIPLIER)
        bt.logging.info(f"Account YPP status: {is_ypp_account}")
        
        # Get recent uploads and add historical videos
        video_ids = get_all_uploads(youtube_data_client, YT_LOOKBACK)
        bt.logging.info(f"Found {len(video_ids)} recent uploads")
        all_video_ids = add_historical_videos_to_list(video_ids, result)
        
        # Vet videos and store the results (includes both recent and historical videos)
        video_matches, video_data_dict, video_analytics_dict, video_decision_details = vet_videos(
            all_video_ids, briefs, youtube_data_client, youtube_analytics_client, is_ypp_account
        )
        
        # Get channel analytics for median cap calculation
        channel_analytics = result["yt_account"]["analytics"]
        
        # Process each video and update the result (includes both recent and historical)
        for video_id in all_video_ids:
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
                    channel_analytics,
                    min_stake
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
                         is_ypp_account, channel_analytics=None, min_stake=False):
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
        record_matching_video(video_id, video_data, matching_brief_ids, result)
        update_video_score(video_id, youtube_analytics_client, video_matches, briefs, result, is_ypp_account, channel_analytics, min_stake)
    else:
        result["videos"][video_id]["score"] = 0

def check_video_brief_matches(video_id, video_matches, briefs):
    """Check if a video matches any briefs and return the matching brief IDs as a list (max length 1)."""
    matches_any_brief = False
    matching_brief_ids = []
    
    for i, match in enumerate(video_matches.get(video_id, [])):
        if match:
            matches_any_brief = True
            matching_brief_ids.append(briefs[i]["id"])
    
    return matches_any_brief, matching_brief_ids


def _get_youtube_scaling_factor(brief_format: str) -> float:
    """Get YouTube-specific scaling factor based on brief format."""
    scaling_factors = {
        "dedicated": YT_SCALING_FACTOR_DEDICATED,
        "ad-read": YT_SCALING_FACTOR_AD_READ
    }
    
    factor = scaling_factors.get(brief_format, YT_SCALING_FACTOR_DEDICATED)
    if brief_format not in scaling_factors:
        bt.logging.warning(f"Unknown brief format '{brief_format}', using dedicated scaling factor")
    
    return factor


def _calculate_per_video_metrics(base_score: float, scaling_factor: float, boost_factor: float) -> dict:
    """Calculate comprehensive per-video metrics for streaming publisher.
    
    Args:
        base_score: The base video score (e.g., from curve-based scoring)
        scaling_factor: Platform-specific scaling (e.g., 400 for dedicated, 80 for ad-read)
        boost_factor: Brief-specific boost multiplier (e.g., 1.25, 2.0)
        
    Returns:
        dict: Per-video metrics including USD/Alpha targets with ALL scaling applied
    """
    try:
        # Calculate USD target with ALL factors (platform scaling + boost) - this is the actual USD value
        usd_target = base_score * scaling_factor * boost_factor
        
        # Get pricing information for weight normalization
        alpha_price_usd = get_bitcast_alpha_price()
        total_daily_alpha = get_total_miner_emissions()
        total_daily_usd = alpha_price_usd * total_daily_alpha
        
        # Calculate alpha target and normalized weight
        alpha_target = usd_target / alpha_price_usd if alpha_price_usd > 0 else 0.0
        weight = usd_target / total_daily_usd if total_daily_usd > 0 else 0.0
        
        # Validation logging
        if usd_target > 0:
            bt.logging.debug(f"Per-video metrics: base={base_score:.6f}, scaling={scaling_factor}, "
                           f"boost={boost_factor}, usd_target=${usd_target:.6f}, "
                           f"alpha_target={alpha_target:.12f}, weight={weight:.12f}")
        
        # Validate boost_factor is within expected range
        if boost_factor < 0.1 or boost_factor > 10.0:
            bt.logging.warning(f"Unusual boost_factor value: {boost_factor} (expected 0.1-10.0)")
        
        return {
            "base_score": base_score,
            "scaling_factor": scaling_factor,
            "brief_boost": boost_factor,
            "usd_target": usd_target,
            "alpha_target": alpha_target,
            "weight": weight,
            "limitation_status": "active"
        }
    except Exception as e:
        bt.logging.error(f"Error calculating per-video metrics: {e}")
        return {
            "base_score": base_score,
            "scaling_factor": scaling_factor,
            "brief_boost": boost_factor,
            "usd_target": 0.0,
            "alpha_target": 0.0,
            "weight": 0.0,
            "limitation_status": "error"
        }


def update_video_score(video_id, youtube_analytics_client, video_matches, briefs, result, is_ypp_account, channel_analytics=None, min_stake=False):
    """Calculate and update the score for a video that matches a brief using curve-based scoring mechanism."""
    video_publish_date = result["videos"][video_id]["details"].get("publishedAt")
    existing_analytics = result["videos"][video_id]["analytics"]
    
    # Get bitcast video ID for logging (falls back to YouTube ID if not available)
    bitcast_video_id = result["videos"][video_id]["details"].get("bitcastVideoId", video_id)
    
    video_score_result = calculate_video_score(
        video_id, youtube_analytics_client, video_publish_date, existing_analytics,
        is_ypp_account=is_ypp_account, channel_analytics=channel_analytics, 
        bitcast_video_id=bitcast_video_id, min_stake=min_stake
    )
    base_video_score = video_score_result["score"]
    scoring_method = video_score_result["scoring_method"]
    
    # Log curve-based scoring information
    curve_info = ""
    if scoring_method in ["ypp_curve_based", "non_ypp_curve_based", "ypp_zero_revenue"]:
        day1_avg = video_score_result.get("day1_average", 0)
        day2_avg = video_score_result.get("day2_average", 0)
        curve_info = f" [Day1 avg: {day1_avg:.4f}, Day2 avg: {day2_avg:.4f}]"
        
        if scoring_method in ["non_ypp_curve_based", "ypp_zero_revenue"]:
            multiplier = video_score_result.get("revenue_multiplier", 0)
            curve_info += f" [Revenue multiplier: {multiplier}]"
    elif scoring_method == "ypp_zero_revenue_no_stake":
        # Special logging for zero-revenue YPP accounts without stake
        curve_info = " [Zero revenue, min_stake=False]"
    
    bt.logging.info(f"Curve-based base_score: {base_video_score} (method: {scoring_method}){curve_info}")
    
    # Store base score and analytics (before scaling)
    result["videos"][video_id]["base_score"] = base_video_score
    result["videos"][video_id]["daily_analytics"] = video_score_result["daily_analytics"]
    result["videos"][video_id]["scoring_method"] = scoring_method
    
    # Store cap debugging information
    if "applied_cap" in video_score_result:
        cap_info_dict = {"applied_cap": video_score_result["applied_cap"]}
        
        # Add debugging fields based on account type  
        ypp_fields = ["original_revenue", "capped_revenue", "median_revenue_cap"]
        non_ypp_fields = ["original_minutes_watched", "capped_minutes_watched", "median_minutes_watched_cap", "predicted_revenue"]
        
        fields = ypp_fields if scoring_method == "ypp" else non_ypp_fields
        cap_info_dict.update({field: video_score_result.get(field) for field in fields})
        
        result["videos"][video_id]["cap_info"] = cap_info_dict
    
    # Apply YouTube-specific scaling and boost factors per brief match
    usd_targets_by_brief = {}
    per_video_metrics_by_brief = {}
    
    for i, match in enumerate(video_matches.get(video_id, [])):
        if match:
            brief = briefs[i]
            brief_id = brief["id"]
            brief_format = brief.get("format", "dedicated")
            boost_factor = brief.get("boost", 1.0)
            
            # Get platform-specific scaling factor
            scaling_factor = _get_youtube_scaling_factor(brief_format)
            
            # Calculate comprehensive per-video metrics with ALL scaling factors applied
            video_metrics = _calculate_per_video_metrics(base_video_score, scaling_factor, boost_factor)
            
            # Extract the USD target (this is now the actual meaningful USD value)
            usd_target = video_metrics["usd_target"]
            
            # Store USD target and metrics for this brief
            usd_targets_by_brief[brief_id] = usd_target
            per_video_metrics_by_brief[brief_id] = video_metrics
            
            # Update the brief score with USD target value
            result["scores"][brief_id] += usd_target
            
            bt.logging.info(f"Brief: {brief_id}, Video: {result['videos'][video_id]['details']['bitcastVideoId']}, "
                          f"Base Score: {base_video_score:.6f}, Scaling: {scaling_factor}, "
                          f"Boost: {boost_factor}, USD Target: ${usd_target:.6f}")
    
    # Store per-video metrics for streaming publisher
    result["videos"][video_id]["brief_metrics"] = per_video_metrics_by_brief
    result["videos"][video_id]["usd_targets"] = usd_targets_by_brief
    
    # Maintain backward compatibility: store the highest USD target as "score"
    if usd_targets_by_brief:
        result["videos"][video_id]["score"] = max(usd_targets_by_brief.values())
    else:
        result["videos"][video_id]["score"] = base_video_score 