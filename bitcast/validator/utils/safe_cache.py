"""
Thread-safe cache operations to prevent memory corruption from concurrent access.
"""
import bittensor as bt
from threading import RLock
from typing import Any, Optional
from diskcache import Cache


class SafeCacheManager:
    """
    Thread-safe cache manager that provides safe operations for diskcache instances.
    Uses a global lock to prevent concurrent access issues that can cause memory corruption.
    """
    # Global lock to coordinate all cache operations across all cache instances
    _global_cache_lock = RLock()
    
    @classmethod
    def safe_get(cls, cache: Optional[Cache], key: str, default: Any = None) -> Any:
        """
        Thread-safe cache get operation with error handling.
        
        Args:
            cache: The cache instance (can be None if caching is disabled)
            key: The cache key
            default: Default value to return if key not found or error occurs
            
        Returns:
            Cached value or default
        """
            
        try:
            with cls._global_cache_lock:
                return cache.get(key, default)
        except Exception as e:
            bt.logging.warning(f"Cache get error for key '{key}': {e}")
            return default
    
    @classmethod
    def safe_set(cls, cache: Optional[Cache], key: str, value: Any, expire: Optional[int] = None) -> bool:
        """
        Thread-safe cache set operation with error handling.
        
        Args:
            cache: The cache instance (can be None if caching is disabled)
            key: The cache key
            value: The value to cache
            expire: Expiration time in seconds
            
        Returns:
            True if successful, False otherwise
        """
            
        try:
            with cls._global_cache_lock:
                if expire is not None:
                    return cache.set(key, value, expire=expire)
                else:
                    return cache.set(key, value)
        except Exception as e:
            bt.logging.warning(f"Cache set error for key '{key}': {e}")
            return False
    
    @classmethod
    def safe_delete(cls, cache: Optional[Cache], key: str) -> bool:
        """
        Thread-safe cache delete operation with error handling.
        
        Args:
            cache: The cache instance (can be None if caching is disabled)
            key: The cache key to delete
            
        Returns:
            True if successful, False otherwise
        """
            
        try:
            with cls._global_cache_lock:
                return cache.delete(key)
        except Exception as e:
            bt.logging.warning(f"Cache delete error for key '{key}': {e}")
            return False
    
    @classmethod
    def safe_clear(cls, cache: Optional[Cache]) -> bool:
        """
        Thread-safe cache clear operation with error handling.
        
        Args:
            cache: The cache instance (can be None if caching is disabled)
            
        Returns:
            True if successful, False otherwise
        """
            
        try:
            with cls._global_cache_lock:
                cache.clear()
                return True
        except Exception as e:
            bt.logging.warning(f"Cache clear error: {e}")
            return False
    
    @classmethod
    def safe_expire(cls, cache: Optional[Cache]) -> bool:
        """
        Thread-safe cache expire operation with error handling.
        
        Args:
            cache: The cache instance (can be None if caching is disabled)
            
        Returns:
            True if successful, False otherwise
        """
            
        try:
            with cls._global_cache_lock:
                cache.expire()
                return True
        except Exception as e:
            bt.logging.warning(f"Cache expire error: {e}")
            return False
    
    @classmethod
    def safe_close(cls, cache: Optional[Cache]) -> bool:
        """
        Thread-safe cache close operation with error handling.
        
        Args:
            cache: The cache instance (can be None if caching is disabled)
            
        Returns:
            True if successful, False otherwise
        """
            
        try:
            with cls._global_cache_lock:
                cache.close()
                return True
        except Exception as e:
            bt.logging.warning(f"Cache close error: {e}")
            return False 