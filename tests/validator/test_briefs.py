from pathlib import Path

import requests
from datetime import datetime, timezone
from bitcast.validator.briefs import get_briefs

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
    Test that get_briefs returns an empty list when a RequestException is raised.
    """
    def mock_get(*args, **kwargs):
        raise requests.exceptions.RequestException("API error")
    monkeypatch.setattr(requests, "get", mock_get)
    briefs = get_briefs(all=True)
    assert briefs == []

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
