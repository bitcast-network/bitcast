"""
DEPRECATED: This module is being replaced by the evaluation sub-modules.

This file now imports from the new evaluation modules for backwards compatibility.
All new code should import directly from bitcast.validator.socials.youtube.evaluation.
"""

# Import all functions from the new evaluation modules
from bitcast.validator.socials.youtube.evaluation import (
    # Channel evaluation
    vet_channel,
    calculate_channel_age,
    check_channel_criteria,
    
    # Video evaluation
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
    evaluate_content_against_briefs,
    
    # Scoring
    calculate_video_score,
    calculate_blacklisted_ext_url_proportion,
    get_scorable_minutes
)

# Re-export all functions for backwards compatibility
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
    'calculate_blacklisted_ext_url_proportion',
    'get_scorable_minutes'
] 