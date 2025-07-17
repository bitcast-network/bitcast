"""
Tests for brief pre-screening functionality.
"""
import pytest
from unittest.mock import patch, MagicMock

from bitcast.validator.platforms.youtube.evaluation.video import (
    check_brief_unique_identifier,
    vet_video,
    initialize_decision_details
)
from bitcast.validator.utils.config import YT_MIN_VIDEO_RETENTION


class TestBriefPreScreening:
    """Test brief pre-screening functionality."""

    def test_check_brief_unique_identifier_case_insensitive(self):
        """Test that unique identifier matching is case insensitive."""
        brief = {"id": "test1", "unique_identifier": "BITCAST2024"}
        description = "This video is about bitcast2024 and blockchain technology"
        
        result = check_brief_unique_identifier(brief, description)
        assert result is True

    def test_check_brief_unique_identifier_no_match(self):
        """Test that non-matching identifiers return False."""
        brief = {"id": "test2", "unique_identifier": "SPECIAL_CODE"}
        description = "This video is about something else entirely"
        
        result = check_brief_unique_identifier(brief, description)
        assert result is False

    def test_check_brief_unique_identifier_empty_description(self):
        """Test handling of empty video descriptions."""
        brief = {"id": "test3", "unique_identifier": "TEST123"}
        description = ""
        
        result = check_brief_unique_identifier(brief, description)
        assert result is False

    def test_check_brief_unique_identifier_none_description(self):
        """Test handling of None video descriptions."""
        brief = {"id": "test4", "unique_identifier": "TEST123"}
        description = None
        
        result = check_brief_unique_identifier(brief, description)
        assert result is False

    def test_check_brief_unique_identifier_missing_field(self):
        """Test that missing unique_identifier field raises ValueError."""
        brief = {"id": "test5"}
        description = "Some description"
        
        with pytest.raises(ValueError, match="missing required unique_identifier field"):
            check_brief_unique_identifier(brief, description)

    def test_check_brief_unique_identifier_empty_field(self):
        """Test that empty unique_identifier field raises ValueError."""
        brief = {"id": "test6", "unique_identifier": ""}
        description = "Some description"
        
        with pytest.raises(ValueError, match="has empty unique_identifier field"):
            check_brief_unique_identifier(brief, description)

    def test_initialize_decision_details_includes_prescreening(self):
        """Test that decision details includes preScreeningCheck field."""
        details = initialize_decision_details()
        assert "preScreeningCheck" in details
        assert details["preScreeningCheck"] == []

    @patch('bitcast.validator.platforms.youtube.evaluation.video.get_video_transcript')
    @patch('bitcast.validator.platforms.youtube.evaluation.video.check_for_prompt_injection')
    @patch('bitcast.validator.platforms.youtube.evaluation.video.evaluate_content_against_brief')
    def test_vet_video_prescreening_filters_briefs(self, mock_evaluate_content, mock_check_injection, mock_get_transcript):
        """Test that pre-screening filters out briefs without matching unique identifiers."""
        # Setup mock data
        video_id = "test_video"
        briefs = [
            {"id": "brief1", "unique_identifier": "MATCH123", "start_date": "2023-01-01"},
            {"id": "brief2", "unique_identifier": "NOMATCH456", "start_date": "2023-01-01"}
        ]
        video_data = {
            "bitcastVideoId": video_id,
            "title": "Test Video",
            "description": "This video contains MATCH123 but not the other code",
            "publishedAt": "2023-01-15T00:00:00Z",
            "duration": "PT10M",
            "caption": False,
            "privacyStatus": "public"
        }
        video_analytics = {
            "averageViewPercentage": YT_MIN_VIDEO_RETENTION + 5,
            "estimatedMinutesWatched": 1000
        }

        # Mock dependencies
        mock_get_transcript.return_value = "Test transcript content"
        mock_check_injection.return_value = False  # No prompt injection
        mock_evaluate_content.return_value = (True, "Content meets brief")

        # Call vet_video
        result = vet_video(video_id, briefs, video_data, video_analytics)

        # Verify pre-screening results
        decision_details = result["decision_details"]
        assert decision_details["preScreeningCheck"] == [True, False]
        assert decision_details["contentAgainstBriefCheck"] == [True, False]
        
        # Verify only one brief was evaluated (the one that passed pre-screening)
        assert mock_evaluate_content.call_count == 1
        
        # Verify the reasoning for the filtered brief
        brief_reasonings = result["brief_reasonings"]
        assert len(brief_reasonings) == 2
        assert brief_reasonings[0] == "Content meets brief"
        assert brief_reasonings[1] == "Video description does not contain required unique identifier"

    @patch('bitcast.validator.platforms.youtube.evaluation.video.get_video_transcript')
    @patch('bitcast.validator.platforms.youtube.evaluation.video.check_for_prompt_injection')
    @patch('bitcast.validator.platforms.youtube.evaluation.video.evaluate_content_against_brief')
    def test_vet_video_no_briefs_pass_prescreening(self, mock_evaluate_content, mock_check_injection, mock_get_transcript):
        """Test that LLM evaluation is skipped when no briefs pass pre-screening."""
        # Setup mock data
        video_id = "test_video"
        briefs = [
            {"id": "brief1", "unique_identifier": "NOTFOUND1", "start_date": "2023-01-01"},
            {"id": "brief2", "unique_identifier": "NOTFOUND2", "start_date": "2023-01-01"}
        ]
        video_data = {
            "bitcastVideoId": video_id,
            "title": "Test Video", 
            "description": "This video doesn't contain any of the required codes",
            "publishedAt": "2023-01-15T00:00:00Z",
            "duration": "PT10M",
            "caption": False,
            "privacyStatus": "public"
        }
        video_analytics = {
            "averageViewPercentage": YT_MIN_VIDEO_RETENTION + 5,
            "estimatedMinutesWatched": 1000
        }

        # Mock dependencies
        mock_get_transcript.return_value = "Test transcript content"
        mock_check_injection.return_value = False  # No prompt injection

        # Call vet_video
        result = vet_video(video_id, briefs, video_data, video_analytics)

        # Verify pre-screening results
        decision_details = result["decision_details"]
        assert decision_details["preScreeningCheck"] == [False, False]
        assert decision_details["contentAgainstBriefCheck"] == [False, False]
        
        # Verify LLM evaluation was not called at all
        assert mock_evaluate_content.call_count == 0
        
        # Verify all briefs were filtered with appropriate reasoning
        brief_reasonings = result["brief_reasonings"]
        assert len(brief_reasonings) == 2
        assert all("does not contain required unique identifier" in reasoning for reasoning in brief_reasonings)

    @patch('bitcast.validator.platforms.youtube.evaluation.video.get_video_transcript')
    @patch('bitcast.validator.platforms.youtube.evaluation.video.check_for_prompt_injection')
    def test_vet_video_brief_validation_error(self, mock_check_injection, mock_get_transcript):
        """Test that brief validation errors are handled correctly."""
        # Setup mock data
        video_id = "test_video"
        briefs = [
            {"id": "brief1", "start_date": "2023-01-01"},  # Missing unique_identifier field
        ]
        video_data = {
            "bitcastVideoId": video_id,
            "title": "Test Video",
            "description": "Some description",
            "publishedAt": "2023-01-15T00:00:00Z",
            "duration": "PT10M",
            "caption": False,
            "privacyStatus": "public"
        }
        video_analytics = {
            "averageViewPercentage": YT_MIN_VIDEO_RETENTION + 5,
            "estimatedMinutesWatched": 1000
        }

        # Mock dependencies
        mock_get_transcript.return_value = "Test transcript content"
        mock_check_injection.return_value = False  # No prompt injection

        # Call vet_video
        result = vet_video(video_id, briefs, video_data, video_analytics)

        # Verify error handling
        decision_details = result["decision_details"]
        assert decision_details["video_vet_result"] is False
        assert decision_details["preScreeningCheck"] == [False]
        assert decision_details["contentAgainstBriefCheck"] == [False]
        
        # Verify error reasoning
        brief_reasonings = result["brief_reasonings"]
        assert len(brief_reasonings) == 1
        assert "missing required unique_identifier field" in brief_reasonings[0] 