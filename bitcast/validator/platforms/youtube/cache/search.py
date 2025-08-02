"""
YouTube search cache implementation.

This module provides caching for YouTube search API results to reduce
expensive API calls and improve performance.
"""

import atexit
import os
from threading import Lock

from diskcache import Cache

from bitcast.validator.utils.config import CACHE_DIRS


class YouTubeSearchCache:
    """
    Cache for YouTube search API results.
    
    This cache is used to store expensive YouTube search API results (which cost
    100 credits per call) to avoid repeated API calls for the same search queries.
    Cache entries expire after 12 hours to ensure data freshness.
    """
    
    _instance = None
    _lock = Lock()
    _cache: Cache = None
    _cache_dir = CACHE_DIRS["youtube_search"]

    @classmethod
    def initialize_cache(cls) -> None:
        """Initialize the cache if it hasn't been initialized yet."""
        if cls._cache is None:
            os.makedirs(cls._cache_dir, exist_ok=True)
            cls._cache = Cache(
                directory=cls._cache_dir,
                size_limit=1e8,  # 100MB
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
YouTubeSearchCache.initialize_cache() 