import requests
import bittensor as bt
from datetime import datetime, timezone, timedelta
from diskcache import Cache
import os
from threading import Lock
import atexit
from bitcast.validator.utils.config import BITCAST_BRIEFS_ENDPOINT, YT_REWARD_DELAY, YT_SCORING_WINDOW, CACHE_DIRS
from bitcast.validator.utils.error_handling import log_and_raise_api_error

class BriefsCache:
    _instance = None
    _lock = Lock()
    _cache: Cache = None
    _cache_dir = CACHE_DIRS["briefs"]

    @classmethod
    def initialize_cache(cls) -> None:
        """Initialize the cache if it hasn't been initialized yet."""
        if cls._cache is None:
            os.makedirs(cls._cache_dir, exist_ok=True)
            cls._cache = Cache(
                directory=cls._cache_dir,
                size_limit=1e9,  # 1GB
                disk_min_file_size=0,
                disk_pickle_protocol=4,
            )
            # Register cleanup on program exit
            atexit.register(cls.cleanup)

    @classmethod
    def cleanup(cls) -> None:
        """Clean up resources."""
        if cls._cache is not None:
            with cls._lock:
                if cls._cache is not None:
                    cls._cache.close()
                    cls._cache = None

    @classmethod
    def get_cache(cls) -> Cache:
        """Thread-safe cache access."""
        if cls._cache is None:
            cls.initialize_cache()
        return cls._cache

    def __del__(self):
        """Ensure cleanup on object destruction."""
        self.cleanup()

# Initialize cache
BriefsCache.initialize_cache()

def get_briefs(all: bool = False):
    """
    Fetches the briefs from the server.

    :param all: If True, returns all briefs without filtering;
                if False, only returns briefs where the current UTC date is between start and end dates (inclusive),
                or where the end date is within YT_REWARD_DELAY days of the current date.
    :return: List of brief objects
    """
    cache = BriefsCache.get_cache()
    cache_key = f"briefs_{all}"
    
    try:
        # Always try to fetch from API first
        response = requests.get(BITCAST_BRIEFS_ENDPOINT, timeout=30)
        response.raise_for_status()
        
        # Validate JSON response
        try:
            briefs_data = response.json()
        except ValueError as e:
            raise ValueError(f"Invalid JSON response from briefs endpoint: {e}")
        
        # Handle response structure - could be dict with "items" key or list directly
        if isinstance(briefs_data, list):
            briefs_list = briefs_data
        elif isinstance(briefs_data, dict):
            briefs_list = briefs_data.get("items") or briefs_data.get("briefs") or []
        else:
            bt.logging.warning(f"Unexpected response type from briefs endpoint: {type(briefs_data)}")
            briefs_list = []
        
        bt.logging.info(f"Fetched {len(briefs_list)} briefs.")

        filtered_briefs = []
        if not all:
            current_date = datetime.now(timezone.utc).date()
            
            for brief in briefs_list:
                try:
                    # Validate brief structure
                    if not isinstance(brief, dict):
                        bt.logging.warning(f"Skipping invalid brief entry (not a dict): {brief}")
                        continue
                    
                    # Use .get() with validation for required fields
                    start_date_str = brief.get("start_date")
                    end_date_str = brief.get("end_date")
                    
                    if not start_date_str or not end_date_str:
                        bt.logging.warning(f"Skipping brief {brief.get('id', 'unknown')}: missing start_date or end_date")
                        continue
                    
                    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
                    # Apply new window: start_date + YT_REWARD_DELAY, end_date + YT_SCORING_WINDOW + YT_REWARD_DELAY
                    start_window = start_date + timedelta(days=YT_REWARD_DELAY)
                    end_window = end_date + timedelta(days=YT_SCORING_WINDOW + YT_REWARD_DELAY)
                    
                    if start_window <= current_date <= end_window:
                        filtered_briefs.append(brief)
                except (ValueError, KeyError) as e:
                    bt.logging.error(f"Error parsing dates for brief {brief.get('id', 'unknown')}: {e}")
                except Exception as e:
                    bt.logging.error(f"Unexpected error processing brief {brief.get('id', 'unknown')}: {e}")
            
            if not filtered_briefs:
                bt.logging.info("No briefs have an active date range or are within the reward delay period.")
        else:
            filtered_briefs = briefs_list

        # Store the successful API response in cache
        cache.set(cache_key, filtered_briefs)
        return filtered_briefs

    except requests.exceptions.RequestException as e:
        # Try to return cached data if available
        cached_briefs = cache.get(cache_key)
        if cached_briefs is not None:
            bt.logging.warning("Using cached briefs due to API error")
            return cached_briefs
        
        # No cached data available - this is a real error
        log_and_raise_api_error(
            error=e,
            endpoint=BITCAST_BRIEFS_ENDPOINT,
            context="Content briefs fetch"
        )