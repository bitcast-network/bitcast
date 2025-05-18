import asyncio
import bittensor as bt
from datetime import datetime, timedelta
from googleapiclient.discovery import build

from bitcast.validator.socials.youtube import youtube_utils
from bitcast.validator.socials.youtube.youtube_evaluation import (
    vet_channel,
    vet_videos,
    calculate_video_score
)
from bitcast.validator.utils.config import (
    YT_MIN_SUBS, 
    YT_MIN_CHANNEL_AGE, 
    YT_MIN_CHANNEL_RETENTION, 
    YT_MIN_VIDEO_RETENTION, 
    YT_REWARD_DELAY, 
    YT_ROLLING_WINDOW,
    DISCRETE_MODE,
    YT_LOOKBACK,
    ECO_MODE
)
from bitcast.validator.utils.config import (
    RAPID_API_KEY
)

def eval_youtube(creds, briefs):
    bt.logging.info(f"Scoring Youtube Content")
    bt.logging.info(f"Number of briefs received: {len(briefs)}")
    
    # Initialize the result structure and get API clients
    result, youtube_data_client, youtube_analytics_client = initialize_youtube_evaluation(creds, briefs)
    
    # Get and process channel information
    channel_data, channel_analytics = get_channel_information(youtube_data_client, youtube_analytics_client)
    if channel_data is None or channel_analytics is None:
        return result
    
    # Store channel details in the result
    result["yt_account"]["details"] = channel_data
    result["yt_account"]["analytics"] = channel_analytics
    
    # Vet the channel and store the result
    channel_vet_result = vet_channel(channel_data, channel_analytics)
    result["yt_account"]["channel_vet_result"] = channel_vet_result

    if not channel_vet_result and ECO_MODE:
        bt.logging.info("Channel vetting failed and ECO_MODE is enabled - exiting early")
        return result

    filtered_briefs = channel_briefs_filter(briefs, channel_analytics)
    bt.logging.info(f"After filtering, number of briefs: {len(filtered_briefs)}")
    
    # Process videos and update the result
    result = process_videos(youtube_data_client, youtube_analytics_client, filtered_briefs, result)
    
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
    
    try:
        youtube_data_client = build("youtube", "v3", credentials=creds)
        youtube_analytics_client = build("youtubeAnalytics", "v2", credentials=creds)
        return result, youtube_data_client, youtube_analytics_client
    except Exception as e:
        bt.logging.warning(f"An error occurred while initializing YouTube clients: {e}")
        return result, None, None

def get_channel_information(youtube_data_client, youtube_analytics_client):
    """Retrieve channel data and analytics."""
    try:
        channel_data = youtube_utils.get_channel_data(youtube_data_client, DISCRETE_MODE)
        
        # Calculate date range for the last YT_LOOKBACK days
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=YT_LOOKBACK)).strftime('%Y-%m-%d')
        
        channel_analytics = youtube_utils.get_channel_analytics(youtube_analytics_client, start_date=start_date, end_date=end_date)
        return channel_data, channel_analytics
    except Exception as e:
        bt.logging.warning(f"An error occurred while retrieving YouTube data: {e}")
        return None, None

def process_videos(youtube_data_client, youtube_analytics_client, briefs, result):
    """Process videos, calculate scores, and update the result structure."""
    try:
        bt.logging.info(f"Processing videos with {len(briefs)} briefs")
        
        video_ids = youtube_utils.get_all_uploads(youtube_data_client, YT_LOOKBACK)
        bt.logging.info(f"Retrieved {len(video_ids)} videos")
        
        # Vet videos and store the results
        video_matches, video_data_dict, video_analytics_dict, video_decision_details = vet_videos(
            video_ids, briefs, youtube_data_client, youtube_analytics_client
        )
        
        # Process each video and update the result
        for video_id in video_ids:
            if video_id in video_data_dict and video_id in video_analytics_dict:
                try:
                    process_single_video(
                        video_id, 
                        video_data_dict, 
                        video_analytics_dict, 
                        video_matches, 
                        video_decision_details, 
                        briefs, 
                        youtube_analytics_client, 
                        result
                    )
                except Exception as e:
                    bt.logging.error(f"Error processing video {video_data_dict[video_id]['bitcastVideoId']}: {e}", exc_info=True)
            else:
                bt.logging.warning(f"Video missing from data dict or analytics dict")
        
        # If channel vetting failed, set all scores to 0 but keep the video data
        if not result["yt_account"]["channel_vet_result"]:
            bt.logging.info("Channel vetting failed, setting all scores to 0")
            result["scores"] = {brief["id"]: 0 for brief in briefs}
            
    except Exception as e:
        bt.logging.error(f"Error during video evaluation: {e}", exc_info=True)
    
    return result

