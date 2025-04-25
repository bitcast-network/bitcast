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
    DISCRETE_MODE
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
    scores = [0] * len(briefs)
    
    # Initialize the comprehensive result structure
    result = {
        "yt_account": {
            "details": None,
            "analytics": None,
            "channel_vet_result": None
        },
        "videos": {},
        "check_outcomes": {
            "channel_vet": None,
            "video_vet": {}
        },
        "scores": scores
    }

    try:
        youtube_data_client = build("youtube", "v3", credentials=creds)
        youtube_analytics_client_client = build("youtubeAnalytics", "v2", credentials=creds)

        channel_data = youtube_utils.get_channel_data(youtube_data_client, DISCRETE_MODE)
        channel_analytics = youtube_utils.get_channel_analytics(youtube_analytics_client_client, start_date="1995-01-01", end_date="2025-03-31")
        
        # Store channel details in the result
        result["yt_account"]["details"] = channel_data
        result["yt_account"]["analytics"] = channel_analytics
    except Exception as e:
        bt.logging.warning(f"An error occurred while retrieving YouTube data: {e}")
        return result

    # Vet the channel and store the result
    channel_vet_result = vet_channel(channel_data, channel_analytics)
    result["yt_account"]["channel_vet_result"] = channel_vet_result
    result["check_outcomes"]["channel_vet"] = channel_vet_result
    
    if not channel_vet_result:
        return result

    video_ids = youtube_utils.get_all_uploads(youtube_data_client)

    # Vet videos and store the results
    video_matches = vet_videos(video_ids, briefs, youtube_data_client, youtube_analytics_client_client)
    result["check_outcomes"]["video_vet"] = video_matches

    bt.logging.info("VIDEO SCORES")
    for i, brief in enumerate(briefs):
        for video_id, match in zip(video_ids, video_matches):
            if match:
                # Get video data and analytics for reporting
                video_data = youtube_utils.get_video_data(youtube_data_client, video_id, DISCRETE_MODE)
                video_analytics = youtube_utils.get_video_analytics(youtube_analytics_client_client, video_id)
                
                # Store video details in the result
                result["videos"][video_id] = {
                    "details": video_data,
                    "analytics": video_analytics,
                    "matches_brief": True,
                    "brief_id": brief["id"],
                    "url": f"https://www.youtube.com/watch?v={video_id}"
                }
                
                # Calculate and store the score
                video_score = calculate_video_score(video_id, youtube_analytics_client_client)
                scores[i] = video_score
                result["videos"][video_id]["score"] = video_score
                
                bt.logging.info(f"Brief: {brief['id']}, Video: {video_id}, Score: {video_score}")
                break
            else:
                # Store information about videos that didn't match
                if video_id not in result["videos"]:
                    video_data = youtube_utils.get_video_data(youtube_data_client, video_id, DISCRETE_MODE)
                    video_analytics = youtube_utils.get_video_analytics(youtube_analytics_client_client, video_id)
                    
                    result["videos"][video_id] = {
                        "details": video_data,
                        "analytics": video_analytics,
                        "matches_brief": False,
                        "score": 0,
                        "url": f"https://www.youtube.com/watch?v={video_id}"
                    }
                
                bt.logging.info(f"Brief: {brief['id']}, Video: {video_id}, Score: 0")

    return result

def vet_channel(channel_data, channel_analytics):
    bt.logging.info(f"Checking channel")

    # Calculate channel age // youtube returns inconsistent date formats
    try:
        channel_start_date = datetime.strptime(channel_data["channel_start"], '%Y-%m-%dT%H:%M:%S.%fZ')
    except ValueError:
        channel_start_date = datetime.strptime(channel_data["channel_start"], '%Y-%m-%dT%H:%M:%SZ')

    channel_age_days = (datetime.now() - channel_start_date).days

    # Check if channel meets the criteria
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

    if criteria_met:
        bt.logging.info(f"Channel Evaluation Passed")
        return True
    else:
        bt.logging.info(f"Channel Evaluation Failed")
        return False

