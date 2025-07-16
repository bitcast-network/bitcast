"""
YouTube evaluation module.

This module provides functions for evaluating YouTube channels and videos
against various criteria and calculating scores.
"""

# Channel evaluation functions
from .channel import (
    vet_channel,
    calculate_channel_age,
    check_channel_criteria
)

# Video evaluation functions  
from .video import (
    vet_videos,
    vet_video,
    process_video_vetting,
    get_video_analytics_batch,
    initialize_decision_details,
    check_video_privacy,
    check_video_publish_date,
    check_video_retention,
    check_manual_captions,
    get_video_transcript,
    check_prompt_injection,
    evaluate_content_against_briefs
)

# Scoring functions
from .scoring import (
    calculate_video_score
)

__all__ = [
    # Channel evaluation
    'vet_channel',
    'calculate_channel_age', 
    'check_channel_criteria',
    
    # Video evaluation
    'vet_videos',
    'vet_video',
    'process_video_vetting',
    'get_video_analytics_batch',
    'initialize_decision_details',
    'check_video_privacy',
    'check_video_publish_date',
    'check_video_retention',
    'check_manual_captions',
    'get_video_transcript',
    'check_prompt_injection',
    'evaluate_content_against_briefs',
    
    # Scoring
    'calculate_video_score',
] 