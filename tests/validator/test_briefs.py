from pathlib import Path

import requests
from datetime import datetime, timezone, timedelta
from bitcast.validator.utils.briefs import get_briefs, BriefsCache
from bitcast.validator.utils.config import YT_REWARD_DELAY

class MockResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code != 200:
            raise requests.exceptions.HTTPError(f"HTTP Error: {self.status_code}")

def test_get_briefs_all(monkeypatch):
    """
    Test that get_briefs returns all briefs when the 'all' flag is True.
    """
    mock_data = {
        "briefs": [
            {"id": "brief1", "start_date": "2020-01-01", "end_date": "2020-01-02"},
            {"id": "brief2", "start_date": "2021-01-01", "end_date": "2021-01-02"}
        ]
    }

    def mock_get(*args, **kwargs):
        return MockResponse(mock_data)

    monkeypatch.setattr(requests, "get", mock_get)
    briefs = get_briefs(all=True)
    assert isinstance(briefs, list)
    assert len(briefs) == 2
    assert briefs[0]["id"] == "brief1"
    assert briefs[1]["id"] == "brief2"

def test_get_briefs_active(monkeypatch):
    """
    Test that get_briefs correctly filters briefs based on active dates when 'all' is False.
    Only briefs whose start_date and end_date include the current date should be returned.
    """
    current_date = datetime.now(timezone.utc).date()
    current_date_str = current_date.strftime("%Y-%m-%d")
    mock_data = {
        "briefs": [
            {"id": "active", "start_date": current_date_str, "end_date": current_date_str},
            {"id": "inactive", "start_date": "2000-01-01", "end_date": "2000-01-02"}
        ]
    }

    def mock_get(*args, **kwargs):
        return MockResponse(mock_data)

    monkeypatch.setattr(requests, "get", mock_get)
    briefs = get_briefs()  # Default is all=False, so it filters active briefs.
    assert isinstance(briefs, list)
    # Only the 'active' brief should be returned.
    assert len(briefs) == 1
    assert briefs[0]["id"] == "active"

def test_get_briefs_error(monkeypatch):
    """
    Test that get_briefs returns cached data when available, or empty list when no cache exists.
    """
    # First test: No cache available
    cache = BriefsCache.get_cache()
    cache.delete("briefs_True")  # Ensure no cache exists
    
    def mock_get(*args, **kwargs):
        raise requests.exceptions.RequestException("API error")
    
    monkeypatch.setattr(requests, "get", mock_get)
    briefs = get_briefs(all=True)
    assert briefs == []  # Should return empty list when no cache exists
    
    # Second test: Cache available
    cache_data = [{"id": "cached_brief", "start_date": "2020-01-01", "end_date": "2020-01-02"}]
    cache.set("briefs_True", cache_data)
    
    briefs = get_briefs(all=True)
    assert len(briefs) == 1
    assert briefs[0]["id"] == "cached_brief"  # Should return cached data

def test_get_briefs_date_parsing_error(monkeypatch):
    """
    Test that get_briefs handles date parsing errors gracefully.
    Malformed date strings should result in the corresponding brief being skipped.
    """
    mock_data = {
        "briefs": [
            {"id": "invalid", "start_date": "invalid-date", "end_date": "invalid-date"}
        ]
    }

    def mock_get(*args, **kwargs):
        return MockResponse(mock_data)

    monkeypatch.setattr(requests, "get", mock_get)
    briefs = get_briefs()  # Filtering active briefs; invalid date will be skipped.
    assert briefs == []

def test_get_briefs_with_reward_delay(monkeypatch):
    """
    Test that get_briefs correctly includes briefs that ended within YT_REWARD_DELAY days.
    """
    # Calculate dates for testing
    current_date = datetime.now(timezone.utc).date()
    end_date = current_date - timedelta(days=1)  # Yesterday
    start_date = end_date - timedelta(days=5)    # 5 days before end date
    
    # Create a brief that ended yesterday (should be included due to reward delay)
    mock_data = {
        "briefs": [
            {
                "id": "recently_ended", 
                "start_date": start_date.strftime("%Y-%m-%d"), 
                "end_date": end_date.strftime("%Y-%m-%d")
            },
            {
                "id": "old_ended", 
                "start_date": "2000-01-01", 
                "end_date": "2000-01-02"
            }
        ]
    }

    def mock_get(*args, **kwargs):
        return MockResponse(mock_data)

    monkeypatch.setattr(requests, "get", mock_get)
    briefs = get_briefs()  # Default is all=False, so it filters active briefs.
    
    # The 'recently_ended' brief should be included because it ended within YT_REWARD_DELAY days
    assert isinstance(briefs, list)
    assert len(briefs) == 1
    assert briefs[0]["id"] == "recently_ended"
    
    # Test with a brief that ended beyond the reward delay period
    old_end_date = current_date - timedelta(days=YT_REWARD_DELAY + 1)
    old_start_date = old_end_date - timedelta(days=5)
    
    mock_data = {
        "briefs": [
            {
                "id": "beyond_delay", 
                "start_date": old_start_date.strftime("%Y-%m-%d"), 
                "end_date": old_end_date.strftime("%Y-%m-%d")
            }
        ]
    }
    
    briefs = get_briefs()
    assert len(briefs) == 0  # Should not be included as it's beyond the reward delay period

def test_get_briefs_caching_success(monkeypatch):
    """
    Test that get_briefs caches successful API responses.
    """
    mock_data = {
        "briefs": [
            {"id": "brief1", "start_date": "2020-01-01", "end_date": "2020-01-02"}
        ]
    }

    def mock_get(*args, **kwargs):
        return MockResponse(mock_data)

    monkeypatch.setattr(requests, "get", mock_get)
    
    # First call - should fetch from API and cache
    briefs = get_briefs(all=True)
    assert len(briefs) == 1
    assert briefs[0]["id"] == "brief1"
    
    # Verify cache was populated
    cache = BriefsCache.get_cache()
    cached_briefs = cache.get("briefs_True")
    assert cached_briefs is not None
    assert len(cached_briefs) == 1
    assert cached_briefs[0]["id"] == "brief1"

def test_get_briefs_caching_fallback(monkeypatch):
    """
    Test that get_briefs falls back to cached data when API fails.
    """
    # First, populate the cache with some data
    cache = BriefsCache.get_cache()
    cache_data = [{"id": "cached_brief", "start_date": "2020-01-01", "end_date": "2020-01-02"}]
    cache.set("briefs_True", cache_data)
    
    # Mock API to fail
    def mock_get(*args, **kwargs):
        raise requests.exceptions.RequestException("API error")
    
    monkeypatch.setattr(requests, "get", mock_get)
    
    # Call should use cached data
    briefs = get_briefs(all=True)
    assert len(briefs) == 1
    assert briefs[0]["id"] == "cached_brief"

def test_get_briefs_no_cache_fallback(monkeypatch):
    """
    Test that get_briefs returns empty list when API fails and no cache exists.
    """
    # Ensure cache is empty
    cache = BriefsCache.get_cache()
    cache.delete("briefs_True")
    
    # Mock API to fail
    def mock_get(*args, **kwargs):
        raise requests.exceptions.RequestException("API error")
    
    monkeypatch.setattr(requests, "get", mock_get)
    
    # Call should return empty list
    briefs = get_briefs(all=True)
    assert briefs == []
