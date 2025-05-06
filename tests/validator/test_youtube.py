import pytest
from bitcast.validator.socials.youtube.youtube_utils import get_video_transcript, youtube_cache
from unittest.mock import MagicMock, patch
from bitcast.validator.utils.config import TRANSCRIPT_MAX_RETRY
from bitcast.validator.socials.youtube.youtube_scoring import update_video_score, check_video_brief_matches
from bitcast.validator.socials.youtube.youtube_evaluation import vet_videos
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


@pytest.mark.asyncio
async def test_update_video_score():
    # Setup
    youtube_analytics_client = MagicMock()
    briefs = [{"id": "test_brief"}]
    result = {"videos": {}, "scores": {"test_brief": 0}}
    
    # Create a single video_matches dictionary that will be updated
    video_matches = {}
    
    # Mock calculate_video_score to return different scores
    with patch('bitcast.validator.socials.youtube.youtube_scoring.calculate_video_score') as mock_calculate:
        # Test case 1: First video with score 2
        video_id_1 = "test_video_id_1"
        video_matches[video_id_1] = [True]  # Add to video_matches
        result["videos"][video_id_1] = {"details": {"bitcastVideoId": video_id_1}, "analytics": {}}  # Initialize video data
        mock_calculate.return_value = {"score": 2, "daily_analytics": {}}
        update_video_score(video_id_1, youtube_analytics_client, video_matches, briefs, result)
        assert result["scores"]["test_brief"] == 2, "First score should be 2"
        
        # Test case 2: Second video with score 4
        video_id_2 = "test_video_id_2"
        video_matches[video_id_2] = [True]  # Add to video_matches
        result["videos"][video_id_2] = {"details": {"bitcastVideoId": video_id_2}, "analytics": {}}  # Initialize video data
        mock_calculate.return_value = {"score": 4, "daily_analytics": {}}
        update_video_score(video_id_2, youtube_analytics_client, video_matches, briefs, result)
        assert result["scores"]["test_brief"] == 6, "Score should be sum of 2 and 4"
        
        # Test case 3: Third video with score 2
        video_id_3 = "test_video_id_3"
        video_matches[video_id_3] = [True]  # Add to video_matches
        result["videos"][video_id_3] = {"details": {"bitcastVideoId": video_id_3}, "analytics": {}}  # Initialize video data
        mock_calculate.return_value = {"score": 2, "daily_analytics": {}}
        update_video_score(video_id_3, youtube_analytics_client, video_matches, briefs, result)
        assert result["scores"]["test_brief"] == 8, "Score should be sum of 2, 4, and 2"
        
        # Test case 4: Fourth video with score 0
        video_id_4 = "test_video_id_4"
        video_matches[video_id_4] = [True]  # Add to video_matches
        result["videos"][video_id_4] = {"details": {"bitcastVideoId": video_id_4}, "analytics": {}}  # Initialize video data
        mock_calculate.return_value = {"score": 0, "daily_analytics": {}}
        update_video_score(video_id_4, youtube_analytics_client, video_matches, briefs, result)
        assert result["scores"]["test_brief"] == 8, "Score should remain 8 (sum of 2, 4, 2, and 0)"

def test_check_video_brief_matches():
    # Setup
    video_id = "test_video"
    briefs = [
        {"id": "brief1"},
        {"id": "brief2"},
        {"id": "brief3"}
    ]
    
    # Test case 1: Video matches multiple briefs
    video_matches = {
        video_id: [True, True, False]  # Matches brief1 and brief2
    }
    matches_any_brief, matching_brief_ids = check_video_brief_matches(video_id, video_matches, briefs)
    assert matches_any_brief == True
    assert matching_brief_ids == ["brief1", "brief2"]
    
    # Test case 2: Video matches no briefs
    video_matches = {
        video_id: [False, False, False]
    }
    matches_any_brief, matching_brief_ids = check_video_brief_matches(video_id, video_matches, briefs)
    assert matches_any_brief == False
    assert matching_brief_ids == []
    
    # Test case 3: Video matches all briefs
    video_matches = {
        video_id: [True, True, True]
    }
    matches_any_brief, matching_brief_ids = check_video_brief_matches(video_id, video_matches, briefs)
    assert matches_any_brief == True
    assert matching_brief_ids == ["brief1", "brief2", "brief3"]

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
