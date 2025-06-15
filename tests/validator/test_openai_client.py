import pytest
from unittest.mock import patch, MagicMock
import bittensor as bt

from bitcast.validator.clients.OpenaiClient import (
    evaluate_content_against_brief,
    _get_prompt_version
)
from bitcast.validator.clients.prompts import (
    generate_brief_evaluation_prompt_v1,
    generate_brief_evaluation_prompt_v2,
    generate_brief_evaluation_prompt
)


class TestBriefVersioning:
    """Test suite for brief versioning functionality."""

    def test_get_prompt_version_defaults_to_v1(self):
        """Test that briefs without prompt_version default to version 1."""
        brief_without_version = {"id": "test1", "brief": "Test brief"}
        brief_with_v1 = {"id": "test2", "brief": "Test brief", "prompt_version": 1}
        brief_with_v2 = {"id": "test3", "brief": "Test brief", "prompt_version": 2}
        
        assert _get_prompt_version(brief_without_version) == 1
        assert _get_prompt_version(brief_with_v1) == 1
        assert _get_prompt_version(brief_with_v2) == 2

    def test_generate_prompt_v1_format(self):
        """Test that v1 prompt generation produces the original format."""
        brief = {"brief": "Create a video about cats"}
        duration = "5:30"
        description = "A video about cats"
        transcript = "In this video, we talk about cats..."
        
        prompt = generate_brief_evaluation_prompt_v1(brief, duration, description, transcript)
        
        # Check for v1 specific elements
        assert "///// BRIEF /////" in prompt
        assert "///// VIDEO DETAILS /////" in prompt
        assert "///// YOUR TASK /////" in prompt
        assert "You are evaluating a video and its content" in prompt
        assert "Be thorough and objective." in prompt
        
        # Ensure v2 specific elements are NOT present
        assert "///// SPONSOR BRIEF /////" not in prompt
        assert "**Key definitions**" not in prompt
        assert "**Evaluation checklist**" not in prompt

    def test_generate_prompt_v2_format(self):
        """Test that v2 prompt generation produces the new format."""
        brief = {"brief": "Create a video about cats"}
        duration = "5:30"
        description = "A video about cats"
        transcript = "In this video, we talk about cats..."
        
        prompt = generate_brief_evaluation_prompt_v2(brief, duration, description, transcript)
        
        # Check for v2 specific elements
        assert "///// SPONSOR BRIEF /////" in prompt
        assert "**Step-by-step instructions**" in prompt
        assert "**Response format (exactly):**" in prompt
        assert "## Requirement-by-Requirement" in prompt
        assert "## Additional Gates" in prompt
        assert "## Verdict" in prompt
        assert "When in doubt, choose **NO**." in prompt

        # Ensure v1 specific elements are NOT present
        assert "///// BRIEF /////" not in prompt
        assert "You are evaluating a video and its content" not in prompt
        assert "Be thorough and objective." not in prompt

    @patch('bitcast.validator.clients.OpenaiClient._make_openai_request')
    @patch('bitcast.validator.clients.OpenaiClient.OpenaiClient.get_cache')
    def test_evaluate_content_against_brief_v1(self, mock_get_cache, mock_openai_request):
        """Test that brief evaluation uses v1 prompt for briefs without prompt_version."""
        # Setup mock
        mock_get_cache.return_value = None
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.parsed.meets_brief = True
        mock_response.choices[0].message.parsed.reasoning = "Test reasoning"
        mock_openai_request.return_value = mock_response
        
        brief = {"id": "brief1", "brief": "Create a video about cats"}
        duration = "5:30"
        description = "A video about cats"
        transcript = "In this video, we talk about cats..."
        
        with patch('bittensor.logging.info') as mock_log:
            meets_brief, reasoning = evaluate_content_against_brief(brief, duration, description, transcript)
            
            # Verify the correct version is logged
            mock_log.assert_called_with("Brief brief1 (v1) met: True ✅")
            
        # Verify the OpenAI request was made with the correct prompt format
        mock_openai_request.assert_called_once()
        call_args = mock_openai_request.call_args[1]
        prompt_content = call_args['messages'][0]['content']
        
        # Check that it's using v1 format
        assert "///// BRIEF /////" in prompt_content
        assert "///// SPONSOR BRIEF /////" not in prompt_content
        
        assert meets_brief == True
        assert reasoning == "Test reasoning"

    @patch('bitcast.validator.clients.OpenaiClient._make_openai_request')
    @patch('bitcast.validator.clients.OpenaiClient.OpenaiClient.get_cache')
    def test_evaluate_content_against_brief_v2(self, mock_get_cache, mock_openai_request):
        """Test that brief evaluation uses v2 prompt for briefs with prompt_version: 2."""
        # Setup mock
        mock_get_cache.return_value = None
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.parsed.meets_brief = False
        mock_response.choices[0].message.parsed.reasoning = "Test reasoning v2"
        mock_openai_request.return_value = mock_response
        
        brief = {"id": "brief2", "brief": "Create a video about dogs", "prompt_version": 2}
        duration = "10:00"
        description = "A video about dogs"
        transcript = "00:00:05 Welcome to my dog video..."
        
        with patch('bittensor.logging.info') as mock_log:
            meets_brief, reasoning = evaluate_content_against_brief(brief, duration, description, transcript)
            
            # Verify the correct version is logged
            mock_log.assert_called_with("Brief brief2 (v2) met: False ❌")
            
        # Verify the OpenAI request was made with the correct prompt format
        mock_openai_request.assert_called_once()
        call_args = mock_openai_request.call_args[1]
        prompt_content = call_args['messages'][0]['content']
        
        # Check that it's using v2 format
        assert "///// SPONSOR BRIEF /////" in prompt_content
        assert "**Step-by-step instructions**" in prompt_content
        assert "**Response format (exactly):**" in prompt_content
        assert "///// BRIEF /////" not in prompt_content
        
        assert meets_brief == False
        assert reasoning == "Test reasoning v2"

    def test_evaluate_content_against_brief_cached_v1(self):
        """Test that cached results include version information in logs for v1."""
        brief = {"id": "brief3", "brief": "Create a video about birds"}
        
        # Mock the cache to simulate a cache hit
        mock_cache_data = {"meets_brief": True, "reasoning": "Cached reasoning"}
        
        with patch('bitcast.validator.clients.OpenaiClient.DISABLE_LLM_CACHING', False), \
             patch('bitcast.validator.clients.OpenaiClient.OpenaiClient.get_cache') as mock_get_cache, \
             patch('bittensor.logging.info') as mock_log:
            
            # Setup cache mock to return our test data
            mock_cache = MagicMock()
            mock_cache.__contains__ = MagicMock(return_value=True)
            mock_cache.__getitem__ = MagicMock(return_value=mock_cache_data)
            mock_cache.set = MagicMock()
            mock_get_cache.return_value = mock_cache
            
            meets_brief, reasoning = evaluate_content_against_brief(brief, "3:00", "Birds", "Chirp chirp")
            
            # Verify the correct version is logged for cached result
            # Should contain the cache indicator
            log_calls = [str(call) for call in mock_log.call_args_list]
            cache_log_found = any("(cache)" in call and "brief3" in call and "(v1)" in call for call in log_calls)
            assert cache_log_found, f"Expected cache log not found. Log calls: {log_calls}"
            
            assert meets_brief == True
            assert reasoning == "Cached reasoning"

    def test_evaluate_content_against_brief_cached_v2(self):
        """Test that cached results include version information in logs for v2."""
        brief = {"id": "brief4", "brief": "Create a video about fish", "prompt_version": 2}
        
        # Mock the cache to simulate a cache hit
        mock_cache_data = {"meets_brief": False, "reasoning": "Cached reasoning v2"}
        
        with patch('bitcast.validator.clients.OpenaiClient.DISABLE_LLM_CACHING', False), \
             patch('bitcast.validator.clients.OpenaiClient.OpenaiClient.get_cache') as mock_get_cache, \
             patch('bittensor.logging.info') as mock_log:
            
            # Setup cache mock to return our test data
            mock_cache = MagicMock()
            mock_cache.__contains__ = MagicMock(return_value=True)
            mock_cache.__getitem__ = MagicMock(return_value=mock_cache_data)
            mock_cache.set = MagicMock()
            mock_get_cache.return_value = mock_cache
            
            meets_brief, reasoning = evaluate_content_against_brief(brief, "7:45", "Fish", "00:00:10 Swimming...")
            
            # Verify the correct version is logged for cached result
            # Should contain the cache indicator
            log_calls = [str(call) for call in mock_log.call_args_list]
            cache_log_found = any("(cache)" in call and "brief4" in call and "(v2)" in call for call in log_calls)
            assert cache_log_found, f"Expected cache log not found. Log calls: {log_calls}"
            
            assert meets_brief == False
            assert reasoning == "Cached reasoning v2"

    def test_backwards_compatibility(self):
        """Test that existing briefs without prompt_version continue to work as before."""
        legacy_brief = {
            "id": "legacy1",
            "brief": "Create a promotional video about our new product",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31"
        }
        
        # Should default to version 1
        version = _get_prompt_version(legacy_brief)
        assert version == 1
        
        # Should generate v1 prompt
        prompt = generate_brief_evaluation_prompt_v1(legacy_brief, "5:00", "Product demo", "This is our product...")
        assert "///// BRIEF /////" in prompt
        assert "You are evaluating a video and its content" in prompt


