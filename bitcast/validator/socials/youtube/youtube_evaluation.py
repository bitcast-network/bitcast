import bittensor as bt
from datetime import datetime, timedelta
from bitcast.validator.socials.youtube import youtube_utils
from bitcast.validator.clients.OpenaiClient import evaluate_content_against_brief, check_for_prompt_injection
from bitcast.validator.utils.config import (
    YT_MIN_SUBS, 
    YT_MIN_CHANNEL_AGE, 
    YT_MIN_CHANNEL_RETENTION, 
    YT_MIN_VIDEO_RETENTION, 
    YT_REWARD_DELAY,
    YT_ROLLING_WINDOW,
    DISCRETE_MODE,
    RAPID_API_KEY,
    YT_MIN_MINS_WATCHED,
    YT_LOOKBACK,
    YT_VIDEO_RELEASE_BUFFER
)

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
        bt.logging.warning(f"Channel age check failed: {channel_data['bitcastChannelId']}. {channel_age_days} < {YT_MIN_CHANNEL_AGE}")
        criteria_met = False

    if int(channel_data["subCount"]) < YT_MIN_SUBS:
        bt.logging.warning(f"Subscriber count check failed: {channel_data['bitcastChannelId']}. {channel_data['subCount']} < {YT_MIN_SUBS}.")
        criteria_met = False

    if float(channel_analytics["averageViewPercentage"]) < YT_MIN_CHANNEL_RETENTION:
        bt.logging.warning(f"Avg retention check failed (last {YT_LOOKBACK} days): {channel_data['bitcastChannelId']}. {channel_analytics['averageViewPercentage']} < {YT_MIN_CHANNEL_RETENTION}%.")
        criteria_met = False
        
    if float(channel_analytics["estimatedMinutesWatched"]) < YT_MIN_MINS_WATCHED:
        bt.logging.warning(f"Minutes watched check failed (last {YT_LOOKBACK} days): {channel_data['bitcastChannelId']}. {channel_analytics['estimatedMinutesWatched']} < {YT_MIN_MINS_WATCHED}.")
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
            if youtube_utils.is_video_already_scored(video_id):
                results[video_id] = [False] * len(briefs)
                continue
                
            # Check cache for this video
            cached_data = youtube_utils.youtube_cache.get_video_cache(video_id)
            if cached_data:
                # If cached data exists and publishDateCheck failed last time, use cached data
                if cached_data.get("decision_details", {}).get("publishDateCheck") is False:
                    bt.logging.info(f"Using cached data (failed publishDateCheck)")
                    results[video_id] = cached_data["results"]
                    video_data_dict[video_id] = cached_data["video_data"]
                    video_analytics_dict[video_id] = cached_data["video_analytics"]
                    video_decision_details[video_id] = {**cached_data["decision_details"], "cache_used": True}
                    continue
            
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
            
            # Cache the results
            cache_data = {
                "results": results[video_id],
                "video_data": video_data_dict[video_id],
                "video_analytics": video_analytics_dict[video_id],
                "decision_details": video_decision_details[video_id]
            }
            youtube_utils.youtube_cache.set_video_cache(video_id, cache_data)
            
            # Only mark the video as scored if processing was successful
            youtube_utils.mark_video_as_scored(video_id)
            
        except Exception as e:
            bt.logging.error(f"Error evaluating video {e}")
            # Mark this video as not matching any briefs
            results[video_id] = [False] * len(briefs)
            # Don't mark the video as scored if there was an error

    return results, video_data_dict, video_analytics_dict, video_decision_details

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
    bt.logging.info(f"=== Evaluating video: {video_data['bitcastVideoId']} ===")

    # Initialize decision details structure
    decision_details = initialize_decision_details()
    
    # Check if the video is public
    if not check_video_privacy(video_data, decision_details, briefs):
        return {"met_brief_ids": [], "decision_details": decision_details}
    
    # Check if video was published after brief start date
    if not check_video_publish_date(video_data, briefs, decision_details):
        return {"met_brief_ids": [], "decision_details": decision_details}
    
    # Check video retention
    if not check_video_retention(video_data, video_analytics, decision_details, briefs):
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
        "publicVideo": None,
        "publishDateCheck": None,
        "cache_used": False
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

