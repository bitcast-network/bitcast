import requests
import json
from typing import Dict, List, Any

# API endpoint
BASE_URL = "http://localhost:8000"

def test_vet_video():
    """Test the vet_video endpoint with sample data"""
    # Sample data
    video_id = "test_video_123"
    briefs = [
        {
            "brief": "A test video",
            "start_date": "2024-01-01",
            "id": "brief_1"
        }
    ]
    video_data = {
        "videoId": video_id,
        "privacyStatus": "public",
        "caption": False,
        "description": "This is a test video description",
        "transcript": "This is a sample transcript for testing purposes.",
        "duration": "PT10M",  # ISO 8601 duration format
        "publishedAt": "2024-01-01T00:00:00Z",
        "bitcastVideoId": video_id
    }
    video_analytics = {
        "averageViewPercentage": 75
    }

    # Prepare request data
    request_data = {
        "video_id": video_id,
        "briefs": briefs,
        "video_data": video_data,
        "video_analytics": video_analytics
    }

    # Make request to vet_video endpoint
    response = requests.post(
        f"{BASE_URL}/vet_video/",
        json=request_data
    )

    # Print response
    print(f"Status Code: {response.status_code}")
    print("Response:")
    print(json.dumps(response.json(), indent=2))

if __name__ == "__main__":
    test_vet_video() 