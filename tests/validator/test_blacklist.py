import requests
from bitcast.validator.utils.blacklist import get_blacklist, BlacklistCache, is_blacklisted
from bitcast.validator.utils.config import BLACKLIST_CACHE_EXPIRY
import time

class MockResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code != 200:
            raise requests.exceptions.HTTPError(f"HTTP Error: {self.status_code}")

def test_get_blacklist_success(monkeypatch):
    """Test that get_blacklist successfully fetches and returns blacklist items."""
    # Clear any existing cache
    cache = BlacklistCache.get_cache()
    cache.delete("blacklist")
    
    mock_data = {
        "items": ["account1", "account2", "account3"]
    }

    def mock_get(*args, **kwargs):
        return MockResponse(mock_data)

    monkeypatch.setattr(requests, "get", mock_get)
    blacklist = get_blacklist()
    
    assert isinstance(blacklist, list)
    assert len(blacklist) == 3
    assert "account1" in blacklist
    assert "account2" in blacklist
    assert "account3" in blacklist

def test_get_blacklist_empty_response(monkeypatch):
    """Test that get_blacklist handles empty response correctly."""
    # Clear any existing cache
    cache = BlacklistCache.get_cache()
    cache.delete("blacklist")
    
    mock_data = {
        "items": []
    }

    def mock_get(*args, **kwargs):
        return MockResponse(mock_data)

    monkeypatch.setattr(requests, "get", mock_get)
    blacklist = get_blacklist()
    
    assert isinstance(blacklist, list)
    assert len(blacklist) == 0

def test_get_blacklist_api_error(monkeypatch):
    """Test that get_blacklist falls back to cache when API fails."""
    # First, populate the cache with some data
    cache = BlacklistCache.get_cache()
    cache_data = ["cached_account1", "cached_account2"]
    cache.set("blacklist", cache_data, expire=BLACKLIST_CACHE_EXPIRY)
    
    # Mock API to fail
    def mock_get(*args, **kwargs):
        raise requests.exceptions.RequestException("API error")
    
    monkeypatch.setattr(requests, "get", mock_get)
    
    # Should use cached data
    blacklist = get_blacklist()
    assert len(blacklist) == 2
    assert "cached_account1" in blacklist
    assert "cached_account2" in blacklist

def test_get_blacklist_no_cache_fallback(monkeypatch):
    """Test that get_blacklist returns empty list when API fails and no cache exists."""
    # Ensure cache is empty
    cache = BlacklistCache.get_cache()
    cache.delete("blacklist")
    
    # Mock API to fail
    def mock_get(*args, **kwargs):
        raise requests.exceptions.RequestException("API error")
    
    monkeypatch.setattr(requests, "get", mock_get)
    
    # Should return empty list
    blacklist = get_blacklist()
    assert blacklist == []

def test_get_blacklist_cache_expiration(monkeypatch):
    """Test that blacklist cache expires after the specified time."""
    # First, populate the cache with some data
    cache = BlacklistCache.get_cache()
    cache_data = ["account1", "account2"]
    cache.set("blacklist", cache_data, expire=1)  # Set 1 second expiration for testing
    
    # Wait for cache to expire
    time.sleep(1.1)
    
    # Mock API to return new data
    mock_data = {
        "items": ["new_account1", "new_account2"]
    }
    
    def mock_get(*args, **kwargs):
        return MockResponse(mock_data)
    
    monkeypatch.setattr(requests, "get", mock_get)
    
    # Should fetch new data since cache expired
    blacklist = get_blacklist()
    assert len(blacklist) == 2
    assert "new_account1" in blacklist
    assert "new_account2" in blacklist

def test_get_blacklist_invalid_response(monkeypatch):
    """Test that get_blacklist handles invalid API response format."""
    # Clear any existing cache
    cache = BlacklistCache.get_cache()
    cache.delete("blacklist")
    
    mock_data = {
        "invalid_key": ["account1", "account2"]
    }

    def mock_get(*args, **kwargs):
        return MockResponse(mock_data)

    monkeypatch.setattr(requests, "get", mock_get)
    blacklist = get_blacklist()
    
    assert isinstance(blacklist, list)
    assert len(blacklist) == 0

def test_get_blacklist_http_error(monkeypatch):
    """Test that get_blacklist handles HTTP errors correctly."""
    # Clear any existing cache
    cache = BlacklistCache.get_cache()
    cache.delete("blacklist")
    
    def mock_get(*args, **kwargs):
        return MockResponse({}, status_code=500)

    monkeypatch.setattr(requests, "get", mock_get)
    
    # Should return empty list when no cache exists
    blacklist = get_blacklist()
    assert blacklist == []

