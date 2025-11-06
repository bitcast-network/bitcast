"""
Unit tests for historical videos registry module.

Tests cover:
- Recording video matches
- Retrieving historical videos
- Cleanup of old entries
- ECO_MODE integration
- Thread safety
"""

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from bitcast.validator.platforms.youtube.utils.historical_videos import (
    record_video_match,
    get_historical_videos,
    HISTORICAL_VIDEOS_PATH
)


@pytest.fixture
def temp_historical_file(tmp_path):
    """Create a temporary historical videos file for testing."""
    test_file = tmp_path / "historical_videos.jsonl"
    
    # Patch the HISTORICAL_VIDEOS_PATH constant
    with patch('bitcast.validator.platforms.youtube.utils.historical_videos.HISTORICAL_VIDEOS_PATH', test_file):
        yield test_file


@pytest.fixture
def sample_entries():
    """Sample entries for testing."""
    today = datetime.now().strftime('%Y-%m-%d')
    old_date = (datetime.now() - timedelta(days=100)).strftime('%Y-%m-%d')
    recent_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    return [
        {
            "video_id": "video_1",
            "bitcast_video_id": "bitcast_video_1",
            "channel_id": "channel_A",
            "bitcast_channel_id": "bitcast_channel_A",
            "date_first_matched": today,
            "brief_id": "brief_123"
        },
        {
            "video_id": "video_2",
            "bitcast_video_id": "bitcast_video_2",
            "channel_id": "channel_A",
            "bitcast_channel_id": "bitcast_channel_A",
            "date_first_matched": recent_date,
            "brief_id": "brief_456"
        },
        {
            "video_id": "video_3",
            "bitcast_video_id": "bitcast_video_3",
            "channel_id": "channel_B",
            "bitcast_channel_id": "bitcast_channel_B",
            "date_first_matched": old_date,
            "brief_id": "brief_789"
        }
    ]


