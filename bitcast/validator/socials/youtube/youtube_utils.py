import bittensor as bt
import requests
import time
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from bitcast.validator.utils.config import TRANSCRIPT_MAX_RETRY, CACHE_DIRS, YOUTUBE_SEARCH_CACHE_EXPIRY, YT_MAX_VIDEOS
import httpx
import hashlib
import asyncio
from tenacity import retry, stop_after_attempt, wait_fixed, RetryError
from googleapiclient.errors import HttpError
import os
import json
import re
from diskcache import Cache
from threading import Lock
import atexit
from .cache.search import YouTubeSearchCache
from .api.channel import _query_multiple_metrics

# Import global state and helper functions from utils modules
from .utils import (
    scored_video_ids,
    data_api_call_count,
    analytics_api_call_count,
    reset_scored_videos,
    is_video_already_scored,
    mark_video_as_scored,
    reset_api_call_counts,
    _format_error
)

# Import video API functions from the new API module
from .api.video import (
    get_all_uploads,
    get_video_data_batch,
    get_video_data,
    get_video_analytics,
    _get_uploads_playlist_id,
    _fallback_via_search
)

# Import transcript API functions from the new API module
from .api.transcript import (
    get_video_transcript,
    _fetch_transcript
)

# Retry configuration for YouTube API calls
YT_API_RETRY_CONFIG = {
    'stop': stop_after_attempt(3),
    'wait': wait_fixed(0.5),
    'reraise': True
}

# Channel Analytics Functions have been moved to api/channel.py
# Video Management and Analytics Functions have been moved to api/video.py
# Transcript Functions have been moved to api/transcript.py

# _format_error function now imported from utils.helpers