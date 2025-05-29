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
    YT_VIDEO_RELEASE_BUFFER,
    ECO_MODE,
    BITCAST_BLACKLIST_SOURCES_ENDPOINT
)
from bitcast.validator.socials.youtube.config import get_youtube_metrics, get_advanced_metrics
from bitcast.validator.utils.blacklist import is_blacklisted, get_blacklist_sources
import requests

def vet_channel(channel_data, channel_analytics):
    bt.logging.info(f"Checking channel")

    # Check if channel is blacklisted
    if is_blacklisted(channel_data["bitcastChannelId"]):
        bt.logging.warning(f"Channel is blacklisted: {channel_data['bitcastChannelId']}")
        return False

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
            
            # Only mark the video as scored if processing was successful
            youtube_utils.mark_video_as_scored(video_id)
            
        except Exception as e:
            bt.logging.error(f"Error evaluating video {youtube_utils._format_error(e)}")
            # Mark this video as not matching any briefs
            results[video_id] = [False] * len(briefs)
            # Don't mark the video as scored if there was an error

    return results, video_data_dict, video_analytics_dict, video_decision_details

def process_video_vetting(video_id, briefs, youtube_data_client, youtube_analytics_client, 
                         results, video_data_dict, video_analytics_dict, video_decision_details):
    """Process the vetting of a single video."""
    # Get video data and analytics
    video_data = youtube_utils.get_video_data(youtube_data_client, video_id, DISCRETE_MODE)
    
    # Get all metrics from config using the helper function
    all_metric_dims = get_youtube_metrics(eco_mode=ECO_MODE, for_daily=False)
    
    # Get all analytics in a single call
    video_analytics = youtube_utils.get_video_analytics(youtube_analytics_client, video_id, metric_dims=all_metric_dims)
    
    # Store video data and analytics regardless of vetting result
    video_data_dict[video_id] = video_data
    video_analytics_dict[video_id] = video_analytics

    # Get decision details for the video
    vet_result = vet_video(video_id, briefs, video_data, video_analytics)
    decision_details = vet_result["decision_details"]
    results[video_id] = decision_details["contentAgainstBriefCheck"]
    video_decision_details[video_id] = decision_details
    
    # Retrieve advanced metrics only for qualified videos when not in eco mode
    if not ECO_MODE and decision_details.get("anyBriefMatched", False):
        bt.logging.info(f"Fetching advanced metrics.")
        advanced_metrics = get_advanced_metrics()
        advanced_analytics = youtube_utils.get_video_analytics(youtube_analytics_client, video_id, metric_dims=advanced_metrics)
        video_analytics_dict[video_id].update(advanced_analytics)
    
    valid_checks = [check for check in decision_details["contentAgainstBriefCheck"] if check is not None]
    bt.logging.info(f"Video meets {sum(valid_checks)} briefs.")


def vet_video(video_id, briefs, video_data, video_analytics):
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
    if not check_video_publish_date(video_data, briefs, decision_details):
        if handle_check_failure():
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
        transcript = get_video_transcript(video_id, video_data)
        if transcript is None:
            decision_details["video_vet_result"] = False
            decision_details["promptInjectionCheck"] = False
            decision_details["contentAgainstBriefCheck"] = [False] * len(briefs)
            brief_reasonings = ["Failed to get video transcript"] * len(briefs)
        else:
            # Check for prompt injection
            if not check_prompt_injection(video_id, video_data, transcript, decision_details):
                decision_details["video_vet_result"] = False
                decision_details["contentAgainstBriefCheck"] = [False] * len(briefs)
                brief_reasonings = ["Video failed prompt injection check"] * len(briefs)
            else:
                # Evaluate content against briefs only if prompt injection check passed
                met_brief_ids, brief_reasonings = evaluate_content_against_briefs(briefs, video_data, transcript, decision_details)
    else:
        # If any check failed, set all briefs to false and prompt injection to false
        decision_details["promptInjectionCheck"] = False
        decision_details["contentAgainstBriefCheck"] = [False] * len(briefs)
        brief_reasonings = ["Video failed initial checks"] * len(briefs)
    
    # Set anyBriefMatched based on whether any brief matched
    decision_details["anyBriefMatched"] = any(decision_details["contentAgainstBriefCheck"])
    
    # Return the final result
    return {"met_brief_ids": met_brief_ids, "decision_details": decision_details, "brief_reasonings": brief_reasonings}

