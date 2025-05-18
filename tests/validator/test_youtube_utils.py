import pytest
from bitcast.validator.socials.youtube.youtube_utils import get_video_transcript
from unittest.mock import MagicMock, patch
from bitcast.validator.utils.config import TRANSCRIPT_MAX_RETRY
import os
import shutil
import time

@pytest.mark.asyncio
async def test_get_video_transcript_retry_logic():
    video_id = "mock_video_id"
    rapid_api_key = "mock_rapid_api_key"
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(side_effect=[
        {"error": "This video has no subtitles."},  # First attempt
        {"error": "This video has no subtitles."},  # Second attempt
        [{"transcription": "mock_transcription"}]   # Third attempt, success
    ])

    with patch('bitcast.validator.socials.youtube.youtube_utils.requests.get', return_value=mock_response) as mock_get:
        with patch('bitcast.validator.socials.youtube.youtube_utils.time.sleep', return_value=None):  # Mock time.sleep to avoid delays
            transcript = get_video_transcript(video_id, rapid_api_key)
            assert transcript == "mock_transcription"
            assert mock_get.call_count == 3  # Ensure it retried 3 times 