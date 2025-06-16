"""
This test file implements an end-to-end test scenario for the get_rewards function with a single miner.
The test simulates a scenario where:

Two briefs are provided:
- Brief 1: "Test Brief 1" with weight 100
- Brief 2: "Test Brief 2" with weight 100

Technical Scoring Details:
- The final scores are calculated based on watch time from four videos:
  * Video 1: 600 minutes watched, matches Brief 1
  * Video 2: 250 minutes watched, matches both Briefs
  * Video 3: 100 minutes watched, matches neither Brief
  * Video 4: 300 minutes watched, matches Brief 2

- UID 1 has videos with organic traffic (100% scorable_proportion)
- UID 2 has videos with 30% advertising traffic (70% scorable_proportion)

- Final scores:
  * Brief 1: 
    - UID 1: 1275 minutes (900 + 375, 100% scorable)
    - UID 2: 595 minutes (850 minutes × 70% scorable_proportion)
  * Brief 2: 
    - UID 1: 825 minutes (375 + 450, 100% scorable)
    - UID 2: 385 minutes (550 minutes × 70% scorable_proportion)
"""

# Set environment variable before any imports to ensure it's picked up
import os
os.environ['DISABLE_CONCURRENCY'] = 'True'

import unittest
import pytest
import logging
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import numpy as np
import itertools

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
        get_video_analytics,
        get_all_uploads,
        reset_scored_videos
    )
    from bitcast.validator.reward import reward, get_rewards
    from google.oauth2.credentials import Credentials
    from bitcast.validator.utils.config import (
        YT_MIN_SUBS,
        YT_MIN_CHANNEL_AGE,
        YT_MIN_CHANNEL_RETENTION,
        YT_MIN_MINS_WATCHED,
        YT_REWARD_DELAY,
        YT_ROLLING_WINDOW
    )

# Force reload config module to pick up DISABLE_CONCURRENCY
import importlib
import bitcast.validator.utils.config
importlib.reload(bitcast.validator.utils.config)

