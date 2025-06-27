import bittensor as bt
import requests
from tenacity import retry, stop_after_attempt, wait_fixed, RetryError
from bitcast.validator.utils.config import TRANSCRIPT_MAX_RETRY

# ============================================================================
# Transcript API Functions
# ============================================================================

@retry(stop=stop_after_attempt(TRANSCRIPT_MAX_RETRY), wait=wait_fixed(1), reraise=True)
def _fetch_transcript(video_id, rapid_api_key):
    """Internal function to fetch video transcript with retry logic."""
    url = "https://youtube-transcriptor.p.rapidapi.com/transcript"
    headers = {"x-rapidapi-key": rapid_api_key, "x-rapidapi-host": "youtube-transcriptor.p.rapidapi.com"}
    querystring = {"video_id": video_id}
    response = requests.get(url, headers=headers, params=querystring, timeout=5)
    response.raise_for_status()
    transcript_data = response.json()

    if isinstance(transcript_data, list) and transcript_data:
        bt.logging.info("Transcript fetched successfully")
        return transcript_data[0].get("transcription", [])
    elif isinstance(transcript_data, dict) and transcript_data.get("error") == "This video has no subtitles.":
        bt.logging.warning("No subtitles available for video")
        raise Exception("No subtitles available")
    else:
        bt.logging.warning(f"Error retrieving transcript: {transcript_data}")
        raise Exception("Error retrieving transcript")

def get_video_transcript(video_id, rapid_api_key):
    """Get video transcript with error handling."""
    try:
        return _fetch_transcript(video_id, rapid_api_key)
    except RetryError:
        return None 