def test_blacklist_cache_cleanup():
    """Test that BlacklistCache cleanup works correctly."""
    # Initialize cache
    cache = BlacklistCache.get_cache()
    assert cache is not None
    
    # Add some test data
    cache.set("test_key", "test_value")
    assert cache.get("test_key") == "test_value"
    
    # Cleanup
    BlacklistCache.cleanup()
    
    # Cache should be None after cleanup
    assert BlacklistCache._cache is None

def test_is_blacklisted_success(monkeypatch):
    """Test that is_blacklisted correctly identifies blacklisted and non-blacklisted IDs."""
    # Clear any existing cache
    cache = BlacklistCache.get_cache()
    cache.delete("blacklist")
    
    mock_data = {
        "items": ["blacklisted1", "blacklisted2"]
    }

    def mock_get(*args, **kwargs):
        return MockResponse(mock_data)

    monkeypatch.setattr(requests, "get", mock_get)
    
    # Test blacklisted IDs
    assert is_blacklisted("blacklisted1") is True
    assert is_blacklisted("blacklisted2") is True
    
    # Test non-blacklisted ID
    assert is_blacklisted("not_blacklisted") is False

def test_is_blacklisted_empty_list(monkeypatch):
    """Test that is_blacklisted returns False when blacklist is empty."""
    mock_data = {
        "items": []
    }

    def mock_get(*args, **kwargs):
        return MockResponse(mock_data)

    monkeypatch.setattr(requests, "get", mock_get)
    
    assert is_blacklisted("any_id") is False

def test_is_blacklisted_api_error(monkeypatch):
    """Test that is_blacklisted uses cached data when API fails."""
    # First, populate the cache with some data
    cache = BlacklistCache.get_cache()
    cache_data = ["cached_blacklisted"]
    cache.set("blacklist", cache_data, expire=BLACKLIST_CACHE_EXPIRY)
    
    # Mock API to fail
    def mock_get(*args, **kwargs):
        raise requests.exceptions.RequestException("API error")
    
    monkeypatch.setattr(requests, "get", mock_get)
    
    # Should use cached data
    assert is_blacklisted("cached_blacklisted") is True
    assert is_blacklisted("not_cached") is False

def test_cache_size_limit():
    """Test that cache respects size limit and handles full cache correctly."""
    # Clear any existing cache
    cache = BlacklistCache.get_cache()
    cache.delete("blacklist")
    
    try:
        # Create a large string that would exceed 1MB
        large_data = ["x" * 1024 * 1024]  # 1MB string
        
        # Try to set large data
        cache.set("blacklist", large_data, expire=BLACKLIST_CACHE_EXPIRY)
        
        # Verify cache is empty or contains truncated data
        cached_data = cache.get("blacklist")
        assert cached_data is None or len(str(cached_data)) < 1024 * 1024
    finally:
        # Cleanup
        cache.delete("blacklist")

def test_cache_update(monkeypatch):
    """Test that cache is properly updated with new data from API."""
    # Clear any existing cache
    cache = BlacklistCache.get_cache()
    cache.delete("blacklist")
    
    try:
        # First API call
        mock_data1 = {
            "items": ["item1", "item2"]
        }
        
        def mock_get1(*args, **kwargs):
            return MockResponse(mock_data1)
        
        monkeypatch.setattr(requests, "get", mock_get1)
        blacklist1 = get_blacklist()
        assert len(blacklist1) == 2
        assert "item1" in blacklist1
        assert "item2" in blacklist1
        
        # Clear cache to force second API call
        cache.delete("blacklist")
        
        # Second API call with different data
        mock_data2 = {
            "items": ["item3", "item4"]
        }
        
        def mock_get2(*args, **kwargs):
            return MockResponse(mock_data2)
        
        monkeypatch.setattr(requests, "get", mock_get2)
        blacklist2 = get_blacklist()
        assert len(blacklist2) == 2
        assert "item3" in blacklist2
        assert "item4" in blacklist2
    finally:
        # Cleanup
        cache.delete("blacklist")

def test_concurrent_access(monkeypatch):
    """Test thread safety of cache with concurrent access."""
    import threading
    
    # Clear any existing cache
    cache = BlacklistCache.get_cache()
    cache.delete("blacklist")
    
    try:
        # Mock API response
        mock_data = {
            "items": ["item1", "item2"]
        }
        
        def mock_get(*args, **kwargs):
            return MockResponse(mock_data)
        
        monkeypatch.setattr(requests, "get", mock_get)
        
        # Create multiple threads that will access the cache simultaneously
        results = []
        def thread_func():
            blacklist = get_blacklist()
            results.append(blacklist)
            assert isinstance(blacklist, list)
            assert len(blacklist) == 2
            assert "item1" in blacklist
            assert "item2" in blacklist
        
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=thread_func)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify all threads got the same data
        assert all(r == results[0] for r in results)
        
        # Verify cache is still accessible after concurrent access
        assert BlacklistCache.get_cache() is not None
    finally:
        # Cleanup
        cache.delete("blacklist") 