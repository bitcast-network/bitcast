import os
import shutil
import bittensor as bt
from diskcache import Cache
from bitcast.validator.utils.config import CACHE_DIRS, CACHE_ROOT
from bitcast.validator.socials.youtube.youtube_utils import youtube_cache
from bitcast.validator.clients.OpenaiClient import OpenaiClient
from bitcast.validator.utils.briefs import BriefsCache
from bitcast.validator.utils.blacklist import BlacklistCache

def clear_all_caches():
    """Clear all cache directories and instances."""
    bt.logging.info("Clearing all caches")
    try:
        clear_youtube_cache()
        clear_openai_cache()
        clear_briefs_cache()
        clear_blacklist_cache()
        
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
        clear_expired_youtube_cache()
        clear_expired_openai_cache()
        clear_expired_briefs_cache()
        clear_expired_blacklist_cache()
        bt.logging.info("Successfully cleared expired cache entries")
    except Exception as e:
        bt.logging.error(f"Error clearing expired cache entries: {str(e)}")
        raise

def clear_youtube_cache():
    """Clear YouTube cache."""
    bt.logging.info("Clearing YouTube cache")
    try:
        youtube_cache.clear_all()
        bt.logging.info("Successfully cleared YouTube cache")
    except Exception as e:
        bt.logging.error(f"Error clearing YouTube cache: {str(e)}")
        raise

def clear_openai_cache():
    """Clear OpenAI cache."""
    bt.logging.info("Clearing OpenAI cache")
    try:
        if OpenaiClient._cache:
            OpenaiClient._cache.clear()
            bt.logging.info("Successfully cleared OpenAI cache")
        else:
            bt.logging.warning("OpenAI cache not initialized")
    except Exception as e:
        bt.logging.error(f"Error clearing OpenAI cache: {str(e)}")
        raise

def clear_briefs_cache():
    """Clear Briefs cache."""
    bt.logging.info("Clearing Briefs cache")
    try:
        if BriefsCache._cache:
            BriefsCache._cache.clear()
            bt.logging.info("Successfully cleared Briefs cache")
        else:
            bt.logging.warning("Briefs cache not initialized")
    except Exception as e:
        bt.logging.error(f"Error clearing Briefs cache: {str(e)}")
        raise

def clear_blacklist_cache():
    """Clear Blacklist cache."""
    bt.logging.info("Clearing Blacklist cache")
    try:
        if BlacklistCache._cache:
            BlacklistCache._cache.clear()
            bt.logging.info("Successfully cleared Blacklist cache")
        else:
            bt.logging.warning("Blacklist cache not initialized")
    except Exception as e:
        bt.logging.error(f"Error clearing Blacklist cache: {str(e)}")
        raise

def clear_expired_youtube_cache():
    """Clear expired YouTube cache entries."""
    bt.logging.info("Clearing expired YouTube cache entries")
    try:
        youtube_cache.clear_expired()
        bt.logging.info("Successfully cleared expired YouTube cache entries")
    except Exception as e:
        bt.logging.error(f"Error clearing expired YouTube cache entries: {str(e)}")
        raise

def clear_expired_openai_cache():
    """Clear expired OpenAI cache entries."""
    bt.logging.info("Clearing expired OpenAI cache entries")
    try:
        if OpenaiClient._cache:
            OpenaiClient._cache.expire()
            bt.logging.info("Successfully cleared expired OpenAI cache entries")
        else:
            bt.logging.warning("OpenAI cache not initialized")
    except Exception as e:
        bt.logging.error(f"Error clearing expired OpenAI cache entries: {str(e)}")
        raise

def clear_expired_briefs_cache():
    """Clear expired Briefs cache entries."""
    bt.logging.info("Clearing expired Briefs cache entries")
    try:
        if BriefsCache._cache:
            BriefsCache._cache.expire()
            bt.logging.info("Successfully cleared expired Briefs cache entries")
        else:
            bt.logging.warning("Briefs cache not initialized")
    except Exception as e:
        bt.logging.error(f"Error clearing expired Briefs cache entries: {str(e)}")
        raise

def clear_expired_blacklist_cache():
    """Clear expired Blacklist cache entries."""
    bt.logging.info("Clearing expired Blacklist cache entries")
    try:
        if BlacklistCache._cache:
            BlacklistCache._cache.expire()
            bt.logging.info("Successfully cleared expired Blacklist cache entries")
        else:
            bt.logging.warning("Blacklist cache not initialized")
    except Exception as e:
        bt.logging.error(f"Error clearing expired Blacklist cache entries: {str(e)}")
        raise