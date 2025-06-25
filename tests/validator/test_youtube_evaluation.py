import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import bittensor as bt
from bitcast.validator.socials.youtube.evaluation import (
    vet_channel,
    calculate_channel_age,
    check_channel_criteria,
    process_video_vetting,
    check_video_publish_date,
    check_video_retention,
    vet_videos
)
from bitcast.validator.utils.config import (
    YT_MIN_SUBS,
    YT_MAX_SUBS,
    YT_MIN_CHANNEL_AGE,
    YT_MIN_CHANNEL_RETENTION,
    YT_MIN_VIDEO_RETENTION,
    YT_MIN_MINS_WATCHED,
    YT_LOOKBACK,
    YT_VIDEO_RELEASE_BUFFER
)

# ============================================================================
# Channel Evaluation Tests
# ============================================================================

@pytest.fixture(autouse=True)
def mock_blacklist():
    with patch('bitcast.validator.utils.blacklist.get_blacklist') as mock_get_blacklist:
        mock_get_blacklist.return_value = []  # Return empty blacklist
        yield mock_get_blacklist

def test_calculate_channel_age():
    """Test channel age calculation with different date formats."""
    # Test case 1: Standard date format
    channel_data1 = {"channel_start": "2023-01-01T00:00:00Z"}
    age1 = calculate_channel_age(channel_data1)
    expected_age1 = (datetime.now() - datetime.strptime("2023-01-01T00:00:00Z", '%Y-%m-%dT%H:%M:%SZ')).days
    assert age1 == expected_age1

    # Test case 2: Date format with milliseconds
    channel_data2 = {"channel_start": "2023-01-01T00:00:00.000Z"}
    age2 = calculate_channel_age(channel_data2)
    expected_age2 = (datetime.now() - datetime.strptime("2023-01-01T00:00:00.000Z", '%Y-%m-%dT%H:%M:%S.%fZ')).days
    assert age2 == expected_age2

def test_check_channel_criteria():
    """Test channel criteria validation with different scenarios."""
    # Test case 1: Channel meets all criteria
    channel_data = {
        "bitcastChannelId": "test_channel_1",
        "subCount": str(YT_MIN_SUBS + 1000),
        "channel_start": (datetime.now() - timedelta(days=YT_MIN_CHANNEL_AGE + 10)).strftime('%Y-%m-%dT%H:%M:%SZ')
    }
    channel_analytics = {
        "averageViewPercentage": YT_MIN_CHANNEL_RETENTION + 5,
        "estimatedMinutesWatched": YT_MIN_MINS_WATCHED + 1000,
        "playbackBasedCpm": 1.5  # Add this to pass acceptance filter
    }
    channel_age_days = YT_MIN_CHANNEL_AGE + 10
    assert check_channel_criteria(channel_data, channel_analytics, channel_age_days) == True

    # Test case 2: Channel too young
    channel_data["channel_start"] = (datetime.now() - timedelta(days=YT_MIN_CHANNEL_AGE - 10)).strftime('%Y-%m-%dT%H:%M:%SZ')
    channel_age_days = YT_MIN_CHANNEL_AGE - 10
    assert check_channel_criteria(channel_data, channel_analytics, channel_age_days) == False

    # Test case 3: Insufficient subscribers
    channel_data["subCount"] = str(YT_MIN_SUBS - 100)
    channel_age_days = YT_MIN_CHANNEL_AGE + 10
    assert check_channel_criteria(channel_data, channel_analytics, channel_age_days) == False

    # Test case 4: Low retention
    channel_analytics["averageViewPercentage"] = YT_MIN_CHANNEL_RETENTION - 5
    channel_data["subCount"] = str(YT_MIN_SUBS + 1000)
    assert check_channel_criteria(channel_data, channel_analytics, channel_age_days) == False

    # Test case 5: Insufficient minutes watched
    channel_analytics["averageViewPercentage"] = YT_MIN_CHANNEL_RETENTION + 5
    channel_analytics["estimatedMinutesWatched"] = YT_MIN_MINS_WATCHED - 100
    assert check_channel_criteria(channel_data, channel_analytics, channel_age_days) == False

    # Test case 6: Too many subscribers (exceeds maximum)
    channel_analytics["estimatedMinutesWatched"] = YT_MIN_MINS_WATCHED + 1000
    channel_data["subCount"] = str(YT_MAX_SUBS + 1000)  # 201k subscribers
    assert check_channel_criteria(channel_data, channel_analytics, channel_age_days) == False