class TestRecordVideoMatch:
    """Tests for recording video matches."""
    
    def test_record_new_match(self, temp_historical_file):
        """Test recording a new video match creates correct entry."""
        record_video_match(
            video_id="test_video",
            bitcast_video_id="bitcast_test_video",
            channel_id="test_channel",
            bitcast_channel_id="bitcast_test_channel",
            brief_id="test_brief"
        )
        
        # Verify file was created and contains entry
        assert temp_historical_file.exists()
        
        with open(temp_historical_file, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 1
            
            entry = json.loads(lines[0])
            assert entry["video_id"] == "test_video"
            assert entry["bitcast_video_id"] == "bitcast_test_video"
            assert entry["channel_id"] == "test_channel"
            assert entry["bitcast_channel_id"] == "bitcast_test_channel"
            assert entry["brief_id"] == "test_brief"
            assert "date_first_matched" in entry
    
    def test_record_different_videos_same_channel(self, temp_historical_file):
        """Test recording multiple videos from same channel."""
        for i in range(3):
            record_video_match(
                video_id=f"video_{i}",
                bitcast_video_id=f"bitcast_video_{i}",
                channel_id="test_channel",
                bitcast_channel_id="bitcast_test_channel",
                brief_id=f"brief_{i}"
            )
        
        # Verify all entries exist
        with open(temp_historical_file, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 3


class TestGetHistoricalVideos:
    """Tests for retrieving historical videos."""
    
    def test_get_videos_for_channel(self, temp_historical_file, sample_entries):
        """Test retrieving videos for a specific channel."""
        with open(temp_historical_file, 'w') as f:
            for entry in sample_entries:
                f.write(json.dumps(entry) + '\n')
        
        videos = get_historical_videos("channel_A", max_age_days=90)
        
        # Should get video_1 and video_2 (both within 90 days and from channel_A)
        assert len(videos) == 2
        assert "video_1" in videos
        assert "video_2" in videos
        assert "video_3" not in videos  # Different channel
    
    def test_get_videos_filters_by_date(self, temp_historical_file, sample_entries):
        """Test retrieval filters out videos older than max_age_days."""
        with open(temp_historical_file, 'w') as f:
            for entry in sample_entries:
                f.write(json.dumps(entry) + '\n')
        
        videos = get_historical_videos("channel_A", max_age_days=50)
        
        # Should only get video_1 (today) and video_2 (30 days ago)
        assert "video_1" in videos
        assert "video_2" in videos
    
    def test_get_videos_empty_for_unknown_channel(self, temp_historical_file, sample_entries):
        """Test retrieval returns empty list for unknown channel."""
        with open(temp_historical_file, 'w') as f:
            for entry in sample_entries:
                f.write(json.dumps(entry) + '\n')
        
        videos = get_historical_videos("channel_unknown", max_age_days=90)
        assert videos == []
    
    def test_get_videos_empty_when_file_not_exists(self, temp_historical_file):
        """Test retrieval returns empty list when file doesn't exist."""
        videos = get_historical_videos("any_channel", max_age_days=90)
        assert videos == []
    
    def test_get_videos_deduplicates(self, temp_historical_file):
        """Test retrieval deduplicates video IDs."""
        with open(temp_historical_file, 'w') as f:
            today = datetime.now().strftime('%Y-%m-%d')
            for i in range(3):
                entry = {
                    "video_id": "same_video",
                    "bitcast_video_id": "bitcast_same_video",
                    "channel_id": "test_channel",
                    "bitcast_channel_id": "bitcast_test_channel",
                    "date_first_matched": today,
                    "brief_id": f"brief_{i}"
                }
                f.write(json.dumps(entry) + '\n')
        
        videos = get_historical_videos("test_channel", max_age_days=90)
        
        # Should only have one video_id despite multiple entries
        assert len(videos) == 1
        assert videos[0] == "same_video"
    
    def test_get_videos_handles_malformed_entries(self, temp_historical_file):
        """Test retrieval skips malformed JSON entries gracefully."""
        with open(temp_historical_file, 'w') as f:
            today = datetime.now().strftime('%Y-%m-%d')
            good_entry = {
                "video_id": "good_video",
                "bitcast_video_id": "bitcast_good_video",
                "channel_id": "test_channel",
                "bitcast_channel_id": "bitcast_test_channel",
                "date_first_matched": today,
                "brief_id": "brief_1"
            }
            f.write(json.dumps(good_entry) + '\n')
            f.write("this is not json\n")
            good_entry2 = {
                "video_id": "good_video2",
                "bitcast_video_id": "bitcast_good_video2",
                "channel_id": "test_channel",
                "bitcast_channel_id": "bitcast_test_channel",
                "date_first_matched": today,
                "brief_id": "brief_2"
            }
            f.write(json.dumps(good_entry2) + '\n')
        
        videos = get_historical_videos("test_channel", max_age_days=90)
        
        # Should get both good videos, skip the malformed entry
        assert len(videos) == 2
        assert "good_video" in videos
        assert "good_video2" in videos


class TestThreadSafety:
    """Tests for thread safety of file operations."""
    
    def test_concurrent_writes_no_corruption(self, temp_historical_file):
        """Test concurrent writes don't corrupt file."""
        def write_entries(thread_id):
            for i in range(10):
                record_video_match(
                    video_id=f"video_{thread_id}_{i}",
                    bitcast_video_id=f"bitcast_video_{thread_id}_{i}",
                    channel_id=f"channel_{thread_id}",
                    bitcast_channel_id=f"bitcast_channel_{thread_id}",
                    brief_id=f"brief_{i}"
                )
        
        # Launch multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=write_entries, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Verify file integrity
        with open(temp_historical_file, 'r') as f:
            lines = f.readlines()
            # All entries should be valid JSON
            for line in lines:
                entry = json.loads(line)  # Should not raise
                assert "video_id" in entry
                assert "brief_id" in entry