# Also reload youtube_evaluation module to pick up the updated config
import bitcast.validator.socials.youtube.youtube_evaluation
importlib.reload(bitcast.validator.socials.youtube.youtube_evaluation)

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
                                "publishedAt": (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                                "resourceId": {
                                    "videoId": "test_video_1"
                                }
                            }
                        }
                    ],
                    "nextPageToken": None
                })
        return PlaylistItems()

    def _create_videos(self):
        class Videos:
            def list(self, part=None, id=None):
                return MockResponse({
                    "items": [{
                        "id": "mock_video_1",
                        "snippet": {
                            "title": "Mock Video",
                            "description": "Mock Description",
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
                    180,                            # averageViewDuration
                    YT_MIN_CHANNEL_RETENTION + 5,   # averageViewPercentage
                    100,                            # subscribersGained
                    10,                             # subscribersLost
                    YT_MIN_MINS_WATCHED + 10        # estimatedMinutesWatched
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
                            300,  # estimatedMinutesWatched
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
@patch('bitcast.validator.socials.youtube.youtube_utils.get_video_data_batch')
@patch('bitcast.validator.socials.youtube.youtube_utils.get_video_analytics')
@patch('bitcast.validator.socials.youtube.youtube_utils.get_video_transcript')
@patch('bitcast.validator.clients.OpenaiClient._make_openai_request')
@patch('bitcast.validator.utils.config.DISABLE_LLM_CACHING', True)
async def test_get_rewards_single_miner(mock_make_openai_request, mock_get_transcript,
                        mock_get_video_analytics, mock_get_video_data_batch, mock_get_all_uploads, 
                        mock_get_channel_analytics, mock_get_channel_data, mock_get_blacklist_sources,
                        mock_get_blacklist, mock_build):
    """Test the get_rewards function with a single miner."""
    # Mock blacklist sources to return ADVERTISING
    mock_get_blacklist_sources.return_value = ["ADVERTISING"]
    
    # Mock blacklist to return empty list (no blacklisted channels)
    mock_get_blacklist.return_value = []
    
    # Setup test data
    uids = [0, 1, 2]  # Include UIDs 0, 1, and 2
    briefs = [
        {
            "id": "brief1",
            "title": "Test Brief 1",
            "brief": "Test Description 1",
            "weight": 100,
            "max_burn": 0.0,  # This means UID 0 gets 0 reward
            "burn_decay": 0.01,
            "start_date": "2023-01-01"
        },
        {
            "id": "brief2",
            "title": "Test Brief 2",
            "brief": "Test Description 2",
            "weight": 100,
            "max_burn": 0.0,
            "burn_decay": 0.01,
            "start_date": "2023-01-01"
        }
    ]
    
    # Create responses for all UIDs
    mock_response_0 = MagicMock()
    mock_response_0.YT_access_token = None  # UID 0 has no token
    mock_response_0.YT_channel_id = None
    
    mock_response_1 = MagicMock()
    mock_response_1.YT_access_token = "mock_token_1"
    mock_response_1.YT_channel_id = "test_channel"  # Add channel ID for UID 1
    
    mock_response_2 = MagicMock()
    mock_response_2.YT_access_token = "mock_token_2"  # UID 2 has different token from UID 1
    mock_response_2.YT_channel_id = "test_channel_uid2"  # Add channel ID for UID 2
    
    responses = [mock_response_0, mock_response_1, mock_response_2]
    
    youtube_data_client, youtube_analytics_client = get_mock_youtube_clients()
    
    mock_build.side_effect = lambda service, version, credentials=None: (
        youtube_data_client if service == "youtube" else youtube_analytics_client
    )
    
    # Track which UID we're currently evaluating
    current_uid = [0]  # Use a list so we can modify it inside functions
    
    def set_current_uid(uid):
        current_uid[0] = uid
        logger.info(f"Setting current UID to {uid}")
    
    # Maintain a reference to the original reward function
    original_reward = reward
    
    # Create a wrapper around the reward function to track which UID is being evaluated
    def reward_wrapper(uid, briefs, response):
        set_current_uid(uid)
        if uid > 0:  # Don't reset for UID 0 since it's first
            from bitcast.validator.socials.youtube.youtube_utils import reset_scored_videos as reset_func
            reset_func()
        return original_reward(uid, briefs, response)
    
    # Helper to get channel data for the current UID
    def mock_get_channel_data_side_effect(client, discrete_mode=False):
        uid = current_uid[0]
        logger.info(f"get_channel_data called for UID {uid}")
        
        channel_id = responses[uid].YT_channel_id if uid > 0 else None
        
        if channel_id == "test_channel_uid2":
            data = {
                "bitcastChannelId": "test_channel_uid2",
                "subCount": "1000",
                "channel_start": "2023-01-01T00:00:00Z"
            }
        else:
            data = {
                "bitcastChannelId": "test_channel",
                "subCount": "1000",
                "channel_start": "2023-01-01T00:00:00Z"
            }
        logger.info(f"Returning channel data: {data}")
        return data
    
    mock_get_channel_data.side_effect = mock_get_channel_data_side_effect
    
    def mock_get_channel_analytics_side_effect(client, start_date=None, end_date=None, dimensions=None):
        uid = current_uid[0]
        logger.info(f"get_channel_analytics called for UID {uid}")
        
        return {
            "averageViewPercentage": 50,
            "estimatedMinutesWatched": 10000,
            "subCount": "1000"
        }
    
    mock_get_channel_analytics.side_effect = mock_get_channel_analytics_side_effect
    
    def mock_get_all_uploads_side_effect(client, max_age_days=365):
        uid = current_uid[0]
        logger.info(f"get_all_uploads called for UID {uid}")
        
        channel_id = responses[uid].YT_channel_id if uid > 0 else None
        
        if channel_id == "test_channel_uid2":
            videos = ["test_video_1_uid2", "test_video_2_uid2", "test_video_3_uid2", "test_video_4_uid2"]
        else:
            videos = ["test_video_1_uid1", "test_video_2_uid1", "test_video_3_uid1", "test_video_4_uid1"]
        
        logger.info(f"Returning videos for UID {uid}: {videos}")
        return videos
    
    mock_get_all_uploads.side_effect = mock_get_all_uploads_side_effect
    
    def mock_get_video_data_side_effect(client, video_id, discrete_mode=False):
        logger.info(f"get_video_data called with video_id: {video_id}")
        video_data = {
            # UID 1's videos
            "test_video_1_uid1": {
                "bitcastVideoId": "test_video_1_uid1",
                "title": "Test Video 1",
                "description": "Test Description 1",
                "publishedAt": "2023-01-15T00:00:00Z",
                "duration": "PT10M",
                "caption": False,
                "privacyStatus": "public"
            },
            "test_video_2_uid1": {
                "bitcastVideoId": "test_video_2_uid1",
                "title": "Test Video 2",
                "description": "Test Description 2",
                "publishedAt": "2023-01-16T00:00:00Z",
                "duration": "PT15M",
                "caption": False,
                "privacyStatus": "public"
            },
            "test_video_3_uid1": {
                "bitcastVideoId": "test_video_3_uid1",
                "title": "Test Video 3",
                "description": "Test Description 3",
                "publishedAt": "2023-01-17T00:00:00Z",
                "duration": "PT10M",
                "caption": False,
                "privacyStatus": "public"
            },
            "test_video_4_uid1": {
                "bitcastVideoId": "test_video_4_uid1",
                "title": "Test Video 4",
                "description": "Test Description 4",
                "publishedAt": "2023-01-18T00:00:00Z",
                "duration": "PT10M",
                "caption": False,
                "privacyStatus": "public"
            },
            # UID 2's videos
            "test_video_1_uid2": {
                "bitcastVideoId": "test_video_1_uid2",
                "title": "Test Video 1",
                "description": "Test Description 1",
                "publishedAt": "2023-01-15T00:00:00Z",
                "duration": "PT10M",
                "caption": False,
                "privacyStatus": "public"
            },
            "test_video_2_uid2": {
                "bitcastVideoId": "test_video_2_uid2",
                "title": "Test Video 2",
                "description": "Test Description 2",
                "publishedAt": "2023-01-16T00:00:00Z",
                "duration": "PT15M",
                "caption": False,
                "privacyStatus": "public"
            },
            "test_video_3_uid2": {
                "bitcastVideoId": "test_video_3_uid2",
                "title": "Test Video 3",
                "description": "Test Description 3",
                "publishedAt": "2023-01-17T00:00:00Z",
                "duration": "PT10M",
                "caption": False,
                "privacyStatus": "public"
            },
            "test_video_4_uid2": {
                "bitcastVideoId": "test_video_4_uid2",
                "title": "Test Video 4",
                "description": "Test Description 4",
                "publishedAt": "2023-01-18T00:00:00Z",
                "duration": "PT10M",
                "caption": False,
                "privacyStatus": "public"
            }
        }
        result = video_data[video_id]
        logger.info(f"Returning video data for {video_id}: {result}")
        return result
    
    def mock_get_video_data_batch_side_effect(client, video_ids, discrete_mode=False):
        return {vid: mock_get_video_data_side_effect(client, vid) for vid in video_ids}

    mock_get_video_data_batch.side_effect = mock_get_video_data_batch_side_effect
    
    def mock_get_video_analytics_side_effect(client, video_id, start_date=None, end_date=None, dimensions=None, metric_dims=None):
        logger.info(f"get_video_analytics called with video_id: {video_id}, dimensions: {dimensions}, metric_dims: {metric_dims}")
        
        # Use dates relative to today to work with YT_REWARD_DELAY and YT_ROLLING_WINDOW from config
        today = datetime.now()
        day1 = (today - timedelta(days=YT_REWARD_DELAY + 1)).strftime('%Y-%m-%d')
        day2 = (today - timedelta(days=YT_REWARD_DELAY + 2)).strftime('%Y-%m-%d')
        
        # Determine video watch time based on video ID
        video_day_metrics = {
            # UID 1's videos (50% more watch time)
            "test_video_1_uid1": 900,  # 600 * 1.5
            "test_video_2_uid1": 375,  # 250 * 1.5
            "test_video_3_uid1": 150,  # 100 * 1.5
            "test_video_4_uid1": 450,  # 300 * 1.5
            # UID 2's videos (original watch time)
            "test_video_1_uid2": 600,
            "test_video_2_uid2": 250,
            "test_video_3_uid2": 100,
            "test_video_4_uid2": 300
        }
        total_minutes = video_day_metrics.get(video_id, 0)
        half_minutes = total_minutes / 2
        
        # Create appropriate day_metrics structure based on UID
        day_metrics = {}
        
        # For UID 2, include advertising in the day metrics (30% advertising, 70% organic)
        if "uid2" in video_id:
            day_metrics = {
                day1: {
                    "day": day1,
                    "estimatedMinutesWatched": half_minutes,
                    "trafficSourceMinutes": {
                        "YT_CHANNEL": half_minutes * 0.7,
                        "ADVERTISING": half_minutes * 0.3
                    }
                },
                day2: {
                    "day": day2,
                    "estimatedMinutesWatched": half_minutes,
                    "trafficSourceMinutes": {
                        "YT_CHANNEL": half_minutes * 0.7,
                        "ADVERTISING": half_minutes * 0.3
                    }
                }
            }
        else:
            # UID 1 has 100% organic traffic
            day_metrics = {
                day1: {
                    "day": day1,
                    "estimatedMinutesWatched": half_minutes,
                },
                day2: {
                    "day": day2,
                    "estimatedMinutesWatched": half_minutes,
                }
            }
        
        # Handle metric_dims parameter (modern approach)
        if metric_dims:
            # Create result with top-level metrics for vetting
            result = {
                "averageViewPercentage": 50,
                "estimatedMinutesWatched": total_minutes,
                "day_metrics": day_metrics
            }
            
            # Add metrics for each requested metric
            for key, metric_config in metric_dims.items():
                metric, dims = metric_config[0], metric_config[1]  # Extract metric and dims from 5-tuple
                if dims == "day":
                    if metric == "estimatedMinutesWatched":
                        result[key] = {
                            day1: half_minutes,
                            day2: half_minutes
                        }
                    else:
                        result[key] = {
                            day1: half_minutes / 2,
                            day2: half_minutes / 2
                        }
            
            # Add trafficSourceMinutes with appropriate distribution
            if "uid2" in video_id:
                # 30% advertising for UID 2
                result["trafficSourceMinutes"] = {
                    "YT_CHANNEL": total_minutes * 0.7,
                    "ADVERTISING": total_minutes * 0.3
                }
            else:
                # No advertising for UID 1
                result["trafficSourceMinutes"] = {
                    "YT_CHANNEL": total_minutes / 2,
                    "EXT_URL": total_minutes / 2
                }
            
            logger.info(f"Returning day metrics structure for {video_id}: {result}")
            return result
        
        # Legacy format support for backward compatibility (dimensions parameter)
        elif dimensions == 'day':
            # For day-based analytics, we need day-level traffic source data
            if "uid2" in video_id:
                yt_channel_minutes = half_minutes * 0.7
                advertising_minutes = half_minutes * 0.3
                
                return [
                    {
                        "day": day1,
                        "estimatedMinutesWatched": half_minutes,
                        "trafficSourceMinutes": {
                            "YT_CHANNEL": yt_channel_minutes,
                            "ADVERTISING": advertising_minutes
                        }
                    },
                    {
                        "day": day2,
                        "estimatedMinutesWatched": half_minutes,
                        "trafficSourceMinutes": {
                            "YT_CHANNEL": yt_channel_minutes,
                            "ADVERTISING": advertising_minutes
                        }
                    }
                ]
            else:
                # Original format for UID 1
                return [
                    {
                        "day": day1,
                        "estimatedMinutesWatched": half_minutes
                    },
                    {
                        "day": day2,
                        "estimatedMinutesWatched": half_minutes
                    }
                ]
        else:
            # For non-daily metrics, return the regular metrics
            if "uid2" in video_id:
                result = {
                    "averageViewPercentage": 50,
                    "estimatedMinutesWatched": total_minutes,
                    "trafficSourceMinutes": {
                        "YT_CHANNEL": total_minutes * 0.7,
                        "ADVERTISING": total_minutes * 0.3
                    }
                }
            else:
                result = {
                    "averageViewPercentage": 50,
                    "estimatedMinutesWatched": total_minutes,
                    "trafficSourceMinutes": {
                        "YT_CHANNEL": total_minutes / 2,
                        "EXT_URL": total_minutes / 2
                    }
                }
            logger.info(f"Returning overall metrics for {video_id}: {result}")
            return result
    
    mock_get_video_analytics.side_effect = mock_get_video_analytics_side_effect
    
    mock_get_transcript.return_value = "This is a test transcript"
    
    class MockResponse:
        def __init__(self, injection_detected=None, meets_brief=None):
            # Set default reasoning based on the type of response
            if injection_detected is not None:
                reasoning = "Prompt injection test reasoning"
            elif meets_brief is not None:
                reasoning = "Brief evaluation reasoning"
            else:
                reasoning = "Default reasoning"
                
            self.choices = [MagicMock(message=MagicMock(parsed=MagicMock(
                injection_detected=injection_detected,
                meets_brief=meets_brief,
                reasoning=reasoning  # Add the missing reasoning attribute
            )))]
    
    # Create a cycling mock that repeats the pattern for any number of calls
    mock_responses_pattern = [
        # UID 1's videos
        # Video 1 injection check
        MockResponse(injection_detected=False),
        # Video 1 brief 1 check
        MockResponse(meets_brief=True),
        # Video 1 brief 2 check
        MockResponse(meets_brief=False),
        # Video 2 injection check
        MockResponse(injection_detected=False),
        # Video 2 brief 1 check
        MockResponse(meets_brief=True),
        # Video 2 brief 2 check
        MockResponse(meets_brief=True),
        # Video 3 injection check
        MockResponse(injection_detected=False),
        # Video 3 brief 1 check
        MockResponse(meets_brief=False),
        # Video 3 brief 2 check
        MockResponse(meets_brief=False),
        # Video 4 injection check
        MockResponse(injection_detected=False),
        # Video 4 brief 1 check
        MockResponse(meets_brief=False),
        # Video 4 brief 2 check
        MockResponse(meets_brief=True),
        
        # UID 2's videos (same pattern)
        # Video 1 injection check
        MockResponse(injection_detected=False),
        # Video 1 brief 1 check
        MockResponse(meets_brief=True),
        # Video 1 brief 2 check
        MockResponse(meets_brief=False),
        # Video 2 injection check
        MockResponse(injection_detected=False),
        # Video 2 brief 1 check
        MockResponse(meets_brief=True),
        # Video 2 brief 2 check
        MockResponse(meets_brief=True),
        # Video 3 injection check
        MockResponse(injection_detected=False),
        # Video 3 brief 1 check
        MockResponse(meets_brief=False),
        # Video 3 brief 2 check
        MockResponse(meets_brief=False),
        # Video 4 injection check
        MockResponse(injection_detected=False),
        # Video 4 brief 1 check
        MockResponse(meets_brief=False),
        # Video 4 brief 2 check
        MockResponse(meets_brief=True),
    ]
    
    # Create a cycling iterator that repeats the pattern
    cycling_responses = itertools.cycle(mock_responses_pattern)
    
    # Set up the mock to use the cycling responses
    mock_make_openai_request.side_effect = lambda *args, **kwargs: next(cycling_responses)
    
    # Create a mock class instance for self parameter
    mock_self = MagicMock()
    
    # Create mock_query_miner function that returns responses based on UID
    async def mock_query_miner(self, uid):
        return responses[uid]
    
    # Patch get_briefs to return our test briefs
    with patch('bitcast.validator.reward.get_briefs', return_value=briefs) as mock_get_briefs:
        # Create a wrapper around the reward function that resets scored videos between each UID
        with patch('bitcast.validator.reward.reward', side_effect=reward_wrapper):
            # Patch query_miner to return our mock responses
            with patch('bitcast.validator.reward.query_miner', side_effect=mock_query_miner) as mock_query_miner_patch:
                # Call get_rewards
                result, yt_stats_list = await get_rewards(mock_self, uids)
        
        # Verify that the result is a numpy array
        assert isinstance(result, np.ndarray)
        
        # Since we have three miners and two briefs, and the briefs have max_burn=0:
        # 1. reward() gives UID 0 scores of 0
        # 2. scale_rewards() gives UID 0 0 reward when max_burn=0
        # 3. UID 1 gets more reward due to UID 2 having 30% advertising traffic
        # Calculation: UID 1 gets 1275 + 825 = 2100 minutes, UID 2 gets (850 + 550) * 0.7 = 980 minutes
        # Proportional split: UID 1 gets 2100/(2100+980) = 0.68, UID 2 gets 980/(2100+980) = 0.32
        expected_result = np.array([0.0, 0.68, 0.32])
        
        # Check that the result matches the expected values (with some tolerance for floating point)
        np.testing.assert_allclose(result, expected_result, rtol=1e-2)
        
        # Verify that get_briefs was called
        mock_get_briefs.assert_called_once()
        
        # Verify that query_miner was called for each UID
        assert mock_query_miner_patch.call_count == 3
        
        # Verify that yt_stats_list is returned
        assert isinstance(yt_stats_list, list)
        assert len(yt_stats_list) == 3
        
        # Verify the contents of yt_stats_list
        # UID 0 should have all zeros (from reward())
        assert "scores" in yt_stats_list[0]
        assert "brief1" in yt_stats_list[0]["scores"]
        assert "brief2" in yt_stats_list[0]["scores"]
        assert yt_stats_list[0]["scores"]["brief1"] == 0
        assert yt_stats_list[0]["scores"]["brief2"] == 0
        
        # UID 1 should have 100% scorable traffic
        assert "scores" in yt_stats_list[1]
        assert "brief1" in yt_stats_list[1]["scores"]
        assert "brief2" in yt_stats_list[1]["scores"]
        assert yt_stats_list[1]["scores"]["brief1"] == 1275  # 900 + 375 minutes watched
        assert yt_stats_list[1]["scores"]["brief2"] == 825  # 375 + 450 minutes watched
        
        # UID 2 should have scores reduced by scorable_proportion of 0.7
        assert "scores" in yt_stats_list[2]
        assert "brief1" in yt_stats_list[2]["scores"]
        assert "brief2" in yt_stats_list[2]["scores"]
        assert yt_stats_list[2]["scores"]["brief1"] == 595  # (600 + 250) * 0.7 minutes watched
        assert yt_stats_list[2]["scores"]["brief2"] == 385  # (250 + 300) * 0.7 minutes watched
