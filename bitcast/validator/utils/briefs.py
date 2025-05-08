import requests
import bittensor as bt
from datetime import datetime, timezone, timedelta
from diskcache import Cache
import os
from threading import Lock
import atexit
from bitcast.validator.utils.config import BITCAST_BRIEFS_ENDPOINT, YT_REWARD_DELAY, CACHE_DIRS

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
        response = requests.get(BITCAST_BRIEFS_ENDPOINT)
        response.raise_for_status()
        briefs_data = response.json()
        
        # Handle both "items" and "briefs" keys in the response
        briefs_list = briefs_data.get("items") or briefs_data.get("briefs") or []
        bt.logging.info(f"Fetched {len(briefs_list)} briefs.")

        filtered_briefs = []
        if not all:
            current_date = datetime.now(timezone.utc).date()
            
            for brief in briefs_list:
                try:
                    start_date = datetime.strptime(brief["start_date"], "%Y-%m-%d").date()
                    end_date = datetime.strptime(brief["end_date"], "%Y-%m-%d").date()
                    start_date_with_delay = start_date + timedelta(days=YT_REWARD_DELAY)
                    end_date_with_delay = end_date + timedelta(days=YT_REWARD_DELAY)
                    
                    if start_date_with_delay <= current_date <= end_date_with_delay:
                        filtered_briefs.append(brief)
                except Exception as e:
                    bt.logging.error(f"Error parsing dates for brief {brief.get('id', 'unknown')}: {e}")
            
            if not filtered_briefs:
                bt.logging.info("No briefs have an active date range or are within the reward delay period.")
        else:
            filtered_briefs = briefs_list

        # Store the successful API response in cache
        cache.set(cache_key, filtered_briefs)
        return filtered_briefs

    except requests.exceptions.RequestException as e:
        bt.logging.error(f"Error fetching briefs: {e}")
        # Try to return cached data if available
        cached_briefs = cache.get(cache_key)
        if cached_briefs is not None:
            bt.logging.warning("Using cached briefs due to API error")
            return cached_briefs
        bt.logging.error("No cached briefs available")
        return []