def test_vet_channel_blacklisted(mock_blacklist):
    """Test that vet_channel fails when channel is blacklisted."""
    # Setup test data
    channel_data = {
        "bitcastChannelId": "blacklisted_channel",
        "subCount": str(YT_MIN_SUBS + 1000),
        "channel_start": (datetime.now() - timedelta(days=YT_MIN_CHANNEL_AGE + 10)).strftime('%Y-%m-%dT%H:%M:%SZ')
    }
    channel_analytics = {
        "averageViewPercentage": YT_MIN_CHANNEL_RETENTION + 5,
        "estimatedMinutesWatched": YT_MIN_MINS_WATCHED + 1000
    }
    
    # Mock blacklist to include our test channel
    mock_blacklist.return_value = ["blacklisted_channel"]
    
    # Channel should fail vetting even if it meets all other criteria
    vet_result, is_blacklisted = vet_channel(channel_data, channel_analytics)
    assert vet_result == False
    assert is_blacklisted == True
    mock_blacklist.assert_called_once()

def test_vet_channel_not_blacklisted(mock_blacklist):
    """Test that vet_channel proceeds with normal checks when channel is not blacklisted."""
    # Setup test data
    channel_data = {
        "bitcastChannelId": "valid_channel",
        "subCount": str(YT_MIN_SUBS + 1000),
        "channel_start": (datetime.now() - timedelta(days=YT_MIN_CHANNEL_AGE + 10)).strftime('%Y-%m-%dT%H:%M:%SZ')
    }
    channel_analytics = {
        "averageViewPercentage": YT_MIN_CHANNEL_RETENTION + 5,
        "estimatedMinutesWatched": YT_MIN_MINS_WATCHED + 1000,
        "playbackBasedCpm": 1.5  # Add this to pass acceptance filter
    }
    
    # Mock blacklist to be empty
    mock_blacklist.return_value = []
    
    # Channel should pass vetting if it meets all criteria
    vet_result, is_blacklisted = vet_channel(channel_data, channel_analytics)
    assert vet_result == True
    assert is_blacklisted == False
    mock_blacklist.assert_called_once()

def test_vet_channel():
    """Test channel vetting with different scenarios."""
    # Test case 1: Channel passes all checks
    channel_data = {
        "bitcastChannelId": "test_channel_1",
        "subCount": str(YT_MIN_SUBS + 1000),
        "channel_start": (datetime.now() - timedelta(days=YT_MIN_CHANNEL_AGE + 10)).strftime('%Y-%m-%dT%H:%M:%SZ')
    }
    channel_analytics = {
        "averageViewPercentage": YT_MIN_CHANNEL_RETENTION + 5,
        "estimatedMinutesWatched": YT_MIN_MINS_WATCHED + 1000,
        "playbackBasedCpm": 1.5  # Add this to pass acceptance filter
    }
    vet_result, is_blacklisted = vet_channel(channel_data, channel_analytics)
    assert vet_result == True
    assert is_blacklisted == False

    # Test case 2: Channel fails age check
    channel_data["channel_start"] = (datetime.now() - timedelta(days=YT_MIN_CHANNEL_AGE - 10)).strftime('%Y-%m-%dT%H:%M:%SZ')
    vet_result, is_blacklisted = vet_channel(channel_data, channel_analytics)
    assert vet_result == False
    assert is_blacklisted == False

def test_acceptance_filter():
    """Test the new acceptance filter for YouTube Partner Program (YPP) membership and min_stake."""
    # Setup base channel data that meets all other criteria
    channel_data = {
        "bitcastChannelId": "test_channel_acceptance",
        "subCount": str(YT_MIN_SUBS + 1000),
        "channel_start": (datetime.now() - timedelta(days=YT_MIN_CHANNEL_AGE + 10)).strftime('%Y-%m-%dT%H:%M:%SZ')
    }
    channel_analytics = {
        "averageViewPercentage": YT_MIN_CHANNEL_RETENTION + 5,
        "estimatedMinutesWatched": YT_MIN_MINS_WATCHED + 1000
    }
    
    # Test case 1: Channel passes with YPP membership (playbackBasedCpm > 0)
    channel_analytics["playbackBasedCpm"] = 1.5
    vet_result, is_blacklisted = vet_channel(channel_data, channel_analytics)
    assert vet_result == True
    assert is_blacklisted == False
    
    # Test case 2: Channel fails when not YPP member (playbackBasedCpm = 0) and min_stake = False
    channel_analytics["playbackBasedCpm"] = 0
    vet_result, is_blacklisted = vet_channel(channel_data, channel_analytics, min_stake=False)
    assert vet_result == False
    assert is_blacklisted == False
    
    # Test case 3: Channel fails when not YPP member (no playbackBasedCpm field) and min_stake = False
    del channel_analytics["playbackBasedCpm"]
    vet_result, is_blacklisted = vet_channel(channel_data, channel_analytics, min_stake=False)
    assert vet_result == False
    assert is_blacklisted == False
    
    # Test case 4: Channel passes with min_stake = True when not YPP member (high stake bypass)
    vet_result, is_blacklisted = vet_channel(channel_data, channel_analytics, min_stake=True)
    assert vet_result == True
    assert is_blacklisted == False
    
    # Test case 5: Channel fails with min_stake = False when not YPP member
    vet_result, is_blacklisted = vet_channel(channel_data, channel_analytics, min_stake=False)
    assert vet_result == False
    assert is_blacklisted == False
    
    # Test case 6: Channel passes with YPP membership even with min_stake = False
    channel_analytics["playbackBasedCpm"] = 2.0
    vet_result, is_blacklisted = vet_channel(channel_data, channel_analytics, min_stake=False)
    assert vet_result == True
    assert is_blacklisted == False

