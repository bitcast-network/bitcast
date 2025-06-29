# YouTube Content Evaluation Module

## Overview

The YouTube module evaluates YouTube channels and videos against content briefs within the Bitcast validator system. It uses a layered architecture with separate concerns for API operations, business logic, caching, and utilities.

## Architecture

```
bitcast/validator/socials/youtube/
├── main.py                      # Main entry point - eval_youtube()
├── config.py                    # YouTube Analytics API metrics configuration
├── api/                         # YouTube API abstraction layer
│   ├── clients.py              # API client initialization
│   ├── channel.py              # Channel data and analytics operations
│   ├── video.py                # Video data and analytics operations
│   └── transcript.py           # Video transcript fetching
├── cache/                       # Caching layer
│   ├── base.py                 # Base cache implementation
│   └── search.py               # YouTube search result caching
├── evaluation/                  # Business logic layer
│   ├── channel.py              # Channel vetting logic
│   ├── video.py                # Video vetting and content evaluation
│   └── scoring.py              # Video scoring algorithms
└── utils/                       # Utility functions
    ├── state.py                # Global state management
    ├── filters.py              # Brief filtering utilities
    └── helpers.py              # General helper functions
```

## Core Flow

1. **Channel Evaluation**: Fetch channel data → vet against criteria → filter applicable briefs
2. **Video Processing**: Get uploads → batch retrieve data → vet content → match briefs → calculate scores
3. **Result Compilation**: Aggregate scores and performance metrics

## Key Modules

### `main.py`
Primary entry point with `eval_youtube(creds, briefs)` function. Orchestrates the complete evaluation workflow.

### `api/` Layer
- **`clients.py`**: `initialize_youtube_clients(creds)` - Creates authenticated API clients
- **`channel.py`**: `get_channel_data()`, `get_channel_analytics()` - Channel operations
- **`video.py`**: `get_all_uploads()`, `get_video_data_batch()`, `get_video_analytics()` - Video operations
- **`transcript.py`**: `get_video_transcript()` - Transcript fetching via RapidAPI

### `evaluation/` Layer
- **`channel.py`**: `vet_channel()` - Channel qualification against criteria
- **`video.py`**: `vet_videos()`, `vet_video()` - Video content evaluation and brief matching
- **`scoring.py`**: `calculate_video_score()` - Score calculation algorithms

### `utils/` Layer
- **`state.py`**: API call counters, `scored_video_ids` tracking
- **`filters.py`**: `channel_briefs_filter()` - Brief filtering by channel metrics
- **`helpers.py`**: `_format_error()` - Error formatting utilities

## Usage Examples

### Basic Evaluation
```python
from bitcast.validator.socials.youtube.main import eval_youtube

result = eval_youtube(credentials, briefs)
channel_passed = result["yt_account"]["channel_vet_result"]
scores = result["scores"]  # Brief ID -> Score mapping
```

### Direct API Usage
```python
from bitcast.validator.socials.youtube.api import initialize_youtube_clients, get_channel_data

data_client, analytics_client = initialize_youtube_clients(creds)
channel_data = get_channel_data(data_client, discrete_mode=False)
```

### Custom Evaluation
```python
from bitcast.validator.socials.youtube.evaluation import vet_channel, vet_videos

channel_result, is_blacklisted = vet_channel(channel_data, channel_analytics)
video_matches, video_data_dict, analytics_dict, details = vet_videos(
    video_ids, briefs, data_client, analytics_client
)
```

## Configuration

Key configuration variables from `bitcast.validator.utils.config`:

- `YT_MIN_SUBS`, `YT_MIN_CHANNEL_AGE`, `YT_MIN_CHANNEL_RETENTION` - Channel criteria
- `YT_MIN_VIDEO_RETENTION`, `YT_REWARD_DELAY`, `YT_ROLLING_WINDOW` - Video criteria  
- `ECO_MODE` - Performance optimizations and early exits
- `YT_LOOKBACK` - Days to look back for videos
- `RAPID_API_KEY` - API key for transcript services

## Result Structure

```python
{
    "yt_account": {
        "details": {...},           # Channel information
        "analytics": {...},         # Channel analytics
        "channel_vet_result": bool, # Channel qualification status
        "blacklisted": bool         # Blacklist status
    },
    "videos": {
        "video_id": {
            "details": {...},       # Video metadata  
            "analytics": {...},     # Video analytics
            "matches_brief": bool,  # Brief matching status
            "matching_brief_ids": [...], # List of matching brief IDs
            "score": float,         # Video score
            "url": str             # YouTube URL
        }
    },
    "scores": {
        "brief_id": float          # Final scores by brief ID
    },
    "performance_stats": {
        "data_api_calls": int,
        "analytics_api_calls": int,
        "openai_requests": int,
        "evaluation_time_s": float
    }
}
```

## Key Functions Reference

### Main Entry Point
- `eval_youtube(creds, briefs) -> dict` - Complete evaluation workflow

### Channel Operations
- `get_channel_data(client, discrete_mode) -> dict` - Retrieve channel information
- `get_channel_analytics(client, start_date, end_date) -> dict` - Get channel analytics
- `vet_channel(channel_data, channel_analytics) -> (bool, bool)` - Channel evaluation

### Video Operations
- `get_all_uploads(client, lookback_days) -> list` - Get recent video IDs
- `get_video_data_batch(client, video_ids) -> dict` - Batch video data retrieval
- `vet_videos(video_ids, briefs, data_client, analytics_client) -> tuple` - Batch evaluation
- `calculate_video_score(video_id, client, publish_date, analytics) -> dict` - Score calculation

### Utilities
- `initialize_youtube_clients(creds) -> tuple` - Create authenticated clients
- `channel_briefs_filter(briefs, channel_analytics) -> list` - Filter applicable briefs
- `get_video_transcript(video_id) -> str` - Retrieve video transcripts 