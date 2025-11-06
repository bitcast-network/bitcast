"""
Integration tests for historical videos feature with YouTube evaluation system.

Tests cover:
- End-to-end recording of video matches
- End-to-end retrieval and processing
- ECO_MODE integration
- Natural scoring exclusion of old videos
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from bitcast.validator.platforms.youtube.main import (
    process_single_video,
    process_videos
)


@pytest.fixture
def temp_historical_file(tmp_path):
    """Create a temporary historical videos file for testing."""
    test_file = tmp_path / "historical_videos.jsonl"
    
    # Patch the HISTORICAL_VIDEOS_PATH constant
    with patch('bitcast.validator.platforms.youtube.utils.historical_videos.HISTORICAL_VIDEOS_PATH', test_file):
        yield test_file


@pytest.fixture
def mock_result():
    """Create a mock result structure."""
    return {
        "yt_account": {
            "details": {
                "id": "test_channel_id",
                "bitcastChannelId": "bitcast_test_channel"
            },
            "analytics": {
                "ypp": True
            }
        },
        "videos": {},
        "scores": {"brief_1": 0, "brief_2": 0}
    }


@pytest.fixture
def mock_video_data():
    """Create mock video data."""
    return {
        "video_1": {
            "videoId": "video_1",
            "bitcastVideoId": "bitcast_video_1",
            "title": "Test Video 1",
            "publishedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        },
        "video_2": {
            "videoId": "video_2",
            "bitcastVideoId": "bitcast_video_2",
            "title": "Test Video 2",
            "publishedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        }
    }


@pytest.fixture
def mock_briefs():
    """Create mock briefs."""
    return [
        {"id": "brief_1", "start_date": "2025-01-01", "end_date": "2025-12-31"},
        {"id": "brief_2", "start_date": "2025-01-01", "end_date": "2025-12-31"}
    ]


class TestEndToEndRecording:
    """Tests for end-to-end recording of video matches."""
    
    @patch('bitcast.validator.platforms.youtube.main.ECO_MODE', False)
    def test_matching_video_recorded_to_registry(
        self, temp_historical_file, mock_result, mock_video_data, mock_briefs
    ):
        """Test that video matching a brief is recorded to historical registry."""
        video_id = "video_1"
        video_data_dict = mock_video_data
        video_analytics_dict = {"video_1": {"averageViewPercentage": 50}}
        video_matches = {"video_1": [True, False]}  # Matches first brief
        video_decision_details = {
            "video_1": {
                "video_vet_result": True,
                "privacyCheck": True,
                "publishDateCheck": True
            }
        }
        
        # Mock the update_video_score function
        with patch('bitcast.validator.platforms.youtube.main.update_video_score'):
            process_single_video(
                video_id=video_id,
                video_data_dict=video_data_dict,
                video_analytics_dict=video_analytics_dict,
                video_matches=video_matches,
                video_decision_details=video_decision_details,
                briefs=mock_briefs,
                youtube_analytics_client=Mock(),
                result=mock_result,
                is_ypp_account=True,
                channel_analytics={}
            )
        
        # Verify entry was recorded
        assert temp_historical_file.exists()
        
        with open(temp_historical_file, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 1
            
            entry = json.loads(lines[0])
            assert entry["video_id"] == "video_1"
            assert entry["bitcast_video_id"] == "bitcast_video_1"
            assert entry["channel_id"] == "test_channel_id"
            assert entry["brief_id"] == "brief_1"
    
    @patch('bitcast.validator.platforms.youtube.main.ECO_MODE', False)
    def test_non_matching_video_not_recorded(
        self, temp_historical_file, mock_result, mock_video_data, mock_briefs
    ):
        """Test that video not matching any brief is not recorded."""
        video_id = "video_1"
        video_data_dict = mock_video_data
        video_analytics_dict = {"video_1": {"averageViewPercentage": 50}}
        video_matches = {"video_1": [False, False]}  # Matches no briefs
        video_decision_details = {
            "video_1": {
                "video_vet_result": True,
                "privacyCheck": True,
                "publishDateCheck": True
            }
        }
        
        process_single_video(
            video_id=video_id,
            video_data_dict=video_data_dict,
            video_analytics_dict=video_analytics_dict,
            video_matches=video_matches,
            video_decision_details=video_decision_details,
            briefs=mock_briefs,
            youtube_analytics_client=Mock(),
            result=mock_result,
            is_ypp_account=True,
            channel_analytics={}
        )
        
        # Verify no entry was recorded
        assert not temp_historical_file.exists()
    
    @patch('bitcast.validator.platforms.youtube.main.ECO_MODE', False)
    def test_failed_vetting_not_recorded(
        self, temp_historical_file, mock_result, mock_video_data, mock_briefs
    ):
        """Test that video failing vetting is not recorded."""
        video_id = "video_1"
        video_data_dict = mock_video_data
        video_analytics_dict = {"video_1": {"averageViewPercentage": 50}}
        video_matches = {"video_1": [True, False]}  # Would match brief
        video_decision_details = {
            "video_1": {
                "video_vet_result": False,  # Failed vetting
                "privacyCheck": False
            }
        }
        
        process_single_video(
            video_id=video_id,
            video_data_dict=video_data_dict,
            video_analytics_dict=video_analytics_dict,
            video_matches=video_matches,
            video_decision_details=video_decision_details,
            briefs=mock_briefs,
            youtube_analytics_client=Mock(),
            result=mock_result,
            is_ypp_account=True,
            channel_analytics={}
        )
        
        # Verify no entry was recorded
        assert not temp_historical_file.exists()


class TestEndToEndRetrieval:
    """Tests for end-to-end retrieval and processing."""
    
    @patch('bitcast.validator.platforms.youtube.main.ECO_MODE', False)
    @patch('bitcast.validator.platforms.youtube.main.get_all_uploads')
    @patch('bitcast.validator.platforms.youtube.main.vet_videos')
    def test_historical_videos_added_to_processing(
        self, mock_vet_videos, mock_get_uploads, temp_historical_file, mock_result, mock_briefs
    ):
        """Test that historical videos are added to processing list."""
        # Mock recent uploads
        mock_get_uploads.return_value = ["recent_video_1", "recent_video_2"]
        
        # Add historical video to registry
        with open(temp_historical_file, 'w') as f:
            today = datetime.now().strftime('%Y-%m-%d')
            entry = {
                "video_id": "historical_video_1",
                "bitcast_video_id": "bitcast_historical_video_1",
                "channel_id": "test_channel_id",
                "bitcast_channel_id": "bitcast_test_channel",
                "date_first_matched": today,
                "brief_id": "brief_1"
            }
            f.write(json.dumps(entry) + '\n')
        
        # Mock vet_videos to return empty results
        mock_vet_videos.return_value = ({}, {}, {}, {})
        
        # Call process_videos
        process_videos(
            youtube_data_client=Mock(),
            youtube_analytics_client=Mock(),
            briefs=mock_briefs,
            result=mock_result
        )
        
        # Verify vet_videos was called with all videos (recent + historical)
        called_video_ids = mock_vet_videos.call_args[0][0]
        assert "recent_video_1" in called_video_ids
        assert "recent_video_2" in called_video_ids
        assert "historical_video_1" in called_video_ids
        assert len(called_video_ids) == 3
    
    @patch('bitcast.validator.platforms.youtube.main.ECO_MODE', False)
    @patch('bitcast.validator.platforms.youtube.main.get_all_uploads')
    @patch('bitcast.validator.platforms.youtube.main.vet_videos')
    def test_deduplication_of_historical_and_recent(
        self, mock_vet_videos, mock_get_uploads, temp_historical_file, mock_result, mock_briefs
    ):
        """Test that videos appearing in both lists are deduplicated."""
        # Mock recent uploads (includes video_1)
        mock_get_uploads.return_value = ["video_1", "video_2"]
        
        # Add video_1 to historical registry (duplicate)
        with open(temp_historical_file, 'w') as f:
            today = datetime.now().strftime('%Y-%m-%d')
            entry = {
                "video_id": "video_1",  # Same as in recent uploads
                "bitcast_video_id": "bitcast_video_1",
                "channel_id": "test_channel_id",
                "bitcast_channel_id": "bitcast_test_channel",
                "date_first_matched": today,
                "brief_id": "brief_1"
            }
            f.write(json.dumps(entry) + '\n')
        
        # Mock vet_videos to return empty results
        mock_vet_videos.return_value = ({}, {}, {}, {})
        
        # Call process_videos
        process_videos(
            youtube_data_client=Mock(),
            youtube_analytics_client=Mock(),
            briefs=mock_briefs,
            result=mock_result
        )
        
        # Verify vet_videos was called with deduplicated list
        called_video_ids = mock_vet_videos.call_args[0][0]
        assert called_video_ids.count("video_1") == 1  # No duplicates
        assert len(called_video_ids) == 2  # Only video_1 and video_2


class TestEcoModeIntegration:
    """Tests for ECO_MODE integration in full flow."""
    
    @patch('bitcast.validator.platforms.youtube.utils.historical_videos.ECO_MODE', True)
    @patch('bitcast.validator.platforms.youtube.main.ECO_MODE', True)
    def test_no_recording_in_eco_mode(
        self, temp_historical_file, mock_result, mock_video_data, mock_briefs
    ):
        """Test that no recording happens in ECO_MODE."""
        video_id = "video_1"
        video_data_dict = mock_video_data
        video_analytics_dict = {"video_1": {"averageViewPercentage": 50}}
        video_matches = {"video_1": [True, False]}
        video_decision_details = {
            "video_1": {
                "video_vet_result": True,
                "privacyCheck": True
            }
        }
        
        with patch('bitcast.validator.platforms.youtube.main.update_video_score'):
            process_single_video(
                video_id=video_id,
                video_data_dict=video_data_dict,
                video_analytics_dict=video_analytics_dict,
                video_matches=video_matches,
                video_decision_details=video_decision_details,
                briefs=mock_briefs,
                youtube_analytics_client=Mock(),
                result=mock_result,
                is_ypp_account=True,
                channel_analytics={}
            )
        
        # Verify no file was created
        assert not temp_historical_file.exists()
    
    @patch('bitcast.validator.platforms.youtube.utils.historical_videos.ECO_MODE', True)
    @patch('bitcast.validator.platforms.youtube.main.ECO_MODE', True)
    @patch('bitcast.validator.platforms.youtube.main.get_all_uploads')
    @patch('bitcast.validator.platforms.youtube.main.vet_videos')
    def test_no_retrieval_in_eco_mode(
        self, mock_vet_videos, mock_get_uploads, temp_historical_file, mock_result, mock_briefs
    ):
        """Test that no historical videos are retrieved in ECO_MODE."""
        # Mock recent uploads
        mock_get_uploads.return_value = ["recent_video_1"]
        
        # Add historical video to registry (should be ignored)
        with open(temp_historical_file, 'w') as f:
            today = datetime.now().strftime('%Y-%m-%d')
            entry = {
                "video_id": "historical_video_1",
                "bitcast_video_id": "bitcast_historical_video_1",
                "channel_id": "test_channel_id",
                "bitcast_channel_id": "bitcast_test_channel",
                "date_first_matched": today,
                "brief_id": "brief_1"
            }
            f.write(json.dumps(entry) + '\n')
        
        # Mock vet_videos to return empty results
        mock_vet_videos.return_value = ({}, {}, {}, {})
        
        # Call process_videos
        process_videos(
            youtube_data_client=Mock(),
            youtube_analytics_client=Mock(),
            briefs=mock_briefs,
            result=mock_result
        )
        
        # Verify vet_videos was called with only recent videos
        called_video_ids = mock_vet_videos.call_args[0][0]
        assert called_video_ids == ["recent_video_1"]
        assert "historical_video_1" not in called_video_ids


class TestNaturalScoringExclusion:
    """Tests that old videos naturally score 0 without explicit exclusion."""
    
    @patch('bitcast.validator.platforms.youtube.main.ECO_MODE', False)
    def test_old_video_scores_zero_naturally(
        self, temp_historical_file, mock_result, mock_briefs
    ):
        """Test that old videos score 0 due to date validation, not explicit exclusion."""
        # Create video from 120 days ago (outside brief window)
        old_date = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        video_id = "old_video"
        video_data_dict = {
            "old_video": {
                "videoId": "old_video",
                "bitcastVideoId": "bitcast_old_video",
                "title": "Old Video",
                "publishedAt": old_date
            }
        }
        video_analytics_dict = {"old_video": {"averageViewPercentage": 50}}
        video_matches = {"old_video": [False, False]}  # Would fail date check
        video_decision_details = {
            "old_video": {
                "video_vet_result": False,  # Failed vetting (date check)
                "publishDateCheck": False
            }
        }
        
        process_single_video(
            video_id=video_id,
            video_data_dict=video_data_dict,
            video_analytics_dict=video_analytics_dict,
            video_matches=video_matches,
            video_decision_details=video_decision_details,
            briefs=mock_briefs,
            youtube_analytics_client=Mock(),
            result=mock_result,
            is_ypp_account=True,
            channel_analytics={}
        )
        
        # Verify video has score of 0
        assert mock_result["videos"]["old_video"]["score"] == 0
        assert mock_result["videos"]["old_video"]["matches_brief"] is False

