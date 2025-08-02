"""
Unit tests for individual brief publish date validation functionality.
"""

import pytest
from datetime import datetime

from bitcast.validator.platforms.youtube.evaluation.video.validation import (
    check_brief_publish_date_range
)


class TestCheckBriefPublishDateRange:
    """Test the check_brief_publish_date_range function."""

    def test_video_within_date_range(self):
        """Test video published within brief's date range."""
        video_data = {"publishedAt": "2023-06-15T12:00:00Z"}
        brief = {
            "id": "test_brief",
            "start_date": "2023-01-01",
            "end_date": "2023-12-31"
        }
        assert check_brief_publish_date_range(video_data, brief) is True

    def test_video_before_start_date_with_buffer(self):
        """Test video published before brief start date (even with buffer)."""
        video_data = {"publishedAt": "2022-12-28T12:00:00Z"}  # Before buffer
        brief = {
            "id": "test_brief",
            "start_date": "2023-01-01",  # Buffer makes allowed start 2022-12-29
            "end_date": "2023-12-31"
        }
        assert check_brief_publish_date_range(video_data, brief) is False

    def test_video_after_end_date(self):
        """Test video published after brief end date."""
        video_data = {"publishedAt": "2024-01-01T12:00:00Z"}
        brief = {
            "id": "test_brief",
            "start_date": "2023-01-01",
            "end_date": "2023-12-31"
        }
        assert check_brief_publish_date_range(video_data, brief) is False

    def test_video_on_buffer_boundary(self):
        """Test video published exactly on buffer boundary."""
        video_data = {"publishedAt": "2022-12-29T00:00:00Z"}  # Exactly on buffer boundary
        brief = {
            "id": "test_brief",
            "start_date": "2023-01-01",  # Buffer (3 days) makes allowed start 2022-12-29
            "end_date": "2023-12-31"
        }
        assert check_brief_publish_date_range(video_data, brief) is True

    def test_video_on_end_date_boundary(self):
        """Test video published exactly on end date."""
        video_data = {"publishedAt": "2023-12-31T23:59:59Z"}
        brief = {
            "id": "test_brief",
            "start_date": "2023-01-01",
            "end_date": "2023-12-31"
        }
        assert check_brief_publish_date_range(video_data, brief) is True

    def test_invalid_video_date(self):
        """Test with invalid video publishedAt date."""
        video_data = {"publishedAt": "invalid-date"}
        brief = {
            "id": "test_brief",
            "start_date": "2023-01-01",
            "end_date": "2023-12-31"
        }
        assert check_brief_publish_date_range(video_data, brief) is False

    def test_missing_video_published_at(self):
        """Test with missing publishedAt in video data."""
        video_data = {}
        brief = {
            "id": "test_brief",
            "start_date": "2023-01-01",
            "end_date": "2023-12-31"
        }
        assert check_brief_publish_date_range(video_data, brief) is False

    def test_invalid_brief_dates(self):
        """Test with invalid brief dates."""
        video_data = {"publishedAt": "2023-06-15T12:00:00Z"}
        brief = {
            "id": "test_brief",
            "start_date": "invalid-date",
            "end_date": "2023-12-31"
        }
        assert check_brief_publish_date_range(video_data, brief) is False 