def initialize_decision_details():
    """Initialize the decision details structure."""
    return {
        "averageViewPercentageCheck": None,
        "manualCaptionsCheck": None,
        "promptInjectionCheck": None,
        "contentAgainstBriefCheck": [],
        "publicVideo": None,
        "publishDateCheck": None,
        "video_vet_result": True
    }

def check_video_privacy(video_data, decision_details):
    """Check if the video is public."""
    if video_data.get("privacyStatus") != "public":
        bt.logging.warning(f"Video is not public")
        decision_details["publicVideo"] = False
        return False
    else:
        decision_details["publicVideo"] = True
        return True

def check_video_publish_date(video_data, briefs, decision_details):
    """Check if the video was published after the earliest brief's start date (minus buffer days)."""
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
        bt.logging.error(f"Error checking video publish date: {e}")
        decision_details["publishDateCheck"] = False
        return False

def check_video_retention(video_data, video_analytics, decision_details):
    """Check if the video meets the minimum retention criteria."""
    averageViewPercentage = float(video_analytics.get("averageViewPercentage", -1))
    if averageViewPercentage < YT_MIN_VIDEO_RETENTION:
        bt.logging.info(f"Avg retention check failed for video: {video_data['bitcastVideoId']}. {averageViewPercentage} <= {YT_MIN_VIDEO_RETENTION}%.")
        decision_details["averageViewPercentageCheck"] = False
        return False
    else:
        decision_details["averageViewPercentageCheck"] = True
        return True

def check_manual_captions(video_id, video_data, decision_details):
    """Check if the video has manual captions."""
    if video_data.get("caption"):
        bt.logging.info(f"Manual captions detected for video: {video_data['bitcastVideoId']} - skipping eval")
        decision_details["manualCaptionsCheck"] = False
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
            bt.logging.warning(f"Error retrieving transcript for video: {video_data['bitcastVideoId']} - {youtube_utils._format_error(e)}")
            transcript = None

    if transcript is None:
        bt.logging.warning(f"Transcript retrieval failed for video: {video_data['bitcastVideoId']}")
        return None
        
    return transcript

def check_prompt_injection(video_id, video_data, transcript, decision_details):
    """Check if the video contains prompt injection."""
    if check_for_prompt_injection(video_data["description"], transcript):
        bt.logging.warning(f"Prompt injection detected for video: {video_data['bitcastVideoId']} - skipping eval")
        decision_details["promptInjectionCheck"] = False
        return False
    else:
        decision_details["promptInjectionCheck"] = True
        return True

def evaluate_content_against_briefs(briefs, video_data, transcript, decision_details):
    """Evaluate the video content against each brief."""
    met_brief_ids = []
    reasonings = []  # Store reasonings separately

    for brief in briefs:
        try:
            match, reasoning = evaluate_content_against_brief(brief, video_data['duration'], video_data['description'], transcript)
            decision_details["contentAgainstBriefCheck"].append(match)
            reasonings.append(reasoning)  # Store reasoning in separate list
            if match:
                met_brief_ids.append(brief["id"])
        except Exception as e:
            bt.logging.error(f"Error evaluating brief {brief['id']} for video: {video_data['bitcastVideoId']}: {youtube_utils._format_error(e)}")
            decision_details["contentAgainstBriefCheck"].append(False)
            reasonings.append(f"Error during evaluation: {str(e)}")  # Store error as reasoning
            
    return met_brief_ids, reasonings

