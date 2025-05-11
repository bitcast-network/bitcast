import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import bittensor as bt
from bitcast.validator.socials.youtube.youtube_evaluation import (
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
        "estimatedMinutesWatched": YT_MIN_MINS_WATCHED + 1000
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

@patch('bitcast.validator.utils.blacklist.get_blacklist')
def test_vet_channel_blacklisted(mock_get_blacklist):
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
    mock_get_blacklist.return_value = ["blacklisted_channel"]
    
    # Channel should fail vetting even if it meets all other criteria
    result = vet_channel(channel_data, channel_analytics)
    assert result == False
    mock_get_blacklist.assert_called_once()

@patch('bitcast.validator.utils.blacklist.get_blacklist')
def test_vet_channel_not_blacklisted(mock_get_blacklist):
    """Test that vet_channel proceeds with normal checks when channel is not blacklisted."""
    # Setup test data
    channel_data = {
        "bitcastChannelId": "valid_channel",
        "subCount": str(YT_MIN_SUBS + 1000),
        "channel_start": (datetime.now() - timedelta(days=YT_MIN_CHANNEL_AGE + 10)).strftime('%Y-%m-%dT%H:%M:%SZ')
    }
    channel_analytics = {
        "averageViewPercentage": YT_MIN_CHANNEL_RETENTION + 5,
        "estimatedMinutesWatched": YT_MIN_MINS_WATCHED + 1000
    }
    
    # Mock blacklist to be empty
    mock_get_blacklist.return_value = []
    
    # Channel should pass vetting if it meets all criteria
    result = vet_channel(channel_data, channel_analytics)
    assert result == True
    mock_get_blacklist.assert_called_once()

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
        "estimatedMinutesWatched": YT_MIN_MINS_WATCHED + 1000
    }
    assert vet_channel(channel_data, channel_analytics) == True

    # Test case 2: Channel fails age check
    channel_data["channel_start"] = (datetime.now() - timedelta(days=YT_MIN_CHANNEL_AGE - 10)).strftime('%Y-%m-%dT%H:%M:%SZ')
    assert vet_channel(channel_data, channel_analytics) == False

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
    assert len(decision_details["contentAgainstBriefCheck"]) == len(briefs)
    assert all(not check for check in decision_details["contentAgainstBriefCheck"])

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
    briefs = [{"id": "brief1"}]
    
    assert check_video_retention(video_data, video_analytics, decision_details, briefs) == True
    assert decision_details["averageViewPercentageCheck"] == True

    # Test case 2: Video fails retention criteria
    video_analytics["averageViewPercentage"] = YT_MIN_VIDEO_RETENTION - 5
    decision_details = {"contentAgainstBriefCheck": []}
    
    assert check_video_retention(video_data, video_analytics, decision_details, briefs) == False
    assert decision_details["averageViewPercentageCheck"] == False
    assert len(decision_details["contentAgainstBriefCheck"]) == len(briefs)
    assert all(not check for check in decision_details["contentAgainstBriefCheck"])

    # Test case 3: Missing analytics data
    video_analytics = {}
    decision_details = {"contentAgainstBriefCheck": []}
    
    assert check_video_retention(video_data, video_analytics, decision_details, briefs) == False
    assert decision_details["averageViewPercentageCheck"] == False

def test_process_video_vetting():
    """Test the complete video vetting process."""
    # Setup test data
    video_id = "test_video_1"
    briefs = [{"id": "brief1"}]
    youtube_data_client = MagicMock()
    youtube_analytics_client = MagicMock()
    results = {}
    video_data_dict = {}
    video_analytics_dict = {}
    video_decision_details = {}

    # Mock video data
    video_data = {
        "bitcastVideoId": video_id,
        "title": "Test Video",
        "description": "Test Description",
        "publishedAt": "2023-01-15T00:00:00Z",
        "duration": "PT10M",
        "caption": False,
        "privacyStatus": "public"
    }

    # Mock video analytics
    video_analytics = {
        "averageViewPercentage": YT_MIN_VIDEO_RETENTION + 5,
        "estimatedMinutesWatched": 1000
    }

    # Mock YouTube API responses
    with patch('bitcast.validator.socials.youtube.youtube_utils.get_video_data', return_value=video_data):
        with patch('bitcast.validator.socials.youtube.youtube_utils.get_video_analytics', return_value=video_analytics):
            with patch('bitcast.validator.socials.youtube.youtube_evaluation.vet_video', return_value={
                "met_brief_ids": ["brief1"],
                "decision_details": {
                    "contentAgainstBriefCheck": [True],
                    "publicVideo": True,
                    "publishDateCheck": True,
                    "averageViewPercentageCheck": True,
                    "manualCaptionsCheck": True,
                    "promptInjectionCheck": True
                }
            }):
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

                # Verify results
                assert video_id in results
                assert video_id in video_data_dict
                assert video_id in video_analytics_dict
                assert video_id in video_decision_details
                assert results[video_id] == [True]
                assert video_data_dict[video_id] == video_data
                assert video_analytics_dict[video_id] == video_analytics
                assert video_decision_details[video_id]["contentAgainstBriefCheck"] == [True]

