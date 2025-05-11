import os
import shutil
from diskcache import Cache
from bitcast.validator.utils.config import CACHE_DIRS, CACHE_ROOT
from bitcast.validator.socials.youtube.youtube_utils import youtube_cache
from bitcast.validator.clients.OpenaiClient import OpenaiClient
from bitcast.validator.utils.briefs import BriefsCache
from bitcast.validator.utils.blacklist import BlacklistCache

def clear_all_caches():
    """Clear all cache directories and instances."""
    clear_youtube_cache()
    clear_openai_cache()
    clear_briefs_cache()
    clear_blacklist_cache()
    
    # Clear all cache directories
    for cache_dir in CACHE_DIRS.values():
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
            os.makedirs(cache_dir)

def clear_expired_caches():
    """Clear expired entries from all caches."""
    clear_expired_youtube_cache()
    clear_expired_openai_cache()
    clear_expired_briefs_cache()
    clear_expired_blacklist_cache()

def clear_youtube_cache():
    """Clear YouTube cache."""
    youtube_cache.clear_all()

def clear_openai_cache():
    """Clear OpenAI cache."""
    if OpenaiClient._cache:
        OpenaiClient._cache.clear()

def clear_briefs_cache():
    """Clear Briefs cache."""
    if BriefsCache._cache:
        BriefsCache._cache.clear()

def clear_blacklist_cache():
    """Clear Blacklist cache."""
    if BlacklistCache._cache:
        BlacklistCache._cache.clear()

def clear_expired_youtube_cache():
    """Clear expired YouTube cache entries."""
    youtube_cache.clear_expired()

def clear_expired_openai_cache():
    """Clear expired OpenAI cache entries."""
    if OpenaiClient._cache:
        OpenaiClient._cache.expire()

def clear_expired_briefs_cache():
    """Clear expired Briefs cache entries."""
    if BriefsCache._cache:
        BriefsCache._cache.expire()

def clear_expired_blacklist_cache():
    """Clear expired Blacklist cache entries."""
    if BlacklistCache._cache:
        BlacklistCache._cache.expire()