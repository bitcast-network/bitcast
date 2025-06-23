"""
YouTube cache module.

This module provides caching functionality for YouTube API responses
to reduce API calls and improve performance.
"""

from .search import YouTubeSearchCache

__all__ = [
    'YouTubeSearchCache'
] 