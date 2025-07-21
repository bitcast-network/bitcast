"""
Base cache class for YouTube-specific caching needs.

This module provides a base cache implementation following the pattern
established in validator/utils for consistent cache management.
"""

from abc import ABC, abstractmethod
import atexit
import os
from threading import Lock

from diskcache import Cache


class BaseCache(ABC):
    """
    Abstract base class for cache implementations.
    
    Provides common cache management patterns including thread-safe access,
    automatic cleanup, and consistent initialization.
    """
    
    _cache: Cache = None
    _lock = Lock()
    
    @classmethod
    @abstractmethod
    def get_cache_dir(cls) -> str:
        """Return the cache directory path for this cache implementation."""
    
    @classmethod
    def initialize_cache(cls) -> None:
        """Initialize the cache if it hasn't been initialized yet."""
        if cls._cache is None:
            cache_dir = cls.get_cache_dir()
            os.makedirs(cache_dir, exist_ok=True)
            cls._cache = Cache(
                directory=cache_dir,
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