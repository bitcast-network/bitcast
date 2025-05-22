import pytest
import bittensor as bt
from unittest.mock import MagicMock, patch

from bitcast.validator.socials.youtube.youtube_evaluation import (
    vet_video,
    check_video_privacy,
    check_video_publish_date,
    check_video_retention,
    check_manual_captions,
    check_prompt_injection,
    get_video_transcript
)
from bitcast.validator.utils.config import (
    YT_MIN_VIDEO_RETENTION,
    YT_VIDEO_RELEASE_BUFFER
)

# Mock functions to isolate testing of ECO_MODE
class Mocks:
    @staticmethod
    def mock_check_video_privacy(video_data, decision_details):
        decision_details["publicVideo"] = True
        return True
    
    @staticmethod
    def mock_check_video_privacy_fail(video_data, decision_details):
        decision_details["publicVideo"] = False
        # Initialize with a single False since we don't have access to briefs here
        decision_details["contentAgainstBriefCheck"] = [False]
        return False
    
    @staticmethod
    def mock_check_video_publish_date(video_data, briefs, decision_details):
        decision_details["publishDateCheck"] = True
        return True
    
    @staticmethod
    def mock_check_video_retention(video_data, video_analytics, decision_details):
        decision_details["averageViewPercentageCheck"] = True
        return True
    
    @staticmethod
    def mock_check_manual_captions(video_id, video_data, decision_details):
        decision_details["manualCaptionsCheck"] = True
        return True
    
    @staticmethod
    def mock_get_video_transcript(video_id, video_data):
        return "Sample transcript text for testing."
    
    @staticmethod
    def mock_check_prompt_injection(video_id, video_data, transcript, decision_details):
        decision_details["promptInjectionCheck"] = True
        return True


# Test ECO_MODE enabled with early return
@patch('bitcast.validator.socials.youtube.youtube_evaluation.ECO_MODE', True)
@patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_privacy', Mocks.mock_check_video_privacy_fail)
def test_eco_mode_enabled_early_return():
    """Test that ECO_MODE causes early return when a check fails."""
    # Setup
    video_id = "test_video_1"
    briefs = [{"id": "brief1"}, {"id": "brief2"}]
    video_data = {
        "bitcastVideoId": video_id,
        "privacyStatus": "private",  # This should fail the privacy check
    }
    video_analytics = {"averageViewPercentage": YT_MIN_VIDEO_RETENTION + 5}
    
    # Create patches for all subsequent checks
    with patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_publish_date') as mock_publish_date, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_retention') as mock_retention, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_manual_captions') as mock_captions, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.get_video_transcript') as mock_transcript, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_prompt_injection') as mock_prompt_injection, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.evaluate_content_against_briefs') as mock_evaluate:
        
        # Call the function
        result = vet_video(video_id, briefs, video_data, video_analytics)
        
        # Verify early exit with ECO_MODE
        mock_publish_date.assert_not_called()
        mock_retention.assert_not_called()
        mock_captions.assert_not_called()
        mock_transcript.assert_not_called()
        mock_prompt_injection.assert_not_called()
        mock_evaluate.assert_not_called()
        
        # Verify the result contains expected values
        assert "decision_details" in result
        assert result["decision_details"]["video_vet_result"] == False
        assert result["decision_details"]["publicVideo"] == False
        assert result["decision_details"]["contentAgainstBriefCheck"] == [None, None]
        assert result["met_brief_ids"] == []


