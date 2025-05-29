"""
This test file implements an end-to-end test scenario for the YouTube content validation system.
The test simulates a scenario where:

A single brief is provided with a weight of 100

Technical Scoring Details:
- The final score of 1000 is calculated based on watch time from a single video:
  * The video has 500 minutes watched on day 1 and 500 minutes on day 2
  * The video contributes 1000 minutes to the total score
  * Since only one video matches the brief, the final score is 1000
- The score is based purely on total minutes watched across all matching videos
"""

import pytest
import logging
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Patch environment variables before importing modules
with patch.dict('os.environ', {'DISABLE_LLM_CACHING': 'true'}):
    from bitcast.validator.socials.youtube.youtube_evaluation import (
        vet_channel,
        vet_videos,
        calculate_video_score
    )
    from bitcast.validator.socials.youtube.youtube_utils import (
        get_channel_data,
        get_channel_analytics,
        get_video_data,
        get_video_analytics,
        get_all_uploads,
        reset_scored_videos
    )
    from bitcast.validator.reward import reward
    from google.oauth2.credentials import Credentials
    from bitcast.validator.utils.config import (
        YT_MIN_SUBS,
        YT_MIN_CHANNEL_AGE,
        YT_MIN_CHANNEL_RETENTION,
        YT_MIN_MINS_WATCHED,
        YT_REWARD_DELAY,
        YT_ROLLING_WINDOW
    )

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True
)
logger = logging.getLogger(__name__)

# Mock YouTube API Classes
class MockResponse:
    def __init__(self, data):
        self._data = data
        logger.debug(f"Created MockResponse with data: {data}")

    def execute(self):
        logger.debug("Executing MockResponse")
        return self._data