def vet_videos(video_ids, briefs, youtube_data_client, youtube_analytics_client):
    results = {}

    for video_id in video_ids:
        if video_id in scored_video_ids:
            bt.logging.info(f"Video {video_id} already scored by another hotkey")
            results[video_id] = [False] * len(briefs)
            continue
        scored_video_ids.append(video_id)
        
        video_data = youtube_utils.get_video_data(youtube_data_client, video_id, DISCRETE_MODE)
        video_analytics = youtube_utils.get_video_analytics(youtube_analytics_client, video_id)

        decision_details = vet_video(video_id, briefs, video_data, video_analytics)["decision_details"]
        results[video_id] = decision_details["contentAgainstBriefCheck"]
        bt.logging.info(f"Video meets {sum(decision_details['contentAgainstBriefCheck'])} briefs.")

    return results

def vet_video(video_id, briefs, video_data, video_analytics):
    bt.logging.info(f"=== Evaluating video: {video_data['videoId']} ===")

    decision_details = {
        "averageViewPercentageCheck": None,
        "manualCaptionsCheck": None,
        "promptInjectionCheck": None,
        "contentAgainstBriefCheck": [],
        "publicVideo": None
    }

    # Check if the video is public
    if video_data.get("privacyStatus") != "public":
        bt.logging.warning(f"Video is not public - exiting early")
        decision_details["publicVideo"] = False
        return {"met_brief_ids": [], "decision_details": decision_details}
    else:
        decision_details["publicVideo"] = True

    averageViewPercentage = float(video_analytics.get("averageViewPercentage", 0))
    if averageViewPercentage < YT_MIN_VIDEO_RETENTION:
        bt.logging.info(f"Avg retention check failed for video: {video_id}. {averageViewPercentage} <= {YT_MIN_VIDEO_RETENTION}%.")
        decision_details["averageViewPercentageCheck"] = False
        return {"met_brief_ids": [], "decision_details": decision_details}
    else:
        decision_details["averageViewPercentageCheck"] = True

    if video_data.get("caption"):
        bt.logging.info(f"Manual captions detected for video: {video_id} - skipping eval")
        decision_details["manualCaptionsCheck"] = False
        return {"met_brief_ids": [], "decision_details": decision_details}
    else:
        decision_details["manualCaptionsCheck"] = True

    transcript = video_data.get("transcript") # transcript will only be in video_data for test runs
    if transcript is None:
        transcript = youtube_utils.get_video_transcript(video_id, RAPID_API_KEY)

    if transcript is None:
        bt.logging.warning(f"Transcript retrieval failed for video: {video_id} - exiting early")
        decision_details["contentAgainstBriefCheck"].extend([False] * len(briefs))
        return {"met_brief_ids": [], "decision_details": decision_details}

    if check_for_prompt_injection(video_data["description"], transcript):
        bt.logging.warning(f"Prompt injection detected for video: {video_id} - skipping eval")
        decision_details["promptInjectionCheck"] = False
        return {"met_brief_ids": [], "decision_details": decision_details}
    else:
        decision_details["promptInjectionCheck"] = True

    met_brief_ids = []

    for brief in briefs:
        try:
            match = evaluate_content_against_brief(brief, video_data['duration'], video_data['description'], transcript)
            decision_details["contentAgainstBriefCheck"].append(match)
            if match:
                met_brief_ids.append(brief["id"])
        except Exception as e:
            bt.logging.error(f"Error evaluating brief {brief['id']} for video: {video_id}: {e}")

    return {"met_brief_ids": met_brief_ids, "decision_details": decision_details}

def calculate_video_score(video_id, youtube_analytics_client):

    start_date = (datetime.now() - timedelta(days=YT_REWARD_DELAY + YT_ROLLING_WINDOW - 1)).strftime('%Y-%m-%d')
    end_date = (datetime.now() - timedelta(days=YT_REWARD_DELAY)).strftime('%Y-%m-%d')

    video_analytics = youtube_utils.get_video_analytics(youtube_analytics_client, video_id, start_date, end_date, dimensions='day')

    total_minutes_watched = sum(item.get('estimatedMinutesWatched', 0) for item in video_analytics)

    return total_minutes_watched