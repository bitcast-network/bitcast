"""
This test file implements an end-to-end test scenario for the YouTube content validation system.
The test simulates a scenario where:

Two briefs are provided, each with a weight of 100:
- Brief 1: "Test Brief 1"
- Brief 2: "Test Brief 2"

Technical Scoring Details:
- The final scores are calculated based on watch time from two videos:
  * Each video has 500 minutes watched on day 1 and 500 minutes on day 2
  * Each video contributes 1000 minutes to the total score
  * Since both videos match both briefs, their scores are added to each brief:
    - Brief 1 score: 1000 + 1000 = 2000
    - Brief 2 score: 1000 + 1000 = 2000
- The score is based purely on total minutes watched across all matching videos
"""

import pytest
import logging
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Patch environment variables before importing modules
with patch.dict('os.environ', {'DISABLE_LLM_CACHING': 'true'}):
    from bitcast.validator.socials.youtube.evaluation import (
        vet_channel,
        vet_videos,
        calculate_video_score
    )
    from bitcast.validator.socials.youtube.api.channel import (
        get_channel_data,
        get_channel_analytics
    )
    from bitcast.validator.socials.youtube.api.video import (
        get_video_analytics,
        get_all_uploads
    )
    from bitcast.validator.socials.youtube.utils.state import reset_scored_videos
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
                            "viewCount": "50000",
                            "videoCount": "25"
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
            def list(self, playlistId=None, part=None, maxResults=None, pageToken=None, fields=None, **kwargs):
                return MockResponse({
                    "items": [
                        {
                            "contentDetails": {
                                "videoId": f"test_video_{i+1}"
                            },
                            "snippet": {
                                "publishedAt": (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%dT%H:%M:%SZ')
                            }
                        } for i in range(5)
                    ],
                    "nextPageToken": None
                })
                
            def list_next(self, previous_request, previous_response):
                """Handle pagination - return None to indicate no more pages"""
                return None
        return PlaylistItems()

    def _create_videos(self):
        class Videos:
            def list(self, part=None, id=None, **kwargs):
                items = []
                if isinstance(id, str):
                    # Handle comma-separated IDs for batch requests
                    video_ids = id.split(',') if ',' in id else [id]
                elif isinstance(id, list):
                    video_ids = id
                else:
                    video_ids = []

                for vid_id in video_ids:
                    items.append({
                        "id": vid_id.strip(),  # Strip whitespace from comma-separated IDs
                        "snippet": {
                            "title": f"Mock Video {vid_id.strip()}",
                            "description": f"Mock Description for {vid_id.strip()}",
                            "publishedAt": (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
                        },
                        "statistics": {
                            "viewCount": "1000",
                            "likeCount": "100",
                            "commentCount": "50"
                        },
                        "contentDetails": {
                            "duration": "PT10M",
                            "caption": "false"
                        },
                        "status": {
                            "privacyStatus": "public"
                        },
                        "transcript": f"This is a test transcript for {vid_id.strip()}"
                    })

                return MockResponse({"items": items})
        return Videos()

class MockYouTubeAnalyticsClient:
    def __init__(self):
        logger.debug("Initializing MockYouTubeAnalyticsClient")
        self._reports = self._create_reports()

    def reports(self):
        return self._reports

    def _create_reports(self):
        class Reports:
            def query(self, ids=None, startDate=None, endDate=None, dimensions=None, metrics=None, filters=None, **kwargs):
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
                    # Generate dates within the scoring window for better test results
                    today = datetime.now()
                    # Use dates that will be within scoring window (today-4 and today-5)
                    scoring_day1 = today - timedelta(days=YT_REWARD_DELAY + 1)  # today-4
                    scoring_day2 = today - timedelta(days=YT_REWARD_DELAY + 2)  # today-5
                    
                    for day in [scoring_day2, scoring_day1]:  # Add in chronological order
                        day_data = [
                            day.strftime('%Y-%m-%d'),
                            500,  # estimatedMinutesWatched
                            250,  # views
                            10,   # subscribersGained
                            2     # subscribersLost
                        ]
                        days.append(day_data)
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
                    # Return analytics in the new core metrics format: [averageViewPercentage, estimatedMinutesWatched, cpm]
                    return MockResponse({"rows": [[YT_MIN_CHANNEL_RETENTION + 5, YT_MIN_MINS_WATCHED + 10, 2.5]]})
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
    from bitcast.validator.socials.youtube.utils.state import reset_scored_videos as reset_func
    reset_func()
    yield

@pytest.mark.asyncio
@patch('bitcast.validator.socials.youtube.api.clients.build')
@patch('bitcast.validator.utils.blacklist.get_blacklist')
@patch('bitcast.validator.utils.blacklist.get_blacklist_sources')
@patch('bitcast.validator.socials.youtube.api.channel.get_channel_data')
@patch('bitcast.validator.socials.youtube.api.channel.get_channel_analytics')
@patch("bitcast.validator.socials.youtube.api.video.get_all_uploads")
@patch("bitcast.validator.socials.youtube.api.video.get_video_data_batch")
@patch("bitcast.validator.socials.youtube.api.video.get_video_analytics")
@patch("bitcast.validator.socials.youtube.api.transcript.get_video_transcript")
@patch('bitcast.validator.clients.OpenaiClient._make_openai_request')
@patch('bitcast.validator.utils.config.DISABLE_LLM_CACHING', True)
async def test_reward_function(mock_make_openai_request, mock_get_transcript,
                        mock_get_video_analytics, mock_get_video_data_batch, mock_get_all_uploads, 
                        mock_get_channel_analytics, mock_get_channel_data, mock_get_blacklist_sources,
                        mock_get_blacklist, mock_build):
    """Test the reward function with two videos and two briefs."""
    # Mock blacklist sources to return ADVERTISING
    mock_get_blacklist_sources.return_value = ["ADVERTISING"]
    
    # Mock blacklist to return empty list (no blacklisted channels)
    mock_get_blacklist.return_value = []
    
    # Setup test data
    uid = 1
    briefs = [
        {
            "id": "brief1",
            "title": "Test Brief 1",
            "brief": "Test Description 1",
            
            "weight": 100,
            "start_date": "2023-01-01"
        },
        {
            "id": "brief2",
            "title": "Test Brief 2",
            "brief": "Test Description 2",
            "requirements": ["requirement3", "requirement4"],
            "weight": 150,
            "start_date": "2023-01-01"
        }
    ]
    
    mock_response = MagicMock()
    mock_response.YT_access_tokens = ["mock_token"]
    
    youtube_data_client, youtube_analytics_client = get_mock_youtube_clients()
    
    mock_build.side_effect = [youtube_data_client, youtube_analytics_client]
    
    mock_get_channel_data.return_value = {
        "bitcastChannelId": "test_channel",
        "subCount": "1000",
        "channel_start": "2023-01-01T00:00:00Z"
    }
    mock_get_channel_analytics.return_value = {
        "averageViewPercentage": 50,
        "estimatedMinutesWatched": 10000,
        "cpm": 2.5  # Add YPP membership indicator
    }
    
    mock_get_all_uploads.return_value = ["test_video_1", "test_video_2"]
    
    # Use single-video helper to build batch results
    def mock_get_video_data_side_effect(client, video_id, discrete_mode=False):
        # existing mapping of video_id to video_data
        video_data = {
            "test_video_1": {
                "bitcastVideoId": "test_video_1",
                "title": "Test Video 1",
                "description": "Test Description 1",
                "publishedAt": "2023-01-15T00:00:00Z",
                "duration": "PT10M",
                "caption": False,
                "privacyStatus": "public",
                "contentDetails": {
                    "duration": "PT10M",
                    "caption": "false"
                },
                "statistics": {
                    "viewCount": "1000",
                    "likeCount": "100",
                    "commentCount": "50"
                },
                "transcript": "This is a test transcript for test_video_1"
            },
            "test_video_2": {
                "bitcastVideoId": "test_video_2",
                "title": "Test Video 2",
                "description": "Test Description 2",
                "publishedAt": "2023-01-16T00:00:00Z",
                "duration": "PT15M",
                "caption": False,
                "privacyStatus": "public",
                "contentDetails": {
                    "duration": "PT15M",
                    "caption": "false"
                },
                "statistics": {
                    "viewCount": "1000",
                    "likeCount": "100",
                    "commentCount": "50"
                },
                "transcript": "This is a test transcript for test_video_2"
            }
        }
        return video_data[video_id]
    
    def mock_get_video_data_batch_side_effect(client, video_ids, discrete_mode=False):
        return {vid: mock_get_video_data_side_effect(client, vid) for vid in video_ids}
    
    mock_get_video_data_batch.side_effect = mock_get_video_data_batch_side_effect
    
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
            else:
                # Return general analytics
                if video_id == "test_video_1":
                    return {
                        "views": 500,
                        "comments": 40,
                        "likes": 200, 
                        "shares": 20,
                        "averageViewDuration": 180,
                        "averageViewPercentage": 50,
                        "estimatedMinutesWatched": 1000,
                        "trafficSourceMinutes": {"YT_CHANNEL": 500, "EXT_URL": 500}
                    }
                else:  # test_video_2
                    return {
                        "views": 600,
                        "comments": 50,
                        "likes": 250, 
                        "shares": 30,
                        "averageViewDuration": 200,
                        "averageViewPercentage": 55,
                        "estimatedMinutesWatched": 1200,
                        "trafficSourceMinutes": {"YT_CHANNEL": 700, "EXT_URL": 500}
                    }
        
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
            video_metrics = {
                "test_video_1": {
                    "averageViewPercentage": 50,
                    "estimatedMinutesWatched": 1000
                },
                "test_video_2": {
                    "averageViewPercentage": 55,
                    "estimatedMinutesWatched": 1200
                }
            }
            return video_metrics[video_id]
    
    mock_get_video_analytics.side_effect = mock_get_video_analytics_side_effect
    mock_get_transcript.return_value = "This is a test transcript"
    
    class MockResponse:
        def __init__(self, injection_detected=None, meets_brief=None):
            self.choices = [MagicMock(message=MagicMock(parsed=MagicMock(
                injection_detected=injection_detected,
                meets_brief=meets_brief
            )))]
    
    # Mock responses for both videos and both briefs
    mock_make_openai_request.side_effect = [
        # Video 1 injection check
        MockResponse(injection_detected=False),
        # Video 1 brief 1 check
        MockResponse(meets_brief=True),
        # Video 1 brief 2 check
        MockResponse(meets_brief=True),
        # Video 2 injection check
        MockResponse(injection_detected=False),
        # Video 2 brief 1 check
        MockResponse(meets_brief=True),
        # Video 2 brief 2 check
        MockResponse(meets_brief=True),
    ]
    
    result = reward(uid, briefs, mock_response)
    
    assert isinstance(result, dict)
    assert "scores" in result
    assert isinstance(result["scores"], dict)
    assert "brief1" in result["scores"]
    assert "brief2" in result["scores"]
    assert isinstance(result["scores"]["brief1"], (int, float))
    assert isinstance(result["scores"]["brief2"], (int, float))
    # Both briefs should have scores since both videos meet both briefs
    assert result["scores"]["brief1"] == 2000
    assert result["scores"]["brief2"] == 2000