# ============================================================================
# Video Evaluation Tests
# ============================================================================

def test_check_video_publish_date():
    """Test video publish date validation with different scenarios."""

    # Setup test briefs with different dates
    briefs = [
        {"id": "brief1", "start_date": "2023-01-01"},  # Earliest allowed: Dec 29
        {"id": "brief2", "start_date": "2023-02-01"},  # Earliest allowed: Jan 29
        {"id": "brief3", "start_date": "2023-03-01"}   # Earliest allowed: Feb 26
    ]
    
    # Test case 1: Video published before ANY brief's earliest allowed date (should fail)
    video_data = {
        "publishedAt": "2022-12-28T00:00:00Z"  # Dec 28, before brief1's Dec 29
    }
    decision_details = {"contentAgainstBriefCheck": []}
    assert check_video_publish_date(video_data, briefs, decision_details) == False
    assert decision_details["publishDateCheck"] == False

    # Test case 2: Video published after ALL briefs' earliest allowed dates (should pass)
    video_data["publishedAt"] = "2023-02-27T00:00:00Z"  # Feb 27, after all earliest allowed dates
    decision_details = {"contentAgainstBriefCheck": []}
    assert check_video_publish_date(video_data, briefs, decision_details) == True
    assert decision_details["publishDateCheck"] == True

    # Test case 3: Video published one day after earliest brief's allowed date (should pass)
    video_data["publishedAt"] = "2022-12-30T00:00:00Z"  # Dec 30, one day after brief1's Dec 29
    decision_details = {"contentAgainstBriefCheck": []}
    assert check_video_publish_date(video_data, briefs, decision_details) == True
    assert decision_details["publishDateCheck"] == True

    # Test case 4: Video published before earliest brief's allowed date (should fail)
    video_data["publishedAt"] = "2022-12-28T12:34:56Z"  # Dec 28, before brief1's Dec 29
    decision_details = {"contentAgainstBriefCheck": []}
    assert check_video_publish_date(video_data, briefs, decision_details) == False
    assert decision_details["publishDateCheck"] == False

    # Test case 5: Video published with different time components (should pass if after all earliest allowed dates)
    video_data["publishedAt"] = "2023-02-27T23:59:59Z"  # Different time, same day as test case 2
    decision_details = {"contentAgainstBriefCheck": []}
    assert check_video_publish_date(video_data, briefs, decision_details) == True
    assert decision_details["publishDateCheck"] == True

    # Test case 6: Invalid date format (should fail)
    video_data["publishedAt"] = "invalid-date"
    decision_details = {"contentAgainstBriefCheck": []}
    assert check_video_publish_date(video_data, briefs, decision_details) == False
    assert decision_details["publishDateCheck"] == False

    # Test case 7: Missing publishedAt field (should fail)
    video_data = {}
    decision_details = {"contentAgainstBriefCheck": []}
    assert check_video_publish_date(video_data, briefs, decision_details) == False
    assert decision_details["publishDateCheck"] == False

    # Test case 8: Empty briefs list (should pass - no briefs means no date restrictions)
    video_data = {"publishedAt": "2023-01-15T00:00:00Z"}
    decision_details = {"contentAgainstBriefCheck": []}
    assert check_video_publish_date(video_data, [], decision_details) == True
    assert decision_details["publishDateCheck"] == True

    # Test case 9: Malformed brief date (should fail)
    malformed_briefs = [{"id": "brief1", "start_date": "invalid-date"}]
    video_data = {"publishedAt": "2023-01-15T00:00:00Z"}
    decision_details = {"contentAgainstBriefCheck": []}
    assert check_video_publish_date(video_data, malformed_briefs, decision_details) == False
    assert decision_details["publishDateCheck"] == False

