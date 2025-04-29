import pytest
from bitcast.validator.socials.youtube.youtube_utils import get_video_transcript
from unittest.mock import MagicMock, patch
from bitcast.validator.config import TRANSCRIPT_MAX_RETRY
from bitcast.validator.socials.youtube.youtube_scoring import update_video_score, check_video_brief_matches


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
        result["videos"][video_id_1] = {"details": {}, "analytics": {}}  # Initialize video data
        mock_calculate.return_value = {"score": 2, "daily_analytics": {}}
        update_video_score(video_id_1, youtube_analytics_client, video_matches, briefs, result)
        assert result["scores"]["test_brief"] == 2, "First score should be 2"
        
        # Test case 2: Second video with score 4
        video_id_2 = "test_video_id_2"
        video_matches[video_id_2] = [True]  # Add to video_matches
        result["videos"][video_id_2] = {"details": {}, "analytics": {}}  # Initialize video data
        mock_calculate.return_value = {"score": 4, "daily_analytics": {}}
        update_video_score(video_id_2, youtube_analytics_client, video_matches, briefs, result)
        assert result["scores"]["test_brief"] == 6, "Score should be sum of 2 and 4"
        
        # Test case 3: Third video with score 2
        video_id_3 = "test_video_id_3"
        video_matches[video_id_3] = [True]  # Add to video_matches
        result["videos"][video_id_3] = {"details": {}, "analytics": {}}  # Initialize video data
        mock_calculate.return_value = {"score": 2, "daily_analytics": {}}
        update_video_score(video_id_3, youtube_analytics_client, video_matches, briefs, result)
        assert result["scores"]["test_brief"] == 8, "Score should be sum of 2, 4, and 2"
        
        # Test case 4: Fourth video with score 0
        video_id_4 = "test_video_id_4"
        video_matches[video_id_4] = [True]  # Add to video_matches
        result["videos"][video_id_4] = {"details": {}, "analytics": {}}  # Initialize video data
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