# Test ECO_MODE disabled with early return flag set
@patch('bitcast.validator.socials.youtube.youtube_evaluation.ECO_MODE', False)
@patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_privacy', Mocks.mock_check_video_privacy_fail)
def test_eco_mode_disabled_continues_despite_early_return():
    """Test that when ECO_MODE is disabled, the function continues execution through all checks."""
    # Setup
    video_id = "test_video_1"
    briefs = [{"id": "brief1"}, {"id": "brief2"}]
    video_data = {
        "bitcastVideoId": video_id,
        "privacyStatus": "private",  # This should fail the privacy check
    }
    video_analytics = {"averageViewPercentage": YT_MIN_VIDEO_RETENTION + 5}
    
    # The key difference with ECO_MODE is that we continue through all checks
    # even after a failure, but all_checks_passed will be False
    with patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_publish_date') as mock_publish_date, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_retention') as mock_retention, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_manual_captions') as mock_captions, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.get_video_transcript') as mock_transcript, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_prompt_injection') as mock_prompt_injection, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.evaluate_content_against_briefs') as mock_evaluate:
        
        # Call the function
        result = vet_video(video_id, briefs, video_data, video_analytics)
        
        # With ECO_MODE disabled, we continue through all checks
        mock_publish_date.assert_called_once()
        mock_retention.assert_called_once()
        mock_captions.assert_called_once()
        mock_transcript.assert_called_once()
        mock_prompt_injection.assert_called_once()
        mock_evaluate.assert_not_called()  # This is still not called because all_checks_passed is False
        
        # Verify result contains expected values
        assert "decision_details" in result
        assert result["decision_details"]["video_vet_result"] == False
        assert result["decision_details"]["publicVideo"] == False
        assert result["decision_details"]["contentAgainstBriefCheck"] == [False, False]
        assert result["met_brief_ids"] == []
        
        # The main difference with ECO_MODE disabled is that the function continues
        # through all checks but still sets all_checks_passed to False
        assert "anyBriefMatched" in result["decision_details"]
        assert result["decision_details"]["anyBriefMatched"] == False


# Test early return at each stage of the pipeline with ECO_MODE enabled
@patch('bitcast.validator.socials.youtube.youtube_evaluation.ECO_MODE', True)
def test_eco_mode_early_return_at_each_stage():
    """Test early return at each stage of the validation pipeline with ECO_MODE enabled."""
    video_id = "test_video_1"
    briefs = [{"id": "brief1"}]
    video_data = {"bitcastVideoId": video_id}
    video_analytics = {"averageViewPercentage": YT_MIN_VIDEO_RETENTION + 5}
    
    # Test 1: Fail at privacy check
    with patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_privacy', 
               return_value=False), \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_publish_date') as mock_publish_date, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.evaluate_content_against_briefs') as mock_evaluate:
        
        result = vet_video(video_id, briefs, video_data, video_analytics)
        mock_publish_date.assert_not_called()
        mock_evaluate.assert_not_called()
    
    # Test 2: Pass privacy check, fail at publish date
    with patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_privacy', 
               return_value=True), \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_publish_date', 
               return_value=False), \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_retention') as mock_retention, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.evaluate_content_against_briefs') as mock_evaluate:
        
        result = vet_video(video_id, briefs, video_data, video_analytics)
        mock_retention.assert_not_called()
        mock_evaluate.assert_not_called()
    
    # Test 3: Pass privacy and publish date, fail at retention
    with patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_privacy', 
               return_value=True), \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_publish_date', 
               return_value=True), \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_retention', 
               return_value=False), \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_manual_captions') as mock_captions, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.evaluate_content_against_briefs') as mock_evaluate:
        
        result = vet_video(video_id, briefs, video_data, video_analytics)
        mock_captions.assert_not_called()
        mock_evaluate.assert_not_called()
    
    # Test 4: Pass through retention, fail at manual captions
    with patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_privacy', 
               return_value=True), \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_publish_date', 
               return_value=True), \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_retention', 
               return_value=True), \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_manual_captions', 
               return_value=False), \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.get_video_transcript') as mock_transcript, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.evaluate_content_against_briefs') as mock_evaluate:
        
        result = vet_video(video_id, briefs, video_data, video_analytics)
        mock_transcript.assert_not_called()
        mock_evaluate.assert_not_called()


