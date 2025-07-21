from googleapiclient.discovery import build

from ..utils.error_handlers import handle_authentication_error


def initialize_youtube_clients(creds):
    """Initialize YouTube Data and Analytics API clients.
    
    Args:
        creds: OAuth2 credentials for YouTube API
        
    Returns:
        tuple: (youtube_data_client, youtube_analytics_client)
        
    Raises:
        RuntimeError: If client initialization fails due to invalid credentials or configuration
    """
    try:
        youtube_data_client = build("youtube", "v3", credentials=creds)
        youtube_analytics_client = build("youtubeAnalytics", "v2", credentials=creds)
        return youtube_data_client, youtube_analytics_client
    except Exception as e:
        handle_authentication_error(e, "youtube_oauth") 