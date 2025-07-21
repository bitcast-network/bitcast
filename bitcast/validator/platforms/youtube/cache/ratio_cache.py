"""
Views-to-revenue ratio cache implementation.

This module provides caching for the global views-to-revenue ratio used
for Non-YPP account scoring. The ratio is calculated from YPP accounts
and cached for use in predicting revenue for Non-YPP accounts.
"""

from typing import Optional

import bittensor as bt

from bitcast.validator.utils.config import CACHE_DIRS

from .base import BaseCache


class ViewsToRevenueRatioCache(BaseCache):
    """
    Cache for storing global views-to-revenue ratio for Non-YPP scoring.
    
    This cache stores a single global ratio value that represents the
    average views-to-revenue ratio calculated from all YPP accounts.
    The ratio is updated every 4-hour validation cycle.
    """
    
    @classmethod
    def get_cache_dir(cls) -> str:
        """Return the cache directory path for ratio cache."""
        return CACHE_DIRS["views_revenue_ratio"]
    
    def store_ratio(self, ratio: float) -> None:
        """
        Store the calculated global ratio (overwrites previous).
        
        Args:
            ratio: The global views-to-revenue ratio to cache
        """
        cache = self.get_cache()
        cache.set("global_views_revenue_ratio", ratio)
        bt.logging.info(f"Stored global views-to-revenue ratio: {ratio}")
    
    def get_current_ratio(self) -> Optional[float]:
        """
        Get the cached ratio, returns None if no ratio available.
        
        Returns:
            The cached global ratio or None if not available
        """
        cache = self.get_cache()
        ratio = cache.get("global_views_revenue_ratio")
        if ratio is not None:
            bt.logging.debug(f"Retrieved cached views-to-revenue ratio: {ratio}")
        else:
            bt.logging.debug("No cached views-to-revenue ratio available")
        return ratio
    
    def has_cached_ratio(self) -> bool:
        """
        Check if any ratio is cached (for fallback logic).
        
        Returns:
            True if a ratio is cached, False otherwise
        """
        return self.get_current_ratio() is not None
    
    def clear_ratio(self) -> None:
        """Clear the cached ratio."""
        cache = self.get_cache()
        cache.pop("global_views_revenue_ratio", None)
        bt.logging.info("Cleared cached views-to-revenue ratio") 