# Test full pipeline execution with ECO_MODE disabled
@patch('bitcast.validator.socials.youtube.youtube_evaluation.ECO_MODE', False)
def test_eco_mode_disabled_full_pipeline():
    """Test the full validation pipeline executes with ECO_MODE disabled."""
    video_id = "test_video_1"
    briefs = [{"id": "brief1"}]
    video_data = {"bitcastVideoId": video_id}
    video_analytics = {"averageViewPercentage": YT_MIN_VIDEO_RETENTION + 5}
    
    # Set up all checks to pass
    with patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_privacy', 
               return_value=True) as mock_privacy, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_publish_date', 
               return_value=True) as mock_publish_date, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_retention', 
               return_value=True) as mock_retention, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_manual_captions', 
               return_value=True) as mock_captions, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.get_video_transcript', 
               return_value="Mock transcript") as mock_transcript, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_prompt_injection', 
               return_value=True) as mock_prompt_injection, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.evaluate_content_against_briefs', 
               return_value=(["brief1"], ["Test reasoning"])) as mock_evaluate:
        
        result = vet_video(video_id, briefs, video_data, video_analytics)
        
        # Verify all functions were called
        mock_privacy.assert_called_once()
        mock_publish_date.assert_called_once()
        mock_retention.assert_called_once()
        mock_captions.assert_called_once()
        mock_transcript.assert_called_once()
        mock_prompt_injection.assert_called_once()
        mock_evaluate.assert_called_once()
        
        # Verify successful result
        assert result["met_brief_ids"] == ["brief1"]
        assert result["decision_details"]["video_vet_result"] == True
        assert result["brief_reasonings"] == ["Test reasoning"]


# Test that the early_return flag is properly set when checks fail
@patch('bitcast.validator.socials.youtube.youtube_evaluation.ECO_MODE', True)
def test_early_return_flag():
    """Test that the early_return flag is properly set when checks fail."""
    video_id = "test_video_1"
    briefs = [{"id": "brief1"}]
    video_data = {"bitcastVideoId": video_id}
    video_analytics = {"averageViewPercentage": YT_MIN_VIDEO_RETENTION + 5}
    
    # Set up a spy on check_prompt_injection to verify early_return value
    with patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_privacy', 
               return_value=True), \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_publish_date', 
               return_value=True), \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_retention', 
               return_value=True), \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_manual_captions', 
               return_value=True), \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.get_video_transcript', 
               return_value="Mock transcript"), \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_prompt_injection') as mock_prompt_injection, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.evaluate_content_against_briefs',
               return_value=([], [])) as mock_evaluate:
        
        # Set up mock to capture early_return value by storing it
        def side_effect(video_id, video_data, transcript, decision_details):
            # Store the value of early_return by checking if check_prompt_injection was called
            setattr(mock_prompt_injection, "was_called", True)
            return True
            
        mock_prompt_injection.side_effect = side_effect
        
        result = vet_video(video_id, briefs, video_data, video_analytics)
        
        # Verify prompt injection check was called (indicating early_return was False)
        assert hasattr(mock_prompt_injection, "was_called")
        # Verify the mock was called with the correct return value
        mock_evaluate.assert_called_once()


# Test for multiple failures in different checks with ECO_MODE
@patch('bitcast.validator.socials.youtube.youtube_evaluation.ECO_MODE', True)
def test_eco_mode_multiple_failures():
    """Test for multiple failures in different checks with ECO_MODE enabled."""
    video_id = "test_video_1"
    briefs = [{"id": "brief1"}]
    video_data = {"bitcastVideoId": video_id}
    video_analytics = {"averageViewPercentage": YT_MIN_VIDEO_RETENTION - 5}  # This would fail retention
    
    # Set up privacy and publish date to pass, but retention to fail
    with patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_privacy', 
               side_effect=Mocks.mock_check_video_privacy), \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_publish_date', 
               side_effect=Mocks.mock_check_video_publish_date), \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_video_retention', 
               return_value=False), \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.check_manual_captions') as mock_captions, \
         patch('bitcast.validator.socials.youtube.youtube_evaluation.evaluate_content_against_briefs') as mock_evaluate:
        
        result = vet_video(video_id, briefs, video_data, video_analytics)
        
        # Verify early exit after retention check fails
        mock_captions.assert_not_called()
        mock_evaluate.assert_not_called()
        
        # Verify result
        assert result["decision_details"]["video_vet_result"] == False
        assert result["decision_details"]["publicVideo"] == True  # This was set by our mock
        assert result["decision_details"]["publishDateCheck"] == True  # This was set by our mock
        assert result["met_brief_ids"] == [] 