"""
Tests for brief pre-screening functionality.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from bitcast.validator.platforms.youtube.evaluation.video import (
    check_brief_unique_identifier,
    vet_video,
    initialize_decision_details,
    prescreen_briefs_for_video
)
from bitcast.validator.utils.config import YT_MIN_VIDEO_RETENTION

# Calculate recent dates for tests
current_date = datetime.now()
brief_start = (current_date - timedelta(days=10)).strftime("%Y-%m-%d")
brief_end = (current_date + timedelta(days=10)).strftime("%Y-%m-%d")
video_publish_date = (current_date - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")


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

    @patch('bitcast.validator.platforms.youtube.evaluation.video.orchestration.get_video_transcript')
    @patch('bitcast.validator.clients.OpenaiClient.check_for_prompt_injection')
    @patch('bitcast.validator.platforms.youtube.evaluation.video.brief_matching.evaluate_content_against_brief')
    @patch('bitcast.validator.platforms.youtube.evaluation.video.brief_matching.ThreadPoolExecutor')
    def test_vet_video_prescreening_filters_briefs(self, mock_executor, mock_evaluate_content, mock_check_injection, mock_get_transcript):
        """Test that pre-screening filters out briefs without matching unique identifiers."""
        # Setup mock data
        video_id = "test_video"
        briefs = [
            {"id": "brief1", "unique_identifier": "MATCH123", "start_date": brief_start, "end_date": brief_end, "brief": "Test brief 1 content"},
            {"id": "brief2", "unique_identifier": "NOMATCH456", "start_date": brief_start, "end_date": brief_end, "brief": "Test brief 2 content"}
        ]
        video_data = {
            "bitcastVideoId": video_id,
            "title": "Test Video",
            "description": "This video contains MATCH123 but not the other code",
            "publishedAt": video_publish_date,
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
        
        # Mock ThreadPoolExecutor to execute synchronously
        def sync_submit(fn, *args, **kwargs):
            from concurrent.futures import Future
            future = Future()
            try:
                result = fn(*args, **kwargs)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)
            return future
        
        mock_executor_instance = MagicMock()
        mock_executor_instance.submit = sync_submit
        mock_executor_instance.__enter__ = MagicMock(return_value=mock_executor_instance)
        mock_executor_instance.__exit__ = MagicMock(return_value=None)
        mock_executor.return_value = mock_executor_instance

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

    @patch('bitcast.validator.platforms.youtube.evaluation.video.orchestration.get_video_transcript')
    @patch('bitcast.validator.clients.OpenaiClient.check_for_prompt_injection')
    @patch('bitcast.validator.clients.OpenaiClient.evaluate_content_against_brief')
    def test_vet_video_no_briefs_pass_prescreening(self, mock_evaluate_content, mock_check_injection, mock_get_transcript):
        """Test that LLM evaluation is skipped when no briefs pass pre-screening."""
        # Setup mock data
        video_id = "test_video"
        briefs = [
            {"id": "brief1", "unique_identifier": "NOTFOUND1", "start_date": brief_start, "end_date": brief_end, "brief": "Test brief 1 content"},
            {"id": "brief2", "unique_identifier": "NOTFOUND2", "start_date": brief_start, "end_date": brief_end, "brief": "Test brief 2 content"}
        ]
        video_data = {
            "bitcastVideoId": video_id,
            "title": "Test Video",
            "description": "This video doesn't contain any of the required codes",
            "publishedAt": video_publish_date,
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

    @patch('bitcast.validator.platforms.youtube.evaluation.video.orchestration.get_video_transcript')
    @patch('bitcast.validator.clients.OpenaiClient.check_for_prompt_injection')
    def test_vet_video_brief_validation_error(self, mock_check_injection, mock_get_transcript):
        """Test that brief validation errors are handled correctly - only the invalid brief fails."""
        # Setup mock data
        video_id = "test_video"
        briefs = [
            {"id": "brief1", "start_date": brief_start, "end_date": brief_end, "brief": "Test brief 1 content"},  # Missing unique_identifier field
        ]
        video_data = {
            "bitcastVideoId": video_id,
            "title": "Test Video",
            "description": "Some description",
            "publishedAt": video_publish_date,
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

        # Verify that the video evaluation doesn't fail entirely due to brief validation error
        decision_details = result["decision_details"]
        assert decision_details["video_vet_result"] is True  # Video evaluation should still succeed
        assert decision_details["preScreeningCheck"] == [False]  # Brief fails pre-screening
        assert decision_details["contentAgainstBriefCheck"] == [False]  # Brief fails content check
        
        # Verify error reasoning - should contain the default message since we just log validation errors
        brief_reasonings = result["brief_reasonings"]
        assert len(brief_reasonings) == 1
        assert brief_reasonings[0] == "Video description does not contain required unique identifier"

    @patch('bitcast.validator.platforms.youtube.evaluation.video.orchestration.get_video_transcript')
    @patch('bitcast.validator.clients.OpenaiClient.check_for_prompt_injection')
    @patch('bitcast.validator.platforms.youtube.evaluation.video.brief_matching.evaluate_content_against_brief')
    @patch('bitcast.validator.platforms.youtube.evaluation.video.brief_matching.ThreadPoolExecutor')
    def test_vet_video_mixed_valid_invalid_briefs(self, mock_executor, mock_evaluate_content, mock_check_injection, mock_get_transcript):
        """Test that evaluation continues for valid briefs even when some briefs have validation errors."""
        # Setup mock data
        video_id = "test_video"
        briefs = [
            {"id": "brief1", "unique_identifier": "VALID123", "start_date": brief_start, "end_date": brief_end, "brief": "Test brief 1 content"},  # Valid brief
            {"id": "brief2", "start_date": brief_start, "end_date": brief_end, "brief": "Test brief 2 content"},  # Missing unique_identifier field
            {"id": "brief3", "unique_identifier": "NOMATCH456", "start_date": brief_start, "end_date": brief_end, "brief": "Test brief 3 content"}  # Valid but no match
        ]
        video_data = {
            "bitcastVideoId": video_id,
            "title": "Test Video",
            "description": "This video contains VALID123 for testing",
            "publishedAt": video_publish_date,
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
        
        # Mock ThreadPoolExecutor to execute synchronously
        def sync_submit(fn, *args, **kwargs):
            from concurrent.futures import Future
            future = Future()
            try:
                result = fn(*args, **kwargs)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)
            return future
        
        mock_executor_instance = MagicMock()
        mock_executor_instance.submit = sync_submit
        mock_executor_instance.__enter__ = MagicMock(return_value=mock_executor_instance)
        mock_executor_instance.__exit__ = MagicMock(return_value=None)
        mock_executor.return_value = mock_executor_instance

        # Call vet_video
        result = vet_video(video_id, briefs, video_data, video_analytics)

        # Verify that the video evaluation succeeds and processes valid briefs
        decision_details = result["decision_details"]
        assert decision_details["video_vet_result"] is True
        assert decision_details["preScreeningCheck"] == [True, False, False]  # Only first brief passes
        assert decision_details["contentAgainstBriefCheck"] == [True, False, False]  # Only first brief evaluated
        
        # Verify only the valid brief was evaluated by LLM
        assert mock_evaluate_content.call_count == 1
        
        # Verify reasoning for each brief
        brief_reasonings = result["brief_reasonings"]
        assert len(brief_reasonings) == 3
        assert brief_reasonings[0] == "Content meets brief"  # Valid brief that passed
        assert brief_reasonings[1] == "Video description does not contain required unique identifier"  # Default message
        assert brief_reasonings[2] == "Video description does not contain required unique identifier"  # No match
        
        # Verify met_brief_ids contains only the valid brief
        assert result["met_brief_ids"] == ["brief1"]

    def test_prescreen_briefs_for_video_with_validation_errors(self):
        """Test that prescreen_briefs_for_video handles validation errors gracefully."""
        briefs = [
            {"id": "brief1", "unique_identifier": "VALID123", "brief": "Test brief 1 content", 
             "start_date": brief_start, "end_date": brief_end},  # Valid brief
            {"id": "brief2", "brief": "Test brief 2 content",
             "start_date": brief_start, "end_date": brief_end},  # Missing unique_identifier field
            {"id": "brief3", "unique_identifier": "", "brief": "Test brief 3 content",
             "start_date": brief_start, "end_date": brief_end},  # Empty unique_identifier field
            {"id": "brief4", "unique_identifier": "NOMATCH456", "brief": "Test brief 4 content",
             "start_date": brief_start, "end_date": brief_end}  # Valid but no match
        ]
        video_description = "This video contains VALID123 for testing"
        video_data = {"publishedAt": video_publish_date}  # Valid publish date within range
        
        # Call prescreen_briefs_for_video
        eligible_briefs, prescreening_results, filtered_brief_ids = prescreen_briefs_for_video(briefs, video_description, video_data)
        
        # Verify only the first brief passed pre-screening
        assert len(eligible_briefs) == 1
        assert eligible_briefs[0]["id"] == "brief1"
        
        # Verify prescreening results for all briefs
        assert prescreening_results == [True, False, False, False]
        
        # Verify filtered brief IDs (validation errors and non-matches are both filtered)
        assert set(filtered_brief_ids) == {"brief2", "brief3", "brief4"} 