"""
Channel evaluation logic for YouTube validation.

This module contains functions for vetting YouTube channels against criteria
such as subscriber count, channel age, retention rates, and blacklist status.
"""

import bittensor as bt
from datetime import datetime, timedelta
from bitcast.validator.utils.config import (
    YT_MIN_SUBS,
    YT_MAX_SUBS,
    YT_MIN_CHANNEL_AGE,
    YT_MIN_CHANNEL_RETENTION,
    YT_MIN_MINS_WATCHED,
    YT_LOOKBACK
)
from bitcast.validator.utils.blacklist import is_blacklisted


def vet_channel(channel_data, channel_analytics):
    """
    Vet a YouTube channel against all validation criteria.
    
    Args:
        channel_data (dict): Channel metadata including subscriber count and creation date
        channel_analytics (dict): Channel analytics data including retention and minutes watched
        
    Returns:
        tuple: (vet_result: bool, blacklisted: bool)
    """
    bt.logging.info(f"Checking channel")

    # Check if channel is blacklisted
    if is_blacklisted(channel_data["bitcastChannelId"]):
        bt.logging.warning(f"Channel is blacklisted: {channel_data['bitcastChannelId']}")
        return False, True  # Return (vet_result, blacklisted)

    # Calculate channel age
    channel_age_days = calculate_channel_age(channel_data)
    
    # Check if channel meets the criteria
    criteria_met = check_channel_criteria(channel_data, channel_analytics, channel_age_days)
    
    if criteria_met:
        bt.logging.info(f"Channel Evaluation Passed")
        return True, False  # Return (vet_result, blacklisted)
    else:
        bt.logging.info(f"Channel Evaluation Failed")
        return False, False  # Return (vet_result, blacklisted)


def calculate_channel_age(channel_data):
    """
    Calculate the age of the channel in days.
    
    Args:
        channel_data (dict): Channel metadata containing channel_start date
        
    Returns:
        int: Channel age in days
    """
    # youtube returns inconsistent date formats
    try:
        channel_start_date = datetime.strptime(channel_data["channel_start"], '%Y-%m-%dT%H:%M:%S.%fZ')
    except ValueError:
        channel_start_date = datetime.strptime(channel_data["channel_start"], '%Y-%m-%dT%H:%M:%SZ')

    return (datetime.now() - channel_start_date).days


def check_channel_criteria(channel_data, channel_analytics, channel_age_days):
    """
    Check if the channel meets all the required criteria.
    
    Args:
        channel_data (dict): Channel metadata including subscriber count
        channel_analytics (dict): Channel analytics including retention and minutes watched
        channel_age_days (int): Age of the channel in days
        
    Returns:
        bool: True if all criteria are met, False otherwise
    """
    criteria_met = True

    if channel_age_days < YT_MIN_CHANNEL_AGE:
        bt.logging.warning(f"Channel age check failed: {channel_data['bitcastChannelId']}. {channel_age_days} < {YT_MIN_CHANNEL_AGE}")
        criteria_met = False

    if int(channel_data["subCount"]) < YT_MIN_SUBS:
        bt.logging.warning(f"Subscriber count check failed: {channel_data['bitcastChannelId']}. {channel_data['subCount']} < {YT_MIN_SUBS}.")
        criteria_met = False

    if int(channel_data["subCount"]) > YT_MAX_SUBS:
        bt.logging.warning(f"Subscriber count check failed: {channel_data['bitcastChannelId']}. {channel_data['subCount']} > {YT_MAX_SUBS}.")
        criteria_met = False

    if float(channel_analytics["averageViewPercentage"]) < YT_MIN_CHANNEL_RETENTION:
        bt.logging.warning(f"Avg retention check failed (last {YT_LOOKBACK} days): {channel_data['bitcastChannelId']}. {channel_analytics['averageViewPercentage']} < {YT_MIN_CHANNEL_RETENTION}%.")
        criteria_met = False
        
    if float(channel_analytics["estimatedMinutesWatched"]) < YT_MIN_MINS_WATCHED:
        bt.logging.warning(f"Minutes watched check failed (last {YT_LOOKBACK} days): {channel_data['bitcastChannelId']}. {channel_analytics['estimatedMinutesWatched']} < {YT_MIN_MINS_WATCHED}.")
        criteria_met = False

    return criteria_met 