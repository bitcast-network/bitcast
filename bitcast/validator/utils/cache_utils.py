import os
import shutil
from diskcache import Cache
from bitcast.validator.utils.config import CACHE_DIRS, CACHE_ROOT
from bitcast.validator.socials.youtube.youtube_utils import youtube_cache
from bitcast.validator.clients.OpenaiClient import OpenaiClient
from bitcast.validator.utils.briefs import BriefsCache

def clear_all_caches():
    """Clear all cache directories and instances."""
    # Clear YouTube cache
    youtube_cache.clear_all()
    
    # Clear OpenAI cache
    if OpenaiClient._cache:
        OpenaiClient._cache.clear()
    
    # Clear Briefs cache
    if BriefsCache._cache:
        BriefsCache._cache.clear()
    
    # Clear all cache directories
    for cache_dir in CACHE_DIRS.values():
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
            os.makedirs(cache_dir)

def clear_expired_caches():
    """Clear expired entries from all caches."""
    # Clear expired YouTube cache entries
    youtube_cache.clear_expired()
    
    # Clear expired OpenAI cache entries
    if OpenaiClient._cache:
        OpenaiClient._cache.expire()
    
    # Clear expired Briefs cache entries
    if BriefsCache._cache:
        BriefsCache._cache.expire() 