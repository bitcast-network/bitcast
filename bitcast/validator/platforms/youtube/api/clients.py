import bittensor as bt
from googleapiclient.discovery import build


def initialize_youtube_clients(creds):
    """Initialize YouTube Data and Analytics API clients.
    
    Args:
        creds: OAuth2 credentials for YouTube API
        
    Returns:
        tuple: (youtube_data_client, youtube_analytics_client) or (None, None) if error
    """
    try:
        youtube_data_client = build("youtube", "v3", credentials=creds)
        youtube_analytics_client = build("youtubeAnalytics", "v2", credentials=creds)
        return youtube_data_client, youtube_analytics_client
    except Exception as e:
        bt.logging.warning(f"An error occurred while initializing YouTube clients: {e}")
        return None, None 