def check_video_publish_date(video_data, briefs, decision_details):
    """Check if the video was published after the earliest brief's start date (minus buffer days)."""
    try:
        video_publish_date = datetime.strptime(video_data["publishedAt"], '%Y-%m-%dT%H:%M:%SZ').date()
        
        for brief in briefs:
            brief_start_date = datetime.strptime(brief["start_date"], "%Y-%m-%d").date()
            # Calculate the earliest allowed publish date by subtracting the buffer days
            earliest_allowed_date = brief_start_date - timedelta(days=YT_VIDEO_RELEASE_BUFFER)
            
            if video_publish_date < earliest_allowed_date:
                bt.logging.warning(f"Video was published before the allowed period")
                decision_details["publishDateCheck"] = False
                decision_details["contentAgainstBriefCheck"].extend([False] * len(briefs))
                return False
        
        decision_details["publishDateCheck"] = True
        return True
    except Exception as e:
        bt.logging.error(f"Error checking video publish date: {e}")
        decision_details["publishDateCheck"] = False
        decision_details["contentAgainstBriefCheck"].extend([False] * len(briefs))
        return False

def check_video_retention(video_data, video_analytics, decision_details, briefs):
    """Check if the video meets the minimum retention criteria."""
    averageViewPercentage = float(video_analytics.get("averageViewPercentage", 0))
    if averageViewPercentage < YT_MIN_VIDEO_RETENTION:
        bt.logging.info(f"Avg retention check failed for video: {video_data['bitcastVideoId']}. {averageViewPercentage} <= {YT_MIN_VIDEO_RETENTION}%.")
        decision_details["averageViewPercentageCheck"] = False
        decision_details["contentAgainstBriefCheck"].extend([False] * len(briefs))
        return False
    else:
        decision_details["averageViewPercentageCheck"] = True
        return True

def check_manual_captions(video_id, video_data, decision_details, briefs):
    """Check if the video has manual captions."""
    if video_data.get("caption"):
        bt.logging.info(f"Manual captions detected for video: {video_data['bitcastVideoId']} - skipping eval")
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
            bt.logging.warning(f"Error retrieving transcript for video: {video_data['bitcastVideoId']} - {e}")
            transcript = None

    if transcript is None:
        bt.logging.warning(f"Transcript retrieval failed for video: {video_data['bitcastVideoId']} - exiting early")
        return None
        
    return transcript

def check_prompt_injection(video_id, video_data, transcript, decision_details, briefs):
    """Check if the video contains prompt injection."""
    if check_for_prompt_injection(video_data["description"], transcript):
        bt.logging.warning(f"Prompt injection detected for video: {video_data['bitcastVideoId']} - skipping eval")
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
            bt.logging.error(f"Error evaluating brief {brief['id']} for video: {video_data['bitcastVideoId']}: {e}")
            decision_details["contentAgainstBriefCheck"].append(False)
            
    return met_brief_ids

def calculate_video_score(video_id, youtube_analytics_client):
    """Calculate the score for a video based on analytics data."""
    start_date = (datetime.now() - timedelta(days=YT_REWARD_DELAY + YT_ROLLING_WINDOW - 1)).strftime('%Y-%m-%d')
    end_date = (datetime.now() - timedelta(days=YT_REWARD_DELAY)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')

    # Get all analytics data from start_date to today
    daily_analytics = youtube_utils.get_video_analytics(youtube_analytics_client, video_id, start_date, today, dimensions='day')

    # Calculate score using only the data between start_date and end_date
    scoreable_days = [item for item in daily_analytics if item.get('day', '') <= end_date]
    total_minutes_watched = sum(item.get('estimatedMinutesWatched', 0) for item in scoreable_days)

    # Return both the score and the daily analytics data
    return {
        "score": total_minutes_watched,
        "daily_analytics": daily_analytics
    } 