# ============================================================================
# Cache Integration Tests
# ============================================================================

def test_vet_videos_cache_usage():
    """Test that vet_videos correctly uses cached data for videos that failed publishDateCheck."""
    # Setup
    video_id = "test_video_1"
    briefs = [{"id": "test_brief"}]
    youtube_data_client = MagicMock()
    youtube_analytics_client = MagicMock()
    
    # Mock cached data with failed publishDateCheck
    cached_data = {
        "results": [False],
        "video_data": {"title": "Cached Video"},
        "video_analytics": {"views": 100},
        "decision_details": {"publishDateCheck": False}
    }
    
    # Mock the cache to return our test data
    with patch('bitcast.validator.socials.youtube.youtube_utils.youtube_cache.get_video_cache', return_value=cached_data):
        # Mock is_video_already_scored to return False
        with patch('bitcast.validator.socials.youtube.youtube_utils.is_video_already_scored', return_value=False):
            # Run vet_videos
            results, video_data_dict, video_analytics_dict, video_decision_details = vet_videos(
                [video_id], briefs, youtube_data_client, youtube_analytics_client
            )
            
            # Verify cached data was used
            assert results[video_id] == cached_data["results"]
            assert video_data_dict[video_id] == cached_data["video_data"]
            assert video_analytics_dict[video_id] == cached_data["video_analytics"]
            expected_decision_details = {**cached_data["decision_details"], "cache_used": True}
            assert video_decision_details[video_id] == expected_decision_details

def test_vet_videos_cache_with_none_publish_date_check():
    """Test that vet_videos does not use cached data when publishDateCheck is None."""
    # Setup
    video_id = "test_video_1"
    briefs = [{"id": "test_brief"}]
    youtube_data_client = MagicMock()
    youtube_analytics_client = MagicMock()
    
    # Mock cached data with None publishDateCheck
    cached_data = {
        "results": [False],
        "video_data": {"title": "Cached Video"},
        "video_analytics": {"views": 100},
        "decision_details": {"publishDateCheck": None}
    }
    
    # Mock the cache to return our test data
    with patch('bitcast.validator.socials.youtube.youtube_utils.youtube_cache.get_video_cache', return_value=cached_data):
        # Mock is_video_already_scored to return False
        with patch('bitcast.validator.socials.youtube.youtube_utils.is_video_already_scored', return_value=False):
            # Mock process_video_vetting to return different data
            mock_results = {video_id: [True]}
            mock_video_data = {video_id: {"title": "New Video"}}
            mock_analytics = {video_id: {"views": 200}}
            mock_details = {video_id: {"publishDateCheck": True}}
            
            with patch('bitcast.validator.socials.youtube.youtube_evaluation.process_video_vetting') as mock_process:
                # Mock the process_video_vetting function to update the results dictionary
                def mock_process_impl(video_id, briefs, youtube_data_client, youtube_analytics_client, results, video_data_dict, video_analytics_dict, video_decision_details):
                    results[video_id] = mock_results[video_id]
                    video_data_dict[video_id] = mock_video_data[video_id]
                    video_analytics_dict[video_id] = mock_analytics[video_id]
                    video_decision_details[video_id] = mock_details[video_id]
                
                mock_process.side_effect = mock_process_impl
                
                # Run vet_videos
                results, video_data_dict, video_analytics_dict, video_decision_details = vet_videos(
                    [video_id], briefs, youtube_data_client, youtube_analytics_client
                )
                
                # Verify new data was used instead of cached data
                assert results[video_id] == mock_results[video_id]
                assert video_data_dict[video_id] == mock_video_data[video_id]
                assert video_analytics_dict[video_id] == mock_analytics[video_id]
                assert video_decision_details[video_id] == mock_details[video_id]

