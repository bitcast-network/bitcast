import bittensor as bt
import requests
import time
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from bitcast.validator.config import TRANSCRIPT_MAX_RETRY
import httpx
import hashlib
import asyncio
from tenacity import retry, stop_after_attempt, wait_fixed, RetryError

# CHANNELS

def get_channel_data(youtube_data_client, discrete_mode=False):
    account_info = youtube_data_client.channels().list(
        part="snippet,contentDetails,statistics",
        mine=True
    ).execute()

    channel_id = account_info['items'][0]['id']
    if discrete_mode:
        channel_id = hashlib.sha256(channel_id.encode()).hexdigest()

    channel_info = {
        "title": account_info['items'][0]['snippet']['title'],
        "id": channel_id,
        "channel_start": account_info['items'][0]['snippet']['publishedAt'],
        "viewCount": account_info['items'][0]['statistics']['viewCount'],
        "subCount": account_info['items'][0]['statistics']['subscriberCount'],
        "videoCount": account_info['items'][0]['statistics']['videoCount']
    }

    return channel_info

def get_channel_analytics(youtube_analytics_client, start_date, end_date=None, dimensions=""):
    if end_date is None:
        end_date = datetime.today().strftime('%Y-%m-%d')
        
    analytics_response = youtube_analytics_client.reports().query(
        ids="channel==MINE",
        startDate=start_date,
        endDate=end_date,
        dimensions=dimensions,
        metrics="views,comments,likes,dislikes,shares,averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost,estimatedMinutesWatched"
        ).execute()

    if not analytics_response.get("rows"):
        raise Exception("No channel analytics data found.")

    metric_names = [
        "views", "comments", "likes",
        "shares", "averageViewDuration", "averageViewPercentage",
        "estimatedMinutesWatched"
    ]

    if dimensions:
        # Handle the case where dimensions are present
        analytics_info = []
        for row in analytics_response.get("rows", []):
            dimension_values = row[:len(dimensions.split(','))]
            metrics = dict(zip(metric_names, row[len(dimension_values):]))
            for i, dimension in enumerate(dimensions.split(',')):
                metrics[dimension] = dimension_values[i]
            analytics_info.append(metrics)
    else:
        # Handle the case where no dimensions are present
        analytics_data = analytics_response["rows"][0]
        analytics_info = dict(zip(metric_names, analytics_data))

    return analytics_info

def get_uploads_playlist_id(youtube):
    # Retrieve the channel's uploads playlist id
    channels_response = youtube.channels().list(
        mine=True,
        part="contentDetails"
    ).execute()

    if not channels_response["items"]:
        raise Exception("No channel found for the authenticated user.")
        
    uploads_playlist_id = channels_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    return uploads_playlist_id

def list_all_videos(youtube, uploads_playlist_id):
    videos = []
    nextPageToken = None

    while True:
        playlist_response = youtube.playlistItems().list(
            playlistId=uploads_playlist_id,
            part="snippet",
            maxResults=50,
            pageToken=nextPageToken
        ).execute()
        videos.extend(playlist_response.get("items", []))
        nextPageToken = playlist_response.get("nextPageToken")
        if not nextPageToken:
            break
    return videos

def get_all_uploads(youtube_data_client):
    uploads_playlist_id = get_uploads_playlist_id(youtube_data_client)
    videos = list_all_videos(youtube_data_client, uploads_playlist_id)
    
    video_ids = []
    # Collect each video's title and URL
    for video in videos:
        snippet = video["snippet"]
        title = snippet["title"]
        video_id = snippet["resourceId"]["videoId"]
        video_ids.append(video_id)
    
    return video_ids

# VIDEOS

def get_video_data(youtube_data_client, video_id, discrete_mode=False):
    video_response = youtube_data_client.videos().list(
        part="snippet,statistics,contentDetails,status",
        id=video_id
    ).execute()

    if not video_response["items"]:
        raise Exception(f"No video found with ID: {video_id}")

    if discrete_mode:
        video_id = hashlib.sha256(video_id.encode()).hexdigest()

    video_info = video_response["items"][0]
    stats = {
        "videoId": video_id,
        "title": video_info["snippet"]["title"],
        "description": video_info["snippet"]["description"],
        "publishedAt": video_info["snippet"]["publishedAt"],
        "viewCount": video_info["statistics"].get("viewCount", 0),
        "likeCount": video_info["statistics"].get("likeCount", 0),
        "commentCount": video_info["statistics"].get("commentCount", 0),
        "duration": video_info["contentDetails"]["duration"],
        "caption": video_info["contentDetails"]["caption"].lower() == "true",
        "privacyStatus": video_info["status"]["privacyStatus"]
    }

    return stats

def get_video_analytics(youtube_analytics_client, video_id, start_date=None, end_date=None, dimensions=""):

    if end_date is None:
        end_date = datetime.today().strftime('%Y-%m-%d')

    if start_date is None:
        start_date = (datetime.today() - timedelta(days=365)).strftime('%Y-%m-%d')

    analytics_response = youtube_analytics_client.reports().query(
        ids="channel==MINE",
        startDate=start_date,
        endDate=end_date,
        dimensions=dimensions,
        metrics="views,comments,likes,shares,averageViewDuration,averageViewPercentage,estimatedMinutesWatched",
        filters=f"video=={video_id}"
    ).execute()

    if not analytics_response.get("rows"):
        bt.logging.warning(f"No analytics data found for video ID: {video_id}")
        return []

    metric_names = [
        "views", "comments", "likes",
        "shares", "averageViewDuration", "averageViewPercentage",
        "estimatedMinutesWatched"
    ]

    if dimensions:
        # Handle the case where dimensions are present
        analytics_info = []
        for row in analytics_response.get("rows", []):
            date = row[0]  # Assuming the first element is the date
            metrics = dict(zip(metric_names, row[1:]))
            metrics["date"] = date
            analytics_info.append(metrics)
    else:
        # Handle the case where no dimensions are present
        analytics_data = analytics_response.get("rows", [])[0]
        analytics_info = dict(zip(metric_names, analytics_data))

    return analytics_info

@retry(stop=stop_after_attempt(TRANSCRIPT_MAX_RETRY), wait=wait_fixed(1), reraise=True)
def _fetch_transcript(video_id, rapid_api_key):
    url = "https://youtube-transcriptor.p.rapidapi.com/transcript"
    headers = {"x-rapidapi-key": rapid_api_key, "x-rapidapi-host": "youtube-transcriptor.p.rapidapi.com"}
    querystring = {"video_id": video_id}
    response = requests.get(url, headers=headers, params=querystring, timeout=10)
    response.raise_for_status()
    transcript_data = response.json()

    if isinstance(transcript_data, list) and transcript_data:
        bt.logging.info("Transcript fetched successfully")
        return transcript_data[0].get("transcription", [])
    elif isinstance(transcript_data, dict) and transcript_data.get("error") == "This video has no subtitles.":
        bt.logging.warning(f"No subtitles available for video_id {video_id}")
        raise Exception("No subtitles available")
    else:
        bt.logging.warning(f"Error retrieving transcript: {transcript_data}")
        raise Exception("Error retrieving transcript")

def get_video_transcript(video_id, rapid_api_key):
    try:
        return _fetch_transcript(video_id, rapid_api_key)
    except RetryError:
        return None