class MockYouTubeDataClient:
    def __init__(self):
        logger.debug("Initializing MockYouTubeDataClient")
        self._channels = self._create_channels()
        self._playlist_items = self._create_playlist_items()
        self._videos = self._create_videos()

    def channels(self):
        return self._channels

    def playlistItems(self):
        return self._playlist_items

    def videos(self):
        return self._videos

    def _create_channels(self):
        class Channels:
            def list(self, part=None, mine=None):
                channel_id = "mock_channel_id"
                channel_start = (datetime.now() - timedelta(days=YT_MIN_CHANNEL_AGE + 10)).strftime('%Y-%m-%dT%H:%M:%SZ')
                return MockResponse({
                    "items": [{
                        "id": channel_id,
                        "snippet": {
                            "title": "Mock Channel",
                            "publishedAt": channel_start
                        },
                        "statistics": {
                            "subscriberCount": str(YT_MIN_SUBS + 1000),
                        },
                        "contentDetails": {
                            "relatedPlaylists": {
                                "uploads": "mock_uploads_playlist"
                            }
                        }
                    }]
                })
        return Channels()

    def _create_playlist_items(self):
        class PlaylistItems:
            def list(self, playlistId=None, part=None, maxResults=None, pageToken=None):
                return MockResponse({
                    "items": [
                        {
                            "snippet": {
                                "publishedAt": (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                                "resourceId": {
                                    "videoId": f"mock_video_{i}"
                                }
                            }
                        } for i in range(5)
                    ],
                    "nextPageToken": None
                })
        return PlaylistItems()

    def _create_videos(self):
        class Videos:
            def list(self, part=None, id=None):
                return MockResponse({
                    "items": [{
                        "snippet": {
                            "title": "Mock Video",
                            "description": "Mock Description",
                            "publishedAt": (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
                        },
                        "contentDetails": {
                            "duration": "PT10M",
                            "caption": "false"
                        },
                        "status": {
                            "privacyStatus": "public"
                        }
                    }]
                })
        return Videos()

class MockYouTubeAnalyticsClient:
    def __init__(self):
        logger.debug("Initializing MockYouTubeAnalyticsClient")
        self._reports = self._create_reports()

    def reports(self):
        return self._reports

    def _create_reports(self):
        class Reports:
            def query(self, ids=None, startDate=None, endDate=None, dimensions=None, metrics=None, filters=None):
                # Static base metrics
                base_metrics = [
                    10000,                          # views
                    100,                            # comments
                    500,                            # likes
                    10,                             # dislikes
                    50,                             # shares
                    180,                      # averageViewDuration
                    YT_MIN_CHANNEL_RETENTION + 5,   # averageViewPercentage
                    100,                            # subscribersGained
                    10,                             # subscribersLost
                    YT_MIN_MINS_WATCHED + 10      # estimatedMinutesWatched
                ]

                if dimensions == "country":
                    return MockResponse({
                        "rows": [
                            ["US", 3000],
                            ["UK", 1500],
                            ["CA", 800]
                        ]
                    })
                elif dimensions == "day":
                    days = []
                    start = datetime.strptime(startDate, '%Y-%m-%d')
                    end = datetime.strptime(endDate, '%Y-%m-%d')
                    current = start
                    while current <= end:
                        day_data = [
                            current.strftime('%Y-%m-%d'),
                            500,  # estimatedMinutesWatched
                            250,  # views
                            10,   # subscribersGained
                            2     # subscribersLost
                        ]
                        days.append(day_data)
                        current += timedelta(days=1)
                    return MockResponse({"rows": days})
                elif dimensions == "insightTrafficSourceType":
                    return MockResponse({
                        "rows": [
                            ["EXT_URL", 3000],
                            ["YT_CHANNEL", 1500],
                            ["YT_OTHER_PAGE", 800]
                        ]
                    })
                else:
                    return MockResponse({"rows": [base_metrics]})
        return Reports()

def get_mock_youtube_clients():
    """Returns mock YouTube data and analytics clients for testing."""
    return MockYouTubeDataClient(), MockYouTubeAnalyticsClient()

@pytest.fixture(autouse=True)
def mock_bt_logging():
    with patch('bittensor.logging') as mock_logging:
        mock_logging.info = logger.info
        mock_logging.warning = logger.warning
        mock_logging.error = logger.error
        mock_logging.debug = logger.debug
        yield mock_logging

@pytest.fixture
def mock_clients():
    return get_mock_youtube_clients()

@pytest.fixture
def mock_credentials():
    return Credentials(
        token="mock_token",
        refresh_token="mock_refresh_token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="mock_client_id",
        client_secret="mock_client_secret"
    )

@pytest.fixture(autouse=True)
def reset_scored_videos():
    from bitcast.validator.socials.youtube.youtube_utils import reset_scored_videos as reset_func
    reset_func()
    yield

@pytest.mark.asyncio
@patch('bitcast.validator.socials.youtube.youtube_scoring.build')
@patch('bitcast.validator.utils.blacklist.get_blacklist')
@patch('bitcast.validator.utils.blacklist.get_blacklist_sources')
@patch('bitcast.validator.socials.youtube.youtube_utils.get_channel_data')
@patch('bitcast.validator.socials.youtube.youtube_utils.get_channel_analytics')
@patch('bitcast.validator.socials.youtube.youtube_utils.get_all_uploads')
@patch('bitcast.validator.socials.youtube.youtube_utils.get_video_data')
@patch('bitcast.validator.socials.youtube.youtube_utils.get_video_analytics')
@patch('bitcast.validator.socials.youtube.youtube_utils.get_video_transcript')
@patch('bitcast.validator.clients.OpenaiClient._make_openai_request')
@patch('bitcast.validator.utils.config.DISABLE_LLM_CACHING', True)
async def test_reward_function(mock_make_openai_request, mock_get_transcript,
                        mock_get_video_analytics, mock_get_video_data, mock_get_all_uploads, 
                        mock_get_channel_analytics, mock_get_channel_data, mock_get_blacklist_sources,
                        mock_get_blacklist, mock_build):
    """Test the reward function with one video and one brief."""
    # Mock blacklist sources to return ADVERTISING
    mock_get_blacklist_sources.return_value = ["ADVERTISING"]
    
    # Mock blacklist to return empty list (no blacklisted channels)
    mock_get_blacklist.return_value = []
    
    # Setup test data
    uid = 1
    briefs = [
        {
            "id": "brief1",
            "title": "Test Brief",
            "brief": "Test Description",
            
            "weight": 100,
            "start_date": "2023-01-01"
        }
    ]
    
    mock_response = MagicMock()
    mock_response.YT_access_token = "mock_token"
    
    youtube_data_client, youtube_analytics_client = get_mock_youtube_clients()
    
    mock_build.side_effect = [youtube_data_client, youtube_analytics_client]
    
    mock_get_channel_data.return_value = {
        "bitcastChannelId": "test_channel",
        "subCount": "1000",
        "channel_start": "2023-01-01T00:00:00Z"
    }
    mock_get_channel_analytics.return_value = {
        "averageViewPercentage": 50,
        "estimatedMinutesWatched": 10000
    }
    
    mock_get_all_uploads.return_value = ["test_video_1", "test_video_2"]
    
    def mock_get_video_data_side_effect(client, video_id, *args, **kwargs):
        return {
            "bitcastVideoId": video_id,
            "title": f"Test Video {video_id}",
            "description": f"Test Description for {video_id}",
            "publishedAt": "2023-01-15T00:00:00Z",
            "duration": "PT10M",
            "caption": False,
            "privacyStatus": "public"
        }
    
    mock_get_video_data.side_effect = mock_get_video_data_side_effect
    
    # Note: The hardcoded dates (2023-01-15, 2023-01-16) in the mock data are not significant.
    def mock_get_video_analytics_side_effect(client, video_id, start_date=None, end_date=None, metric_dims=None, dimensions=None):
        # Use dates relative to today to work with YT_REWARD_DELAY and YT_ROLLING_WINDOW from config
        today = datetime.now()
        day1 = (today - timedelta(days=YT_REWARD_DELAY + 1)).strftime('%Y-%m-%d')
        day2 = (today - timedelta(days=YT_REWARD_DELAY + 2)).strftime('%Y-%m-%d')
        
        # Handle the new metric_dims parameter
        if metric_dims:
            # Check if this is a daily metrics request
            has_day_dimension = any('day' in dims for metric_config in metric_dims.values() for dims in [metric_config[1]] if dims)
            
            # If we have day dimension metrics, include them in the result
            if has_day_dimension:
                # Create day_metrics structure
                day_metrics = {
                    day1: {
                        "day": day1,
                        "estimatedMinutesWatched": 500,
                        "views": 250,
                        "averageViewPercentage": 50
                    },
                    day2: {
                        "day": day2,
                        "estimatedMinutesWatched": 500,
                        "views": 250,
                        "averageViewPercentage": 50
                    }
                }
                
                result = {
                    # Include averageViewPercentage at top level for vetting
                    "averageViewPercentage": 50,
                    "estimatedMinutesWatched": 1000,
                    "trafficSourceMinutes": {"YT_CHANNEL": 500, "EXT_URL": 500}
                }
                
                # Add basic day metrics
                for key, metric_config in metric_dims.items():
                    metric, dims = metric_config[0], metric_config[1]  # Extract metric and dims from 5-tuple
                    if dims == "day":
                        result[key] = {
                            day1: 500 if metric == "estimatedMinutesWatched" else 250,
                            day2: 500 if metric == "estimatedMinutesWatched" else 250
                        }
                
                # Add the day_metrics structure
                result["day_metrics"] = day_metrics
                return result
            
            # Check if this video meets briefs for non-day dimension case
            result = {
                "averageViewPercentage": 50,
                "estimatedMinutesWatched": 1000,
                "trafficSourceMinutes": {"YT_CHANNEL": 500, "EXT_URL": 500}
            }
            
            # Add non-day metrics
            for key, metric_config in metric_dims.items():
                metric, dims = metric_config[0], metric_config[1]  # Extract metric and dims from 5-tuple
                if dims != "day":
                    # Special handling for EXT_URL detail metrics
                    if key == "insightTrafficSourceDetail_EXT_URL":
                        result[key] = {"twitter.com": 50, "discord.com": 30}  # Mock EXT_URL sources
                    elif "trafficSourceMinutes" in key:
                        result[key] = {"YT_CHANNEL": 300, "EXT_URL": 200}  # Mock traffic source data
                    else:
                        result[key] = 100  # Default value for other non-day metrics
            
            return result
        
        # Legacy format support for backward compatibility
        if dimensions == 'day':
            return [
                {
                    "day": day1,
                    "estimatedMinutesWatched": 500
                },
                {
                    "day": day2,
                    "estimatedMinutesWatched": 500
                }
            ]
        else:
            return {
                "averageViewPercentage": 50,
                "estimatedMinutesWatched": 1000
            }
    
    mock_get_video_analytics.side_effect = mock_get_video_analytics_side_effect
    mock_get_transcript.return_value = "This is a test transcript"
    
    class MockResponse:
        def __init__(self, injection_detected=None, meets_brief=None):
            self.choices = [MagicMock(message=MagicMock(parsed=MagicMock(
                injection_detected=injection_detected,
                meets_brief=meets_brief
            )))]
    
    # Mock responses for both videos
    mock_make_openai_request.side_effect = [
        MockResponse(injection_detected=False),  # For video 1
        MockResponse(meets_brief=True),         # For video 1
        MockResponse(injection_detected=False),  # For video 2
        MockResponse(meets_brief=True),         # For video 2
    ]
    
    result = reward(uid, briefs, mock_response)
    
    assert isinstance(result, dict)
    assert "scores" in result
    assert isinstance(result["scores"], dict)
    assert "brief1" in result["scores"]
    assert isinstance(result["scores"]["brief1"], (int, float))
    assert 0 <= result["scores"]["brief1"] == 2000  # Score should be doubled since both videos match