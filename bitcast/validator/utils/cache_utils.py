import os
import shutil
import bittensor as bt
from bitcast.validator.utils.config import CACHE_DIRS, CACHE_ROOT
from bitcast.validator.clients.OpenaiClient import OpenaiClient
from bitcast.validator.utils.briefs import BriefsCache
from bitcast.validator.utils.blacklist import BlacklistCache
from bitcast.validator.socials.youtube.youtube_utils import YouTubeSearchCache

# Import SafeCacheManager for thread-safe cache operations
from bitcast.validator.utils.safe_cache import SafeCacheManager

def clear_all_caches():
    """Clear all cache directories and instances."""
    bt.logging.info("Clearing all caches")
    try:
        clear_openai_cache()
        clear_briefs_cache()
        clear_blacklist_cache()
        clear_youtube_search_cache()
        
        # Clear all cache directories
        for cache_dir in CACHE_DIRS.values():
            if os.path.exists(cache_dir):
                bt.logging.debug(f"Clearing cache directory: {cache_dir}")
                shutil.rmtree(cache_dir)
                os.makedirs(cache_dir)
        bt.logging.info("Successfully cleared all caches")
    except Exception as e:
        bt.logging.error(f"Error clearing all caches: {str(e)}")
        raise

def clear_expired_caches():
    """Clear expired entries from all caches."""
    bt.logging.info("Clearing expired cache entries")
    try:
        clear_expired_openai_cache()
        clear_expired_briefs_cache()
        clear_expired_blacklist_cache()
        clear_expired_youtube_search_cache()
        bt.logging.info("Successfully cleared expired cache entries")
    except Exception as e:
        bt.logging.error(f"Error clearing expired cache entries: {str(e)}")
        raise

def clear_openai_cache():
    """Clear OpenAI cache."""
    bt.logging.info("Clearing OpenAI cache")
    try:
        cache = OpenaiClient.get_cache()
        if SafeCacheManager.safe_clear(cache):
            bt.logging.info("Successfully cleared OpenAI cache")
        else:
            bt.logging.warning("OpenAI cache not available or clearing failed")
    except Exception as e:
        bt.logging.error(f"Error clearing OpenAI cache: {str(e)}")
        raise

def clear_briefs_cache():
    """Clear Briefs cache."""
    bt.logging.info("Clearing Briefs cache")
    try:
        cache = BriefsCache.get_cache()
        if SafeCacheManager.safe_clear(cache):
            bt.logging.info("Successfully cleared Briefs cache")
        else:
            bt.logging.warning("Briefs cache not available or clearing failed")
    except Exception as e:
        bt.logging.error(f"Error clearing Briefs cache: {str(e)}")
        raise

def clear_blacklist_cache():
    """Clear Blacklist cache."""
    bt.logging.info("Clearing Blacklist cache")
    try:
        cache = BlacklistCache.get_cache()
        if SafeCacheManager.safe_clear(cache):
            bt.logging.info("Successfully cleared Blacklist cache")
        else:
            bt.logging.warning("Blacklist cache not available or clearing failed")
    except Exception as e:
        bt.logging.error(f"Error clearing Blacklist cache: {str(e)}")
        raise

def clear_expired_openai_cache():
    """Clear expired OpenAI cache entries."""
    bt.logging.info("Clearing expired OpenAI cache entries")
    try:
        cache = OpenaiClient.get_cache()
        if SafeCacheManager.safe_expire(cache):
            bt.logging.info("Successfully cleared expired OpenAI cache entries")
        else:
            bt.logging.warning("OpenAI cache not available or expire operation failed")
    except Exception as e:
        bt.logging.error(f"Error clearing expired OpenAI cache entries: {str(e)}")
        raise

def clear_expired_briefs_cache():
    """Clear expired Briefs cache entries."""
    bt.logging.info("Clearing expired Briefs cache entries")
    try:
        cache = BriefsCache.get_cache()
        if SafeCacheManager.safe_expire(cache):
            bt.logging.info("Successfully cleared expired Briefs cache entries")
        else:
            bt.logging.warning("Briefs cache not available or expire operation failed")
    except Exception as e:
        bt.logging.error(f"Error clearing expired Briefs cache entries: {str(e)}")
        raise

def clear_expired_blacklist_cache():
    """Clear expired Blacklist cache entries."""
    bt.logging.info("Clearing expired Blacklist cache entries")
    try:
        cache = BlacklistCache.get_cache()
        if SafeCacheManager.safe_expire(cache):
            bt.logging.info("Successfully cleared expired Blacklist cache entries")
        else:
            bt.logging.warning("Blacklist cache not available or expire operation failed")
    except Exception as e:
        bt.logging.error(f"Error clearing expired Blacklist cache entries: {str(e)}")
        raise

def clear_youtube_search_cache():
    """Clear YouTube search cache."""
    bt.logging.info("Clearing YouTube search cache")
    try:
        cache = YouTubeSearchCache.get_cache()
        if SafeCacheManager.safe_clear(cache):
            bt.logging.info("Successfully cleared YouTube search cache")
        else:
            bt.logging.warning("YouTube search cache not available or clearing failed")
    except Exception as e:
        bt.logging.error(f"Error clearing YouTube search cache: {str(e)}")
        raise

def clear_expired_youtube_search_cache():
    """Clear expired YouTube search cache entries."""
    bt.logging.info("Clearing expired YouTube search cache entries")
    try:
        cache = YouTubeSearchCache.get_cache()
        if SafeCacheManager.safe_expire(cache):
            bt.logging.info("Successfully cleared expired YouTube search cache entries")
        else:
            bt.logging.warning("YouTube search cache not available or expire operation failed")
    except Exception as e:
        bt.logging.error(f"Error clearing expired YouTube search cache entries: {str(e)}")
        raise