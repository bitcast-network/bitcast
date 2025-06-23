"""
Brief filtering utilities for YouTube evaluation.

This module contains functions for filtering briefs based on channel criteria
such as subscriber count ranges.
"""

import bittensor as bt


def check_subscriber_range(sub_count, subs_range):
    """
    Check if a subscriber count falls within a given range.
    Handles null values in the range:
    - If both values are null, returns True (no filtering)
    - If first value is null, checks if count is less than or equal to max
    - If second value is null, checks if count is greater than or equal to min
    - If neither is null, checks if count is within range (inclusive)
    
    Args:
        sub_count (int): Channel's subscriber count
        subs_range (list): List of [min_subs, max_subs] where either can be null
        
    Returns:
        bool: True if subscriber count is within range, False otherwise
    """
    min_subs, max_subs = subs_range
    
    # If both values are null, no filtering
    if min_subs is None and max_subs is None:
        return True
        
    # If first value is null, check if count is less than or equal to max
    if min_subs is None:
        return sub_count <= max_subs
        
    # If second value is null, check if count is greater than or equal to min
    if max_subs is None:
        return sub_count >= min_subs
        
    # If neither is null, check if count is within range (inclusive)
    return min_subs <= sub_count <= max_subs


def channel_briefs_filter(briefs, channel_analytics):
    """
    Filter briefs based on the channel's subscriber count.
    Only returns briefs where the channel's subscriber count falls within the brief's subs_range (inclusive).
    
    Args:
        briefs (List[dict]): List of briefs to filter
        channel_analytics (dict): Channel analytics data containing subscriber count
        
    Returns:
        List[dict]: Filtered list of briefs
    """
    if not briefs:
        return []
        
    # Get channel's subscriber count
    sub_count = int(channel_analytics.get("subCount", 0))
    
    # Filter briefs based on subscriber count range
    filtered_briefs = []
    for brief in briefs:
        # If brief doesn't have a subs_range, include it
        if "subs_range" not in brief:
            filtered_briefs.append(brief)
            continue
            
        # Check if channel's subscriber count falls within the range
        if check_subscriber_range(sub_count, brief["subs_range"]):
            filtered_briefs.append(brief)
        else:
            min_subs, max_subs = brief["subs_range"]
            range_str = f"[{min_subs or 'null'}, {max_subs or 'null'}]"
            bt.logging.info(f"Channel subscriber count {sub_count} outside brief {brief['id']} range {range_str}")
            
    return filtered_briefs 