def process_single_video(video_id, video_data_dict, video_analytics_dict, video_matches, 
                         video_decision_details, briefs, youtube_analytics_client, result):
    """Process a single video and update the result structure."""
    video_data = video_data_dict[video_id]
    video_analytics = video_analytics_dict[video_id]
    
    # Check if this video matches any briefs
    if video_id not in video_matches:
        bt.logging.warning(f"Video {video_data['bitcastVideoId']} not found in video_matches dictionary")
        matches_any_brief, matching_brief_ids = False, []
    else:
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
        update_video_score(video_id, youtube_analytics_client, video_matches, briefs, result)
    else:
        result["videos"][video_id]["score"] = 0

def check_video_brief_matches(video_id, video_matches, briefs):
    """Check if a video matches any briefs and return all matching brief IDs."""
    matches_any_brief = False
    matching_brief_ids = []
    
    matches_for_video = video_matches.get(video_id, [])
    
    # Ensure we don't go out of bounds
    if len(matches_for_video) > len(briefs):
        matches_for_video = matches_for_video[:len(briefs)]
    
    for i, match in enumerate(matches_for_video):
        if i >= len(briefs):
            continue
            
        if match:
            matches_any_brief = True
            matching_brief_ids.append(briefs[i]["id"])
    
    return matches_any_brief, matching_brief_ids

def update_video_score(video_id, youtube_analytics_client, video_matches, briefs, result):
    """Calculate and update the score for a video that matches a brief."""
    video_score_result = calculate_video_score(video_id, youtube_analytics_client)
    video_score = video_score_result["score"]
    
    result["videos"][video_id]["score"] = video_score
    result["videos"][video_id]["daily_analytics"] = video_score_result["daily_analytics"]
    
    # Update the score for the matching brief
    matches_for_video = video_matches.get(video_id, [])
    
    # Ensure we don't go out of bounds
    if len(matches_for_video) > len(briefs):
        matches_for_video = matches_for_video[:len(briefs)]
    
    for i, match in enumerate(matches_for_video):
        if i >= len(briefs):
            continue
            
        if match:
            brief_id = briefs[i]["id"]
            result["scores"][brief_id] += video_score
            bt.logging.info(f"Brief: {brief_id}, Video: {result['videos'][video_id]['details'].get('bitcastVideoId', 'unknown')}, Score: {video_score}")

def check_subscriber_range(sub_count, subs_range):
    """
    Check if a subscriber count falls within a given range.
    Handles null values in the range:
    - If both values are null, returns True (no filtering)
    - If first value is null, checks if count is less than or equal to max
    - If second value is null, checks if count is greater than or equal to min
    - If neither is null, checks if count is within range (inclusive)
    
    Args:
        sub_count (int): Channel's subscriber count
        subs_range (list): List of [min_subs, max_subs] where either can be null
        
    Returns:
        bool: True if subscriber count is within range, False otherwise
    """
    min_subs, max_subs = subs_range
    
    # If both values are null, no filtering
    if min_subs is None and max_subs is None:
        return True
        
    # If first value is null, check if count is less than or equal to max
    if min_subs is None:
        return sub_count <= max_subs
        
    # If second value is null, check if count is greater than or equal to min
    if max_subs is None:
        return sub_count >= min_subs
        
    # If neither is null, check if count is within range (inclusive)
    return min_subs <= sub_count <= max_subs

def channel_briefs_filter(briefs, channel_analytics):
    """
    Filter briefs based on the channel's subscriber count.
    Only returns briefs where the channel's subscriber count falls within the brief's subs_range (inclusive).
    
    Args:
        briefs (List[dict]): List of briefs to filter
        channel_analytics (dict): Channel analytics data containing subscriber count
        
    Returns:
        List[dict]: Filtered list of briefs
    """
    if not briefs:
        bt.logging.warning("No briefs provided to channel_briefs_filter")
        return []
        
    # Get channel's subscriber count
    sub_count = int(channel_analytics.get("subCount", 0))
    bt.logging.info(f"Channel subscriber count: {sub_count}")
    
    # Filter briefs based on subscriber count range
    filtered_briefs = []
    for brief in briefs:
        # If brief doesn't have a subs_range, include it
        if "subs_range" not in brief:
            filtered_briefs.append(brief)
            continue
            
        # Check if channel's subscriber count falls within the range
        if check_subscriber_range(sub_count, brief["subs_range"]):
            filtered_briefs.append(brief)
        else:
            min_subs, max_subs = brief["subs_range"]
            range_str = f"[{min_subs or 'null'}, {max_subs or 'null'}]"
            bt.logging.info(f"Channel subscriber count {sub_count} outside brief {brief['id']} range {range_str}")
            
    return filtered_briefs