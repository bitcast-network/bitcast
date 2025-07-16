"""
Global pytest configuration and fixtures for fast test execution.

This file provides comprehensive mocking of external API calls to prevent
slow network requests during testing.
"""

import pytest
from unittest.mock import patch, Mock
import numpy as np


@pytest.fixture(autouse=True)
def mock_external_apis():
    """
    Auto-use fixture that mocks all external API calls to speed up tests.
    This prevents real network requests during testing.
    """
    with patch('bitcast.validator.utils.briefs.get_briefs') as mock_briefs, \
         patch('bitcast.validator.utils.token_pricing.get_bitcast_alpha_price') as mock_price, \
         patch('bitcast.validator.utils.token_pricing.get_total_miner_emissions') as mock_emissions, \
         patch('bitcast.validator.utils.blacklist.get_blacklist_sources') as mock_blacklist, \
         patch('bitcast.validator.clients.OpenaiClient.evaluate_content_against_brief') as mock_openai_eval, \
         patch('bitcast.validator.clients.OpenaiClient.check_for_prompt_injection') as mock_openai_inject, \
         patch('bitcast.validator.platforms.youtube.api.transcript._fetch_transcript') as mock_transcript, \
         patch('requests.get') as mock_requests_get:
        
        # Mock briefs API
        mock_briefs.return_value = [
            {"id": "brief1", "title": "Test Brief 1", "format": "dedicated", "weight": 100},
            {"id": "brief2", "title": "Test Brief 2", "format": "pre-roll", "weight": 100}
        ]
        
        # Mock token pricing APIs
        mock_price.return_value = 1.0  # $1 per token
        mock_emissions.return_value = 1000.0  # 1000 tokens per day
        
        # Mock blacklist API
        mock_blacklist.return_value = ["ADVERTISING"]
        
        # Mock OpenAI API calls
        mock_openai_eval.return_value = (True, "Content matches brief criteria")
        mock_openai_inject.return_value = (False, "No prompt injection detected")
        
        # Mock transcript API
        mock_transcript.return_value = [{"text": "Sample video transcript"}]
        
        # Mock generic requests
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status.return_value = None
        mock_requests_get.return_value = mock_response
        
        yield {
            'briefs': mock_briefs,
            'price': mock_price,
            'emissions': mock_emissions,
            'blacklist': mock_blacklist,
            'openai_eval': mock_openai_eval,
            'openai_inject': mock_openai_inject,
            'transcript': mock_transcript,
            'requests': mock_requests_get
        }


@pytest.fixture(autouse=True)
def disable_delays():
    """
    Auto-use fixture that disables sleep calls and retry delays during testing.
    This makes tests run much faster by removing all artificial delays.
    """
    with patch('time.sleep') as mock_sleep, \
         patch('tenacity.wait_fixed') as mock_wait_fixed, \
         patch('tenacity.stop_after_attempt') as mock_stop_after:
        
        # Disable all sleep calls
        mock_sleep.return_value = None
        
        # Make retry mechanisms immediate (no wait between attempts)
        mock_wait_fixed.return_value = lambda x: 0  # No wait time
        mock_stop_after.return_value = lambda x: x <= 1  # Stop after 1 attempt
        
        yield


@pytest.fixture
def mock_youtube_api_calls():
    """
    Fixture that mocks YouTube API calls for tests that need them.
    """
    with patch('bitcast.validator.platforms.youtube.api.clients.initialize_youtube_clients') as mock_clients, \
         patch('bitcast.validator.platforms.youtube.api.channel.get_channel_data') as mock_channel_data, \
         patch('bitcast.validator.platforms.youtube.api.channel.get_channel_analytics') as mock_channel_analytics, \
         patch('bitcast.validator.platforms.youtube.api.video.get_all_uploads') as mock_uploads, \
         patch('bitcast.validator.platforms.youtube.api.video.get_video_data_batch') as mock_video_data, \
         patch('bitcast.validator.platforms.youtube.api.video.get_video_analytics') as mock_video_analytics:
        
        # Mock YouTube API clients
        mock_data_client = Mock()
        mock_analytics_client = Mock()
        mock_clients.return_value = (mock_data_client, mock_analytics_client)
        
        # Mock channel data
        mock_channel_data.return_value = {
            "id": "test_channel_id",
            "snippet": {
                "title": "Test Channel",
                "publishedAt": "2020-01-01T00:00:00Z",
                "subscriberCount": 10000
            }
        }
        
        # Mock channel analytics
        mock_channel_analytics.return_value = {
            "views": 1000000,
            "averageViewDuration": 120,
            "subscriberCount": 10000
        }
        
        # Mock video operations
        mock_uploads.return_value = ["video1", "video2", "video3"]
        mock_video_data.return_value = {
            "video1": {
                "videoId": "video1",
                "title": "Test Video 1",
                "publishedAt": "2024-01-01T00:00:00Z",
                "viewCount": 1000,
                "duration": "PT5M30S"
            }
        }
        mock_video_analytics.return_value = {
            "averageViewPercentage": 75,
            "estimatedRevenue": 10.0
        }
        
        yield {
            'clients': mock_clients,
            'channel_data': mock_channel_data,
            'channel_analytics': mock_channel_analytics,
            'uploads': mock_uploads,
            'video_data': mock_video_data,
            'video_analytics': mock_video_analytics
        }


@pytest.fixture
def fast_test_data():
    """
    Fixture providing common test data for fast test execution.
    """
    return {
        'uids': [0, 123, 456, 789],
        'briefs': [
            {"id": "brief1", "title": "Test Brief 1", "format": "dedicated", "weight": 100},
            {"id": "brief2", "title": "Test Brief 2", "format": "pre-roll", "weight": 100}
        ],
        'mock_rewards': np.array([0.4, 0.3, 0.2, 0.1]),
        'mock_stats': [
            {"uid": 0, "scores": {"brief1": 0.0}, "yt_account": {}},
            {"uid": 123, "scores": {"brief1": 0.5, "brief2": 0.3}, "yt_account": {}},
            {"uid": 456, "scores": {"brief1": 0.2, "brief2": 0.4}, "yt_account": {}},
            {"uid": 789, "scores": {"brief1": 0.1, "brief2": 0.2}, "yt_account": {}}
        ]
    }


# Performance optimization: disable logging during tests unless explicitly enabled
@pytest.fixture(autouse=True)
def fast_logging():
    """
    Reduce logging verbosity during tests for better performance.
    """
    import logging
    import bittensor as bt
    
    # Set higher log level to reduce output during tests
    logging.getLogger().setLevel(logging.WARNING)
    bt.logging.set_debug(False)
    
    yield
    
    # Restore normal logging after tests
    logging.getLogger().setLevel(logging.INFO) 