def test_check_video_retention():
    """Test video retention validation with different scenarios."""
    # Test case 1: Video meets retention criteria
    video_data = {"bitcastVideoId": "test_video_1"}
    video_analytics = {"averageViewPercentage": YT_MIN_VIDEO_RETENTION + 5}
    decision_details = {"contentAgainstBriefCheck": []}
    
    assert check_video_retention(video_data, video_analytics, decision_details) == True
    assert decision_details["averageViewPercentageCheck"] == True

    # Test case 2: Video fails retention criteria
    video_analytics["averageViewPercentage"] = YT_MIN_VIDEO_RETENTION - 5
    decision_details = {"contentAgainstBriefCheck": []}
    
    assert check_video_retention(video_data, video_analytics, decision_details) == False
    assert decision_details["averageViewPercentageCheck"] == False
    # We don't check contentAgainstBriefCheck as the implementation doesn't modify it

    # Test case 3: Missing analytics data
    video_analytics = {}
    decision_details = {"contentAgainstBriefCheck": []}
    
    assert check_video_retention(video_data, video_analytics, decision_details) == False
    assert decision_details["averageViewPercentageCheck"] == False

@pytest.mark.asyncio
@patch('bitcast.validator.socials.youtube.api.clients.build')
@patch('bitcast.validator.socials.youtube.evaluation.video.get_video_data_batch')
@patch('bitcast.validator.socials.youtube.evaluation.video.get_video_analytics')
@patch('bitcast.validator.socials.youtube.evaluation.video.get_video_transcript')
@patch('bitcast.validator.socials.youtube.evaluation.video.state.is_video_already_scored')
@patch('bitcast.validator.socials.youtube.evaluation.video.state.mark_video_as_scored')
@patch('bitcast.validator.socials.youtube.evaluation.video.check_for_prompt_injection')
@patch('bitcast.validator.socials.youtube.evaluation.video.evaluate_content_against_brief')
@patch('bitcast.validator.utils.config.DISABLE_LLM_CACHING', True)
async def test_process_video_vetting(mock_evaluate_content, mock_check_injection, mock_mark_video_as_scored, 
                        mock_is_video_already_scored, mock_get_transcript,
                        mock_get_video_analytics, mock_get_video_data_batch, mock_build):
    """Test the complete video vetting process."""
    # Setup test data
    video_id = "test_video_1"
    briefs = [{
        "id": "brief1", 
        "title": "Test Brief 1",
        "brief": "Test Brief Description",  # Added missing brief field
        "start_date": "2023-01-01"
    }]
    youtube_data_client = MagicMock()
    youtube_analytics_client = MagicMock()
    results = {}
    video_decision_details = {}

    # Mock video data
    video_data = {
        "bitcastVideoId": video_id,
        "title": "Test Video",
        "description": "Test Description",
        "publishedAt": "2023-01-15T00:00:00Z",
        "duration": "PT10M",
        "caption": False,
        "privacyStatus": "public",
        "transcript": "Test transcript content"  # Add mock transcript
    }

    # Mock video analytics
    video_analytics = {
        "averageViewPercentage": YT_MIN_VIDEO_RETENTION + 5,
        "estimatedMinutesWatched": 1000
    }

    # Mock OpenAI client functions at the high level
    mock_check_injection.return_value = False          # No prompt injection detected
    mock_evaluate_content.return_value = (True, "Video meets the brief criteria")  # Brief evaluation passes

    # Mock transcript retrieval (shouldn't be called due to transcript in video_data)
    mock_get_transcript.return_value = "Test transcript content"
    
    # Mock video scoring state management
    mock_is_video_already_scored.return_value = False  # Video hasn't been scored yet
    mock_mark_video_as_scored.return_value = None      # Mark as scored (void function)

    # Process the video - pass individual video data and analytics, not dictionaries
    process_video_vetting(
        video_id,
        briefs,
        youtube_data_client,
        youtube_analytics_client,
        results,
        video_data,        # Individual video data
        video_analytics,   # Individual video analytics  
        video_decision_details
    )

    # Verify results - the function should populate results and video_decision_details
    assert video_id in results
    assert video_id in video_decision_details
    assert results[video_id] == [True]
    assert video_decision_details[video_id]["contentAgainstBriefCheck"] == [True]
    assert video_decision_details[video_id]["publicVideo"] == True
    assert video_decision_details[video_id]["publishDateCheck"] == True
    assert video_decision_details[video_id]["averageViewPercentageCheck"] == True
    assert video_decision_details[video_id]["manualCaptionsCheck"] == True
    assert video_decision_details[video_id]["promptInjectionCheck"] == True 
