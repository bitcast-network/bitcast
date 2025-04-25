import bittensor as bt
from datetime import datetime, timedelta
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
    RAPID_API_KEY
)

# Global list to track which videos have already been scored
scored_video_ids = []

def reset_scored_videos():
    """Reset the global scored_video_ids list."""
    global scored_video_ids
    scored_video_ids = []

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
    """Calculate the score for a video based on analytics data."""
    start_date = (datetime.now() - timedelta(days=YT_REWARD_DELAY + YT_ROLLING_WINDOW - 1)).strftime('%Y-%m-%d')
    end_date = (datetime.now() - timedelta(days=YT_REWARD_DELAY)).strftime('%Y-%m-%d')

    video_analytics = youtube_utils.get_video_analytics(youtube_analytics_client, video_id, start_date, end_date, dimensions='day')

    total_minutes_watched = sum(item.get('estimatedMinutesWatched', 0) for item in video_analytics)

    # Return both the score and the daily analytics data
    return {
        "score": total_minutes_watched,
        "daily_analytics": video_analytics
    } 