def test_vet_videos_no_cache_usage():
    """Test that vet_videos processes videos normally when no cache hit or publishDateCheck passed."""
    # Setup
    video_id = "test_video_1"
    briefs = [{"id": "test_brief"}]
    youtube_data_client = MagicMock()
    youtube_analytics_client = MagicMock()
    
    # Mock cached data with passed publishDateCheck
    cached_data = {
        "results": [False],
        "video_data": {"title": "Cached Video"},
        "video_analytics": {"views": 100},
        "decision_details": {"publishDateCheck": True}
    }
    
    # Mock the cache to return our test data
    with patch('bitcast.validator.socials.youtube.youtube_utils.youtube_cache.get_video_cache', return_value=cached_data):
        # Mock is_video_already_scored to return False
        with patch('bitcast.validator.socials.youtube.youtube_utils.is_video_already_scored', return_value=False):
            # Mock process_video_vetting to return different data
            mock_results = {video_id: [True]}
            mock_video_data = {video_id: {"title": "New Video"}}
            mock_analytics = {video_id: {"views": 200}}
            mock_details = {video_id: {"publishDateCheck": True}}
            
            with patch('bitcast.validator.socials.youtube.youtube_evaluation.process_video_vetting') as mock_process:
                # Mock the process_video_vetting function to update the results dictionary
                def mock_process_impl(video_id, briefs, youtube_data_client, youtube_analytics_client, results, video_data_dict, video_analytics_dict, video_decision_details):
                    results[video_id] = mock_results[video_id]
                    video_data_dict[video_id] = mock_video_data[video_id]
                    video_analytics_dict[video_id] = mock_analytics[video_id]
                    video_decision_details[video_id] = mock_details[video_id]
                
                mock_process.side_effect = mock_process_impl
                
                # Run vet_videos
                results, video_data_dict, video_analytics_dict, video_decision_details = vet_videos(
                    [video_id], briefs, youtube_data_client, youtube_analytics_client
                )
                
                # Verify new data was used instead of cached data
                assert results[video_id] == mock_results[video_id]
                assert video_data_dict[video_id] == mock_video_data[video_id]
                assert video_analytics_dict[video_id] == mock_analytics[video_id]
                assert video_decision_details[video_id] == mock_details[video_id]

def test_vet_videos_cache_storage():
    """Test that vet_videos stores results in cache."""
    # Setup
    video_id = "test_video_1"
    briefs = [{"id": "test_brief"}]
    youtube_data_client = MagicMock()
    youtube_analytics_client = MagicMock()
    
    # Mock process_video_vetting to return test data
    test_results = {video_id: [True]}
    test_video_data = {video_id: {"title": "Test Video"}}
    test_analytics = {video_id: {"views": 100}}
    test_details = {video_id: {"publishDateCheck": True}}
    
    with patch('bitcast.validator.socials.youtube.youtube_utils.is_video_already_scored', return_value=False):
        with patch('bitcast.validator.socials.youtube.youtube_evaluation.process_video_vetting') as mock_process:
            # Mock the process_video_vetting function to update the results dictionary
            def mock_process_impl(video_id, briefs, youtube_data_client, youtube_analytics_client, results, video_data_dict, video_analytics_dict, video_decision_details):
                results[video_id] = test_results[video_id]
                video_data_dict[video_id] = test_video_data[video_id]
                video_analytics_dict[video_id] = test_analytics[video_id]
                video_decision_details[video_id] = test_details[video_id]
            
            mock_process.side_effect = mock_process_impl
            
            # Mock the cache set method to verify it's called correctly
            with patch('bitcast.validator.socials.youtube.youtube_utils.youtube_cache.set_video_cache') as mock_set_cache:
                # Run vet_videos
                vet_videos([video_id], briefs, youtube_data_client, youtube_analytics_client)
                
                # Verify cache was called with correct data
                mock_set_cache.assert_called_once()
                cache_args = mock_set_cache.call_args[0]
                assert cache_args[0] == video_id
                assert cache_args[1]["results"] == test_results[video_id]
                assert cache_args[1]["video_data"] == test_video_data[video_id]
                assert cache_args[1]["video_analytics"] == test_analytics[video_id]
                assert cache_args[1]["decision_details"] == test_details[video_id] 