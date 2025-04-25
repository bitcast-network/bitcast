import asyncio
import bittensor as bt
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from concurrent.futures import ThreadPoolExecutor, as_completed

from bitcast.validator.socials.youtube import youtube_utils
from bitcast.validator.OpenaiClient import evaluate_content_against_brief, check_for_prompt_injection
from bitcast.validator.config import (
    YT_MIN_SUBS, 
    YT_MIN_CHANNEL_AGE, 
    YT_MIN_CHANNEL_RETENTION, 
    YT_MIN_VIDEO_RETENTION, 
    YT_REWARD_DELAY, 
    YT_ROLLING_WINDOW,
    DISCRETE_MODE,
    YT_VIDEO_LOOKBACK
)
from bitcast.validator.config import (
    RAPID_API_KEY
)

# Global list to track which videos have already been scored
scored_video_ids = []

def reset_scored_videos():
    """Reset the global scored_video_ids list."""
    global scored_video_ids
    scored_video_ids = []

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
    result["yt_account"]["vet_outcome"] = channel_vet_result
    
    if not channel_vet_result:
        return result
    
    # Process videos and update the result
    result = process_videos(youtube_data_client, youtube_analytics_client, briefs, result)
    
    return result

def initialize_youtube_evaluation(creds, briefs):
    """Initialize the result structure and YouTube API clients."""
    scores = [0] * len(briefs)
    
    # Initialize the comprehensive result structure
    result = {
        "yt_account": {
            "details": None,
            "analytics": None,
            "channel_vet_result": None,
            "vet_outcome": None
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
        channel_analytics = youtube_utils.get_channel_analytics(youtube_analytics_client, start_date="1995-01-01", end_date="2025-03-31")
        return channel_data, channel_analytics
    except Exception as e:
        bt.logging.warning(f"An error occurred while retrieving YouTube data: {e}")
        return None, None

def process_videos(youtube_data_client, youtube_analytics_client, briefs, result):
    """Process videos, calculate scores, and update the result structure."""
    try:
        video_ids = youtube_utils.get_all_uploads(youtube_data_client, YT_VIDEO_LOOKBACK)
        
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
        bt.logging.info(f"Video: {video_id} doesn't match any briefs, Score: 0")

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
            result["scores"][i] = video_score
            bt.logging.info(f"Brief: {briefs[i]['id']}, Video: {video_id}, Score: {video_score}")

def vet_channel(channel_data, channel_analytics):
    bt.logging.info(f"Checking channel")

    # Calculate channel age
    channel_age_days = calculate_channel_age(channel_data)
    
    # Check if channel meets the criteria
    criteria_met = check_channel_criteria(channel_data, channel_analytics, channel_age_days)
    
    if criteria_met:
        bt.logging.info(f"Channel Evaluation Passed")
        return True
    else:
        bt.logging.info(f"Channel Evaluation Failed")
        return False

def calculate_channel_age(channel_data):
    """Calculate the age of the channel in days."""
    # youtube returns inconsistent date formats
    try:
        channel_start_date = datetime.strptime(channel_data["channel_start"], '%Y-%m-%dT%H:%M:%S.%fZ')
    except ValueError:
        channel_start_date = datetime.strptime(channel_data["channel_start"], '%Y-%m-%dT%H:%M:%SZ')

    return (datetime.now() - channel_start_date).days

def check_channel_criteria(channel_data, channel_analytics, channel_age_days):
    """Check if the channel meets all the required criteria."""
    criteria_met = True

    if channel_age_days < YT_MIN_CHANNEL_AGE:
        bt.logging.warning(f"Channel age check failed: {channel_data['id']}. {channel_age_days} < {YT_MIN_CHANNEL_AGE}")
        criteria_met = False

    if int(channel_data["subCount"]) < YT_MIN_SUBS:
        bt.logging.warning(f"Subscriber count check failed: {channel_data['id']}. {channel_data['subCount']} < {YT_MIN_SUBS}.")
        criteria_met = False

    if float(channel_analytics["averageViewPercentage"]) < YT_MIN_CHANNEL_RETENTION:
        bt.logging.warning(f"Avg retention check failed: {channel_data['id']}. {channel_analytics['averageViewPercentage']} < {YT_MIN_CHANNEL_RETENTION}%.")
        criteria_met = False

    return criteria_met

def vet_videos(video_ids, briefs, youtube_data_client, youtube_analytics_client):
    results = {}
    video_data_dict = {}  # Store video data for all videos
    video_analytics_dict = {}  # Store video analytics for all videos
    video_decision_details = {}  # Store decision details for all videos

    for video_id in video_ids:
        try:
            # Check if video has already been scored
            if is_video_already_scored(video_id):
                results[video_id] = [False] * len(briefs)
                continue
                
            # Mark video as scored
            mark_video_as_scored(video_id)
            
            # Process the video
            process_video_vetting(
                video_id, 
                briefs, 
                youtube_data_client, 
                youtube_analytics_client, 
                results, 
                video_data_dict, 
                video_analytics_dict, 
                video_decision_details
            )
        except Exception as e:
            bt.logging.error(f"Error evaluating video {video_id}: {e}")
            # Mark this video as not matching any briefs
            results[video_id] = [False] * len(briefs)

    return results, video_data_dict, video_analytics_dict, video_decision_details

def is_video_already_scored(video_id):
    """Check if a video has already been scored by another hotkey."""
    if video_id in scored_video_ids:
        bt.logging.info(f"Video {video_id} already scored by another hotkey")
        return True
    return False

def mark_video_as_scored(video_id):
    """Mark a video as scored to prevent duplicate processing."""
    global scored_video_ids
    scored_video_ids.append(video_id)

def process_video_vetting(video_id, briefs, youtube_data_client, youtube_analytics_client, 
                         results, video_data_dict, video_analytics_dict, video_decision_details):
    """Process the vetting of a single video."""
    # Get video data and analytics
    video_data = youtube_utils.get_video_data(youtube_data_client, video_id, DISCRETE_MODE)
    video_analytics = youtube_utils.get_video_analytics(youtube_analytics_client, video_id)
    
    # Store video data and analytics regardless of vetting result
    video_data_dict[video_id] = video_data
    video_analytics_dict[video_id] = video_analytics

    # Get decision details for the video
    vet_result = vet_video(video_id, briefs, video_data, video_analytics)
    decision_details = vet_result["decision_details"]
    results[video_id] = decision_details["contentAgainstBriefCheck"]
    video_decision_details[video_id] = decision_details
    
    bt.logging.info(f"Video meets {sum(decision_details['contentAgainstBriefCheck'])} briefs.")

def vet_video(video_id, briefs, video_data, video_analytics):
    bt.logging.info(f"=== Evaluating video: {video_data['videoId']} ===")

    # Initialize decision details structure
    decision_details = initialize_decision_details()
    
    # Check if the video is public
    if not check_video_privacy(video_data, decision_details, briefs):
        return {"met_brief_ids": [], "decision_details": decision_details}
    
    # Check video retention
    if not check_video_retention(video_id, video_analytics, decision_details, briefs):
        return {"met_brief_ids": [], "decision_details": decision_details}
    
    # Check for manual captions
    if not check_manual_captions(video_id, video_data, decision_details, briefs):
        return {"met_brief_ids": [], "decision_details": decision_details}
    
    # Get and check transcript
    transcript = get_video_transcript(video_id, video_data)
    if transcript is None:
        decision_details["contentAgainstBriefCheck"].extend([False] * len(briefs))
        return {"met_brief_ids": [], "decision_details": decision_details}
    
    # Check for prompt injection
    if not check_prompt_injection(video_id, video_data, transcript, decision_details, briefs):
        return {"met_brief_ids": [], "decision_details": decision_details}
    
    # Evaluate content against briefs
    met_brief_ids = evaluate_content_against_briefs(briefs, video_data, transcript, decision_details)
    
    return {"met_brief_ids": met_brief_ids, "decision_details": decision_details}

def initialize_decision_details():
    """Initialize the decision details structure."""
    return {
        "averageViewPercentageCheck": None,
        "manualCaptionsCheck": None,
        "promptInjectionCheck": None,
        "contentAgainstBriefCheck": [],
        "publicVideo": None
    }

def check_video_privacy(video_data, decision_details, briefs):
    """Check if the video is public."""
    if video_data.get("privacyStatus") != "public":
        bt.logging.warning(f"Video is not public - exiting early")
        decision_details["publicVideo"] = False
        decision_details["contentAgainstBriefCheck"].extend([False] * len(briefs))
        return False
    else:
        decision_details["publicVideo"] = True
        return True

def check_video_retention(video_id, video_analytics, decision_details, briefs):
    """Check if the video meets the minimum retention criteria."""
    averageViewPercentage = float(video_analytics.get("averageViewPercentage", 0))
    if averageViewPercentage < YT_MIN_VIDEO_RETENTION:
        bt.logging.info(f"Avg retention check failed for video: {video_id}. {averageViewPercentage} <= {YT_MIN_VIDEO_RETENTION}%.")
        decision_details["averageViewPercentageCheck"] = False
        decision_details["contentAgainstBriefCheck"].extend([False] * len(briefs))
        return False
    else:
        decision_details["averageViewPercentageCheck"] = True
        return True

def check_manual_captions(video_id, video_data, decision_details, briefs):
    """Check if the video has manual captions."""
    if video_data.get("caption"):
        bt.logging.info(f"Manual captions detected for video: {video_id} - skipping eval")
        decision_details["manualCaptionsCheck"] = False
        decision_details["contentAgainstBriefCheck"].extend([False] * len(briefs))
        return False
    else:
        decision_details["manualCaptionsCheck"] = True
        return True

def get_video_transcript(video_id, video_data):
    """Get the video transcript."""
    transcript = video_data.get("transcript") # transcript will only be in video_data for test runs
    if transcript is None:
        try:
            transcript = youtube_utils.get_video_transcript(video_id, RAPID_API_KEY)
        except Exception as e:
            bt.logging.warning(f"Error retrieving transcript for video: {video_id} - {e}")
            transcript = None

    if transcript is None:
        bt.logging.warning(f"Transcript retrieval failed for video: {video_id} - exiting early")
        return None
        
    return transcript

def check_prompt_injection(video_id, video_data, transcript, decision_details, briefs):
    """Check if the video contains prompt injection."""
    if check_for_prompt_injection(video_data["description"], transcript):
        bt.logging.warning(f"Prompt injection detected for video: {video_id} - skipping eval")
        decision_details["promptInjectionCheck"] = False
        decision_details["contentAgainstBriefCheck"].extend([False] * len(briefs))
        return False
    else:
        decision_details["promptInjectionCheck"] = True
        return True

def evaluate_content_against_briefs(briefs, video_data, transcript, decision_details):
    """Evaluate the video content against each brief."""
    met_brief_ids = []

    for brief in briefs:
        try:
            match = evaluate_content_against_brief(brief, video_data['duration'], video_data['description'], transcript)
            decision_details["contentAgainstBriefCheck"].append(match)
            if match:
                met_brief_ids.append(brief["id"])
        except Exception as e:
            bt.logging.error(f"Error evaluating brief {brief['id']} for video: {video_id}: {e}")
            decision_details["contentAgainstBriefCheck"].append(False)
            
    return met_brief_ids

def calculate_video_score(video_id, youtube_analytics_client):

    start_date = (datetime.now() - timedelta(days=YT_REWARD_DELAY + YT_ROLLING_WINDOW - 1)).strftime('%Y-%m-%d')
    end_date = (datetime.now() - timedelta(days=YT_REWARD_DELAY)).strftime('%Y-%m-%d')

    video_analytics = youtube_utils.get_video_analytics(youtube_analytics_client, video_id, start_date, end_date, dimensions='day')

    total_minutes_watched = sum(item.get('estimatedMinutesWatched', 0) for item in video_analytics)

    # Return both the score and the daily analytics data
    return {
        "score": total_minutes_watched,
        "daily_analytics": video_analytics
    }