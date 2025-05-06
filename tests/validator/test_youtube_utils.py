import pytest
from bitcast.validator.socials.youtube.youtube_utils import get_video_transcript, youtube_cache
from unittest.mock import MagicMock, patch
from bitcast.validator.utils.config import TRANSCRIPT_MAX_RETRY
import os
import shutil
import time
from diskcache import Cache

@pytest.mark.asyncio
async def test_get_video_transcript_retry_logic():
    video_id = "mock_video_id"
    rapid_api_key = "mock_rapid_api_key"
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(side_effect=[
        {"error": "This video has no subtitles."},  # First attempt
        {"error": "This video has no subtitles."},  # Second attempt
        [{"transcription": "mock_transcription"}]   # Third attempt, success
    ])

    with patch('bitcast.validator.socials.youtube.youtube_utils.requests.get', return_value=mock_response) as mock_get:
        with patch('bitcast.validator.socials.youtube.youtube_utils.time.sleep', return_value=None):  # Mock time.sleep to avoid delays
            transcript = get_video_transcript(video_id, rapid_api_key)
            assert transcript == "mock_transcription"
            assert mock_get.call_count == 3  # Ensure it retried 3 times

@pytest.fixture
def cache_dir():
    """Fixture to create and clean up a temporary cache directory."""
    test_cache_dir = os.path.join(os.path.expanduser("~"), ".bitcast", "cache", "youtube_test")
    os.makedirs(test_cache_dir, exist_ok=True)
    yield test_cache_dir
    shutil.rmtree(test_cache_dir)

def test_youtube_cache_basic_operations(cache_dir):
    """Test basic cache operations."""
    # Create a new cache instance with test directory
    test_cache = Cache(cache_dir)
    
    # Create a new YouTubeCache instance with our test cache
    from bitcast.validator.socials.youtube.youtube_utils import YouTubeCache
    cache = YouTubeCache()
    cache.cache = test_cache
    
    # Test setting and getting cache
    video_id = "test_video_1"
    test_data = {"results": [True, False], "video_data": {"title": "Test Video"}}
    cache.set_video_cache(video_id, test_data)
    
    # Test immediate retrieval
    cached_data = cache.get_video_cache(video_id)
    assert cached_data == test_data
    
    # Test cache expiration
    # Set a very short expiration time (1 second)
    test_cache.set(f"video_{video_id}", test_data, expire=1)
    time.sleep(1.1)  # Wait for expiration
    cache.clear_expired()
    assert cache.get_video_cache(video_id) is None 