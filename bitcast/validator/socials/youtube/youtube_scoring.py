import asyncio
import bittensor as bt
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from concurrent.futures import ThreadPoolExecutor, as_completed

from bitcast.validator.socials.youtube import youtube_utils
from bitcast.validator.socials.youtube.youtube_evaluation import (
    vet_channel,
    vet_videos,
    calculate_video_score,
    process_video_vetting,
    vet_video,
    initialize_decision_details,
    check_video_privacy,
    check_video_retention,
    check_manual_captions,
    get_video_transcript,
    check_prompt_injection,
    evaluate_content_against_briefs
)
from bitcast.validator.config import (
    YT_MIN_SUBS, 
    YT_MIN_CHANNEL_AGE, 
    YT_MIN_CHANNEL_RETENTION, 
    YT_MIN_VIDEO_RETENTION, 
    YT_REWARD_DELAY, 
    YT_ROLLING_WINDOW,
    DISCRETE_MODE,
    YT_LOOKBACK
)
from bitcast.validator.config import (
    RAPID_API_KEY
)

def eval_youtube(creds, briefs):
    bt.logging.info(f"Scoring Youtube Content")
    
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
    
    if not channel_vet_result:
        return result
    
    # Process videos and update the result
    result = process_videos(youtube_data_client, youtube_analytics_client, briefs, result)
    
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
        video_ids = youtube_utils.get_all_uploads(youtube_data_client, YT_LOOKBACK)
        
        # Vet videos and store the results
        video_matches, video_data_dict, video_analytics_dict, video_decision_details = vet_videos(
            video_ids, briefs, youtube_data_client, youtube_analytics_client
        )
        
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
                    result
                )
    except Exception as e:
        bt.logging.error(f"Error during video evaluation: {e}")
    
    return result

def process_single_video(video_id, video_data_dict, video_analytics_dict, video_matches, 
                         video_decision_details, briefs, youtube_analytics_client, result):
    """Process a single video and update the result structure."""
    video_data = video_data_dict[video_id]
    video_analytics = video_analytics_dict[video_id]
    
    # Check if this video matches any briefs
    matches_any_brief, brief_id = check_video_brief_matches(video_id, video_matches, briefs)
    
    # Store video details in the result
    result["videos"][video_id] = {
        "details": video_data,
        "analytics": video_analytics,
        "matches_brief": matches_any_brief,
        "brief_id": brief_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "vet_outcomes": video_matches.get(video_id, []),
        "decision_details": video_decision_details.get(video_id, {})
    }
    
    # Calculate and store the score if the video matches a brief
    if matches_any_brief:
        update_video_score(video_id, youtube_analytics_client, video_matches, briefs, result)
    else:
        result["videos"][video_id]["score"] = 0

def check_video_brief_matches(video_id, video_matches, briefs):
    """Check if a video matches any briefs and return the matching brief ID."""
    matches_any_brief = False
    brief_id = None
    
    for i, match in enumerate(video_matches.get(video_id, [])):
        if match:
            matches_any_brief = True
            brief_id = briefs[i]["id"]
            break
    
    return matches_any_brief, brief_id

def update_video_score(video_id, youtube_analytics_client, video_matches, briefs, result):
    """Calculate and update the score for a video that matches a brief."""
    video_score_result = calculate_video_score(video_id, youtube_analytics_client)
    video_score = video_score_result["score"]
    
    result["videos"][video_id]["score"] = video_score
    result["videos"][video_id]["daily_analytics"] = video_score_result["daily_analytics"]
    
    # Update the score for the matching brief
    for i, match in enumerate(video_matches.get(video_id, [])):
        if match:
            brief_id = briefs[i]["id"]
            result["scores"][brief_id] += video_score
            bt.logging.info(f"Brief: {brief_id}, Video: {video_id}, Score: {video_score}")