class TestPromptContentValidation:
    """Test suite to validate prompt content structure."""

    def test_v1_prompt_contains_all_required_sections(self):
        """Test that v1 prompt contains all required sections."""
        brief = {"brief": "Test brief content"}
        prompt = generate_brief_evaluation_prompt_v1(brief, "5:00", "Test description", "Test transcript")
        
        required_sections = [
            "///// BRIEF /////",
            "///// VIDEO DETAILS /////",
            "///// YOUR TASK /////",
            "VIDEO DURATION: 5:00",
            "VIDEO DESCRIPTION: Test description",
            "VIDEO TRANSCRIPT: Test transcript"
        ]
        
        for section in required_sections:
            assert section in prompt, f"Missing section: {section}"

    def test_v2_prompt_contains_all_required_sections(self):
        """Test that v2 prompt contains all required sections and formatting."""
        brief = {"brief": "Test brief content"}
        prompt = generate_brief_evaluation_prompt_v2(brief, "5:00", "Test description", "Test transcript")
        
        required_sections = [
            "///// SPONSOR BRIEF /////",
            "///// VIDEO DETAILS /////",
            "///// YOUR TASK /////",
            "VIDEO DURATION: 5:00",
            "VIDEO DESCRIPTION: Test description",
            "VIDEO TRANSCRIPT (list of dicts with 'start' (s), 'dur' (s), 'text'):",
            "**Step-by-step instructions**",
            "**Response format (exactly):**",
            "## Requirement-by-Requirement",
            "## Additional Gates",
            "## Verdict"
        ]
        
        for section in required_sections:
            assert section in prompt, f"Missing section: {section}"
            
        # Check for key instructional content
        key_instructions = [
            "You are the sponsor's review agent",
            "**Auto-number** each requirement line",
            "**Video-type check**",
            "**Silent content check**"
        ]
        
        for instruction in key_instructions:
            assert instruction in prompt, f"Missing instruction: {instruction}"


