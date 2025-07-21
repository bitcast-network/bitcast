"""
YouTube video evaluation module.

This module provides comprehensive video evaluation functionality split into
specialized components for better maintainability and clarity.

Modules:
- validation: Basic video validation checks (privacy, retention, etc.)
- transcript: Transcript fetching and prompt injection detection
- brief_matching: Brief evaluation, prescreening, and priority selection
- orchestration: Main workflow coordination and batch processing
"""

# Main orchestration functions
from .orchestration import (
    get_video_analytics_batch,
    process_video_vetting,
    vet_video,
    vet_videos,
)

# Video validation functions
from .validation import (
    check_manual_captions,
    check_video_privacy,
    check_video_publish_date,
    check_video_retention,
    initialize_decision_details,
)

# Transcript and content safety functions
from .transcript import (
    check_prompt_injection,
    get_video_transcript,
)

# Brief matching and evaluation functions
from .brief_matching import (
    check_brief_unique_identifier,
    evaluate_content_against_briefs,
    map_brief_results_to_original_order,
    prescreen_briefs_for_video,
    select_highest_priority_brief,
)

# Import functions that tests may need to patch
from bitcast.validator.clients.OpenaiClient import evaluate_content_against_brief, check_for_prompt_injection
from bitcast.validator.platforms.youtube.utils import state
from bitcast.validator.platforms.youtube.api.video import get_video_analytics, get_video_data_batch

__all__ = [
    # Main orchestration (most commonly used)
    "vet_videos",
    "vet_video", 
    "process_video_vetting",
    "get_video_analytics_batch",
    
    # Video validation
    "initialize_decision_details",
    "check_video_privacy",
    "check_video_publish_date", 
    "check_video_retention",
    "check_manual_captions",
    
    # Transcript handling
    "get_video_transcript",
    "check_prompt_injection",
    
    # Brief matching
    "check_brief_unique_identifier",
    "prescreen_briefs_for_video",
    "evaluate_content_against_briefs",
    "select_highest_priority_brief",
    "map_brief_results_to_original_order",
] 