def calculate_blacklisted_ext_url_proportion(analytics_result, blacklisted_sources):
    """Calculate what proportion of lifetime EXT_URL traffic comes from blacklisted sources."""
    ext_url_lifetime = analytics_result.get("insightTrafficSourceDetail_EXT_URL", {})
    if not ext_url_lifetime:
        return 0.0
    
    total_ext_url_minutes = analytics_result.get("trafficSourceMinutes", {}).get("EXT_URL", 0)
    blacklisted_ext_url_minutes = sum(
        ext_url_lifetime.get(url, 0)
        for url in blacklisted_sources
    )
    
    blacklisted_ext_url_proportion = blacklisted_ext_url_minutes / total_ext_url_minutes if total_ext_url_minutes > 0 else 0.0

    if blacklisted_ext_url_proportion != 1:
        bt.logging.info(f"Blacklisted EXT_URL proportion: {blacklisted_ext_url_proportion}")
        
    return blacklisted_ext_url_proportion

def get_scorable_minutes(day_data, blacklisted_sources, blacklisted_ext_url_proportion):
    """Calculate minutes watched excluding blacklisted sources for a given day."""
    traffic_source_minutes = day_data.get('trafficSourceMinutes', {})
    
    if not traffic_source_minutes:
        return day_data.get('estimatedMinutesWatched', 0)
    
    total_minutes = sum(traffic_source_minutes.values())
    
    # Calculate minutes from blacklisted traffic sources (excluding EXT_URL for now)
    blacklisted_traffic_minutes = sum(
        traffic_source_minutes.get(source, 0) 
        for source in blacklisted_sources
        if source != "EXT_URL"  # Handle EXT_URL separately
    )
    
    # Handle EXT_URL traffic using the calculated proportion
    ext_url_daily_minutes = traffic_source_minutes.get('EXT_URL', 0)
    blacklisted_ext_url_daily_minutes = ext_url_daily_minutes * blacklisted_ext_url_proportion
    
    return max(0, total_minutes - blacklisted_traffic_minutes - blacklisted_ext_url_daily_minutes)

def calculate_video_score(video_id, youtube_analytics_client, video_publish_date):
    """Calculate the score for a video based on analytics data."""
    # Use video publish date as query start date if provided, otherwise use default
    try:
        publish_datetime = datetime.strptime(video_publish_date, '%Y-%m-%dT%H:%M:%SZ')
        query_start_date = publish_datetime.strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        bt.logging.warning(f"Failed to parse video publish date: {video_publish_date}, using default")
        query_start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    
    start_date = (datetime.now() - timedelta(days=YT_REWARD_DELAY + YT_ROLLING_WINDOW - 1)).strftime('%Y-%m-%d')
    end_date = (datetime.now() - timedelta(days=YT_REWARD_DELAY)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')

    # Get daily metrics from config
    metric_dims = get_youtube_metrics(eco_mode=ECO_MODE, for_daily=True)    
    analytics_result = youtube_utils.get_video_analytics(
        youtube_analytics_client, 
        video_id, 
        query_start_date,
        today, 
        metric_dims=metric_dims
    )
    
    daily_analytics = sorted(analytics_result.get("day_metrics", {}).values(), key=lambda x: x.get("day", ""))
    
    # Get blacklist sources once and reuse
    blacklisted_sources = get_blacklist_sources()
    
    # Calculate the proportion of blacklisted EXT_URL traffic from lifetime data
    blacklisted_ext_url_proportion = calculate_blacklisted_ext_url_proportion(analytics_result, blacklisted_sources)
    
    # Calculate score using only the data between start_date and end_date, excluding blacklisted traffic
    scoreable_days = [item for item in daily_analytics if start_date <= item.get('day', '') <= end_date]
    score = sum(get_scorable_minutes(item, blacklisted_sources, blacklisted_ext_url_proportion) for item in scoreable_days)

    scoreable_history_days = [item for item in daily_analytics if item.get('day', '') <= end_date]
    scorableHistoryMins = sum(get_scorable_minutes(item, blacklisted_sources, blacklisted_ext_url_proportion) for item in scoreable_history_days)

    return {
        "score": score,
        "scorableHistoryMins": scorableHistoryMins,
        "daily_analytics": daily_analytics
    } 