class TestUnifiedPromptInterface:
    """Test suite for the unified prompt generation interface."""
    
    def test_generate_brief_evaluation_prompt_defaults_to_v1(self):
        """Test that the unified interface defaults to version 1."""
        brief = {"brief": "Test brief"}
        prompt = generate_brief_evaluation_prompt(brief, "5:00", "desc", "transcript")
        
        # Should generate v1 format by default
        assert "///// BRIEF /////" in prompt
        assert "///// SPONSOR BRIEF /////" not in prompt
    
    def test_generate_brief_evaluation_prompt_v1_explicit(self):
        """Test that the unified interface correctly generates v1 when explicitly requested."""
        brief = {"brief": "Test brief"}
        prompt = generate_brief_evaluation_prompt(brief, "5:00", "desc", "transcript", version=1)
        
        assert "///// BRIEF /////" in prompt
        assert "///// SPONSOR BRIEF /////" not in prompt
        
    def test_generate_brief_evaluation_prompt_v2_explicit(self):
        """Test that the unified interface correctly generates v2 when explicitly requested."""
        brief = {"brief": "Test brief"}
        prompt = generate_brief_evaluation_prompt(brief, "5:00", "desc", "transcript", version=2)
        
        assert "///// SPONSOR BRIEF /////" in prompt
        assert "///// BRIEF /////" not in prompt
        
    def test_generate_brief_evaluation_prompt_unsupported_version(self):
        """Test that unsupported versions raise appropriate errors."""
        brief = {"brief": "Test brief"}
        
        with pytest.raises(ValueError, match="Unsupported prompt version: 99"):
            generate_brief_evaluation_prompt(brief, "5:00", "desc", "transcript", version=99)
            
    def test_prompt_consistency_between_interfaces(self):
        """Test that the unified interface produces the same output as individual functions."""
        brief = {"brief": "Test brief content"}
        duration = "5:00"
        description = "Test description"
        transcript = "Test transcript"
        
        # Test v1 consistency
        v1_direct = generate_brief_evaluation_prompt_v1(brief, duration, description, transcript)
        v1_unified = generate_brief_evaluation_prompt(brief, duration, description, transcript, version=1)
        assert v1_direct == v1_unified
        
        # Test v2 consistency
        v2_direct = generate_brief_evaluation_prompt_v2(brief, duration, description, transcript)
        v2_unified = generate_brief_evaluation_prompt(brief, duration, description, transcript, version=2)
        assert v2_direct == v2_unified 