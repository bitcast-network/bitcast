"""
YouTube evaluation module.

This module provides functions for evaluating YouTube channels and videos
against various criteria and calculating scores.
"""

# Channel evaluation functions
from .channel import calculate_channel_age, check_channel_criteria, vet_channel

# Dual scoring utilities
from .dual_scoring import (
    calculate_dual_score,
    calculate_global_ratio,
    get_cached_ratio,
    update_cached_ratio,
)

# Score capping
from .score_cap import (
    calculate_median_from_analytics,
    get_cap_period_dates,
    pad_missing_days_with_zeros,
)

# Scoring functions
from .scoring import calculate_video_score

# Video evaluation functions  
from .video import (
    check_manual_captions,
    check_prompt_injection,
    check_video_privacy,
    check_video_publish_date,
    check_video_retention,
    evaluate_content_against_briefs,
    get_video_analytics_batch,
    get_video_transcript,
    initialize_decision_details,
    process_video_vetting,
    vet_video,
    vet_videos,
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
    
    # Dual scoring utilities
    'calculate_dual_score',
    'calculate_global_ratio',
    'update_cached_ratio',
    'get_cached_ratio',
    
    # Score capping
    'get_cap_period_dates',
    'pad_missing_days_with_zeros',
    'calculate_median_from_analytics',
] 