import requests
import bittensor as bt
from diskcache import Cache
import os
from threading import Lock
import atexit
from bitcast.validator.utils.config import BITCAST_BLACKLIST_ENDPOINT, CACHE_DIRS

# Cache expiration time in seconds (10 minutes)
BLACKLIST_CACHE_EXPIRY = 10 * 60

class BlacklistCache:
    _instance = None
    _lock = Lock()
    _cache: Cache = None
    _cache_dir = CACHE_DIRS["blacklist"]  # Using dedicated blacklist cache directory

    @classmethod
    def initialize_cache(cls) -> None:
        """Initialize the cache if it hasn't been initialized yet."""
        if cls._cache is None:
            os.makedirs(cls._cache_dir, exist_ok=True)
            cls._cache = Cache(
                directory=cls._cache_dir,
                size_limit=1e6,  # 1MB
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
BlacklistCache.initialize_cache()

def get_blacklist() -> list[str]:
    """
    Fetches the blacklist from the server and returns it as a list of IDs.
    Uses caching to store the results and reduce API calls.
    Cache expires after 10 minutes.

    :return: List of blacklisted IDs
    """
    cache = BlacklistCache.get_cache()
    cache_key = "blacklist"
    
    # First try to get from cache
    cached_blacklist = cache.get(cache_key)
    if cached_blacklist is not None:
        bt.logging.info("Using cached blacklist data")
        return cached_blacklist
    
    try:
        # If no cache, fetch from API
        response = requests.get(BITCAST_BLACKLIST_ENDPOINT)
        response.raise_for_status()
        blacklist_data = response.json()
        
        # Extract items from response
        blacklist_items = blacklist_data.get("items", [])
        bt.logging.info(f"Fetched {len(blacklist_items)} blacklisted items from API.")

        # Store the successful API response in cache with 10-minute expiration
        cache.set(cache_key, blacklist_items, expire=BLACKLIST_CACHE_EXPIRY)
        return blacklist_items

    except requests.exceptions.RequestException as e:
        bt.logging.error(f"Error fetching blacklist: {e}")
        # Try to return cached data if available (even if expired)
        cached_blacklist = cache.get(cache_key)
        if cached_blacklist is not None:
            bt.logging.warning("Using cached blacklist due to API error")
            return cached_blacklist
        bt.logging.error("No cached blacklist available")
        return []

def is_blacklisted(id: str) -> bool:
    """
    Checks if a given ID is in the blacklist.
    Uses the cached blacklist if available, otherwise fetches from the API.

    :param id: The ID to check against the blacklist
    :return: True if the ID is blacklisted, False otherwise
    """
    blacklist = get_blacklist()
    return id in blacklist
