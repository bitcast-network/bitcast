"""
Historical video registry for maintaining data collection on previously matched videos.

This module tracks videos that have matched briefs and automatically includes them
in future data collection cycles (up to 90 days) for historical trend analysis,
even after they no longer match active briefs.

Storage Format: JSON Lines (.jsonl)
- One JSON object per line
- Format: {"video_id": str, "bitcast_video_id": str, "channel_id": str, 
           "bitcast_channel_id": str, "date_first_matched": str, "brief_id": str}
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import List, Dict, Any
import bittensor as bt

# Cross-platform file locking using threading lock
# Note: fcntl is Unix-only, so we use a threading lock for cross-platform compatibility
_file_lock = Lock()

from bitcast.validator.utils.config import ECO_MODE

# Storage location for historical videos registry
# Path: bitcast/validator/data/historical_videos.jsonl
HISTORICAL_VIDEOS_PATH = Path(__file__).parent.parent.parent.parent / "data" / "historical_videos.jsonl"

# In-memory cache of recorded entries to prevent duplicates
_recorded_entries = None


def _load_recorded_entries():
    """Load existing entries into memory cache (called once on first write)."""
    global _recorded_entries
    if _recorded_entries is not None:
        return
    
    _recorded_entries = set()
    if not HISTORICAL_VIDEOS_PATH.exists():
        return
    
    try:
        with open(HISTORICAL_VIDEOS_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        _recorded_entries.add((entry['video_id'], entry['channel_id']))
                    except (json.JSONDecodeError, KeyError):
                        continue
    except Exception as e:
        bt.logging.debug(f"Could not load recorded entries cache: {e}")


def _ensure_file_exists():
    """Ensure the historical videos file and parent directory exist."""
    HISTORICAL_VIDEOS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not HISTORICAL_VIDEOS_PATH.exists():
        HISTORICAL_VIDEOS_PATH.touch()


def record_video_match(
    video_id: str,
    bitcast_video_id: str,
    channel_id: str,
    bitcast_channel_id: str,
    brief_id: str
) -> None:
    """
    Record that a video matched a brief (prevents duplicates using in-memory cache).
    
    Args:
        video_id: YouTube video ID (real ID)
        bitcast_video_id: Bitcast video ID (possibly hashed for privacy)
        channel_id: YouTube channel ID (real ID, not hashed)
        bitcast_channel_id: Bitcast channel ID (possibly hashed for privacy)
        brief_id: Brief ID that was matched
    """
    try:
        _ensure_file_exists()
        _load_recorded_entries()
        
        # Check if already recorded
        entry_key = (video_id, channel_id)
        if entry_key in _recorded_entries:
            return
        
        today = datetime.now().strftime('%Y-%m-%d')
        entry = {
            "video_id": video_id,
            "bitcast_video_id": bitcast_video_id,
            "channel_id": channel_id,
            "bitcast_channel_id": bitcast_channel_id,
            "date_first_matched": today,
            "brief_id": brief_id
        }
        
        # Thread-safe append with cross-platform lock
        # Using threading lock for cross-platform compatibility (works on Windows and Unix)
        with _file_lock:
            with open(HISTORICAL_VIDEOS_PATH, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')
                f.flush()  # Ensure data is written
            _recorded_entries.add(entry_key)
                
    except Exception as e:
        bt.logging.warning(f"Failed to record historical video match: {e}")


def get_historical_videos(channel_id: str, max_age_days: int = 90) -> List[str]:
    """
    Get list of historical video IDs for a channel within the date range.
    
    Args:
        channel_id: YouTube channel ID to query
        max_age_days: Maximum age of matches to include (default: 90 days)
        
    Returns:
        List of deduplicated video IDs
    """
    if not HISTORICAL_VIDEOS_PATH.exists():
        return []
    
    try:
        cutoff_date = (datetime.now() - timedelta(days=max_age_days)).strftime('%Y-%m-%d')
        video_ids = set()
        
        with open(HISTORICAL_VIDEOS_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    if entry['channel_id'] == channel_id and entry['date_first_matched'] >= cutoff_date:
                        video_ids.add(entry['video_id'])
                except (json.JSONDecodeError, KeyError):
                    continue
        
        video_list = list(video_ids)
        if video_list:
            bt.logging.info(f"Found {len(video_list)} historical videos (last {max_age_days} days)")
        
        return video_list
        
    except Exception as e:
        bt.logging.warning(f"Failed to retrieve historical videos: {e}")
        return []


def add_historical_videos_to_list(video_ids: List[str], result: Dict[str, Any]) -> List[str]:
    """
    Add historical videos to processing list (only if not ECO_MODE).
    
    Returns combined list of recent + historical videos with deduplication.
    
    Args:
        video_ids: List of recent video IDs from channel uploads
        result: Result dictionary containing channel details
        
    Returns:
        Combined list of video IDs (deduplicated)
    """
    if ECO_MODE:
        return video_ids
    
    try:
        channel_id = result["yt_account"]["details"].get("id")
        if not channel_id:
            return video_ids
        
        historical_video_ids = get_historical_videos(channel_id, max_age_days=90)
        current_video_ids_set = set(video_ids)
        additional_historical = [vid for vid in historical_video_ids if vid not in current_video_ids_set]
        
        if additional_historical:
            bt.logging.info(f"Including {len(additional_historical)} historical videos for data collection")
            return video_ids + additional_historical
        
        return video_ids
        
    except Exception as e:
        bt.logging.debug(f"Could not retrieve historical videos: {e}")
        return video_ids


def record_matching_video(
    video_id: str,
    video_data: Dict[str, Any],
    matching_brief_ids: List[str],
    result: Dict[str, Any]
) -> None:
    """
    Record that a video matched briefs (only if not ECO_MODE).
    
    Args:
        video_id: YouTube video ID
        video_data: Video data dictionary
        matching_brief_ids: List of brief IDs that matched
        result: Result dictionary containing channel details
    """
    if ECO_MODE:
        return
    
    try:
        channel_id = result["yt_account"]["details"].get("id")
        bitcast_channel_id = result["yt_account"]["details"].get("bitcastChannelId")
        bitcast_video_id = video_data.get("bitcastVideoId", video_id)
        
        if not (channel_id and bitcast_channel_id):
            return
        
        for brief_id in matching_brief_ids:
            record_video_match(
                video_id=video_id,
                bitcast_video_id=bitcast_video_id,
                channel_id=channel_id,
                bitcast_channel_id=bitcast_channel_id,
                brief_id=brief_id
            )
    except Exception as e:
        bt.logging.debug(f"Could not record historical video match: {e}")

