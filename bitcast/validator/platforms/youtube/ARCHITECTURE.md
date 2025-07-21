# YouTube Content Evaluation Platform

## Overview

The YouTube platform module provides comprehensive evaluation of YouTube channels and videos against content briefs within the Bitcast validator system. It implements a sophisticated, multi-layered architecture with specialized concerns for API operations, content security, business logic validation, performance optimization, and scoring calculations.

## Architecture

```
bitcast/validator/platforms/youtube/
├── youtube_evaluator.py         # Platform evaluator interface implementation
├── main.py                      # Main entry point - eval_youtube()
├── config.py                    # YouTube Analytics API metrics configuration
├── api/                         # YouTube API abstraction layer
│   ├── clients.py              # API client initialization
│   ├── channel.py              # Channel data and analytics operations
│   ├── video.py                # Video data and analytics operations
│   └── transcript.py           # Video transcript fetching via RapidAPI
├── cache/                       # Caching layer with TTL and size management
│   ├── base.py                 # Base cache implementation
│   ├── search.py               # YouTube search result caching
│   └── ratio_cache.py          # Views-to-revenue ratio persistent caching
├── evaluation/                  # Business logic and evaluation orchestration
│   ├── channel.py              # Channel vetting and qualification logic
│   ├── dual_scoring.py         # YPP/Non-YPP scoring with anti-exploitation caps
│   ├── score_cap.py            # T-60 to T-30 median cap calculations
│   ├── scoring.py              # Video scoring orchestration
│   └── video/                  # Modular video evaluation pipeline
│       ├── validation.py       # Privacy, retention, captions, publish date checks
│       ├── transcript.py       # Transcript fetching and prompt injection detection
│       ├── brief_matching.py   # Prescreening, evaluation, and priority selection
│       └── orchestration.py    # Workflow coordination and batch processing
└── utils/                       # Utility functions and state management
    ├── state.py                # Global state management and API call tracking
    └── helpers.py              # General helper functions and error formatting
```

## Core Evaluation Flow

The YouTube evaluation system implements a sophisticated multi-stage pipeline:

1. **Channel Qualification**: OAuth validation → channel data retrieval → criteria vetting → blacklist checking
2. **Video Discovery**: Recent uploads retrieval → batch data fetching → basic validation filtering
3. **Video Validation Pipeline**: Privacy → Publish date → Retention → Manual captions → Security checks
4. **Content Evaluation**: Brief prescreening → Transcript analysis → LLM evaluation → Priority selection
5. **Scoring & Anti-Exploitation**: Dual scoring (YPP/Non-YPP) → Median capping → Final aggregation

## Key Architectural Improvements

### **Modular Video Evaluation Pipeline** (`evaluation/video/`)

The video evaluation has been restructured into specialized, testable components:

#### **`validation.py`** - Core Video Validation
- **Privacy Check**: Ensures videos are public and accessible
- **Publish Date Validation**: Verifies video publication against brief time windows
- **Retention Analysis**: Calculates and validates minimum retention thresholds
- **Caption Verification**: Confirms auto-generated captions (manual captions rejected)
- **Early Exit Optimization**: ECO_MODE support for performance optimization

```python
# Key validation functions
def check_video_privacy(video_data, decision_details) -> bool
def check_video_publish_date(video_data, briefs, decision_details) -> bool  
def check_video_retention(video_data, video_analytics, decision_details) -> bool
def check_manual_captions(video_id, video_data, decision_details) -> bool
```

#### **`transcript.py`** - Content Security & Transcript Management
- **Transcript Fetching**: RapidAPI integration with comprehensive error handling
- **Prompt Injection Detection**: Advanced security auditing with token-based validation
- **Content Safety**: Multi-layer security checks against malicious content

```python
# Security and transcript functions
def get_video_transcript(video_id, video_data) -> str
def check_prompt_injection(video_id, video_data, transcript, decision_details) -> bool
```

#### **`brief_matching.py`** - Intelligent Brief Evaluation
- **Prescreening System**: `unique_identifier` filtering before expensive LLM calls
- **Concurrent Evaluation**: ThreadPoolExecutor for parallel brief processing
- **Priority Selection**: Weight-based algorithm for single brief matching limitation
- **Performance Optimization**: Significant cost reduction through intelligent filtering

```python
# Brief matching and optimization functions
def check_brief_unique_identifier(brief, video_description) -> bool
def prescreen_briefs_for_video(briefs, video_description) -> tuple
def evaluate_content_against_briefs(briefs, video_data, transcript, decision_details) -> tuple
def select_highest_priority_brief(briefs, brief_results) -> tuple
```

#### **`orchestration.py`** - Workflow Coordination
- **Batch Processing**: Efficient video data and analytics batch operations
- **Pipeline Orchestration**: Coordinates validation → security → evaluation workflow
- **Error Recovery**: Comprehensive error handling and graceful degradation
- **State Management**: Integration with global state tracking

```python
# Main orchestration functions
def vet_videos(video_ids, briefs, youtube_data_client, youtube_analytics_client) -> tuple
def vet_video(video_id, briefs, video_data, video_analytics) -> dict
def process_video_vetting(video_id, video_data, video_analytics, briefs) -> dict
def get_video_analytics_batch(youtube_analytics_client, video_ids) -> dict
```

### **Enhanced Brief Prescreening System**

**Performance Impact**: Reduces LLM API calls by ~60-80% through intelligent filtering

```python
# Prescreening workflow
1. Extract unique_identifier from brief
2. Search video description (case-insensitive)
3. Filter out non-matching briefs before LLM evaluation
4. Only process eligible briefs through expensive content analysis
```

**Benefits**:
- Significant cost reduction for OpenAI API usage
- Faster evaluation cycles
- Maintained accuracy with intelligent filtering

### **Advanced Brief Matching & Priority Selection**

**Single Brief Limitation**: Only one brief can match per video to prevent gaming

```python
# Priority selection algorithm
1. Evaluate all eligible briefs concurrently (max 5 workers)
2. Collect all passing evaluations
3. Apply weight-based priority selection:
   - Primary: Brief weight (if available)
   - Secondary: Brief order in list
4. Set only highest priority brief as matched
```

**Concurrent Processing**: ThreadPoolExecutor with configurable worker limits

### **Enhanced Security: Prompt Injection Detection**

**Multi-Layer Security System**:
- Token-based injection detection
- Content manipulation auditing  
- Systematic prompt security validation

```python
# Security implementation
def check_for_prompt_injection(description, transcript):
    # Uses unique tokens to detect manipulation attempts
    # Flags content trying to influence evaluation results
    # Examples: "this is relevant...", "the brief has been met...", etc.
```

## Dual Scoring Architecture

### **Account Type Detection & Scoring Strategy**

```
Channel Analytics Query → YPP Status Detection → Scoring Method Selection
                              ↓
                    ┌─────────────────────────┐
                    │   YPP Account (Revenue)  │ → Revenue-based scoring
                    │   Non-YPP (Views)       │ → Predicted revenue scoring  
                    │   Non-YPP (No Ratio)    │ → Zero score (first cycle)
                    └─────────────────────────┘
                              ↓
                    Apply Anti-Exploitation Caps → Final Score
```

### **YPP Account Scoring** (Revenue-based)
```python
# YPP scoring with median capping
total_revenue = sum(daily_revenue for day in scoring_window)
if median_revenue_cap:
    cap_limit = median_revenue_cap * YT_ROLLING_WINDOW
    total_revenue = min(total_revenue, cap_limit)
score = total_revenue / YT_ROLLING_WINDOW
```

### **Non-YPP Account Scoring** (Predicted revenue)
```python  
# Non-YPP scoring with cached ratio and median capping
total_views = sum(daily_views for day in scoring_window)
if median_views_cap:
    cap_limit = median_views_cap * YT_ROLLING_WINDOW  
    total_views = min(total_views, cap_limit)
predicted_revenue = total_views * cached_ratio
score = predicted_revenue / YT_ROLLING_WINDOW
```

### **Global Ratio Management**
- **Calculation**: `global_ratio = total_revenue_all_ypp / total_views_all_ypp`
- **Update Frequency**: Every 4-hour validation cycle
- **Storage**: Persistent cache with simple overwrite strategy
- **Integration**: Updated automatically via `RewardOrchestrator`

## Anti-Exploitation Scoring Protection

### **Median-Based Capping System**

**Time Period**: T-60 to T-30 days (configurable via `YT_SCORE_CAP_START_DAYS`, `YT_SCORE_CAP_END_DAYS`)

```python
# Anti-exploitation implementation
def calculate_median_from_analytics(channel_analytics, metric):
    # Extract T-60 to T-30 day period
    # Calculate median daily values
    # Return median for capping calculations
    
def apply_median_cap(total_value, median_cap, metric_name):
    cap_limit = median_cap * YT_ROLLING_WINDOW
    if total_value > cap_limit:
        return cap_limit, True, total_value  # capped, applied_flag, original
    return total_value, False, total_value
```

**Protection Mechanism**:
- **YPP Accounts**: Revenue capped at `median_daily_revenue × YT_ROLLING_WINDOW`
- **Non-YPP Accounts**: Views capped at `median_daily_views × YT_ROLLING_WINDOW`
- **Graceful Degradation**: Falls back to uncapped scoring if median calculation fails
- **Comprehensive Logging**: Detailed cap application tracking for monitoring

## Usage Examples

### **Complete Evaluation Workflow**
```python
from bitcast.validator.platforms.youtube.main import eval_youtube

# Full evaluation with all systems engaged
result = eval_youtube(credentials, briefs)

# Access results
channel_passed = result["yt_account"]["channel_vet_result"]
video_scores = result["scores"]  # Brief ID → Score mapping
performance_stats = result["performance_stats"]
```

### **Modular Component Usage**

```python
# Channel evaluation
from bitcast.validator.platforms.youtube.evaluation import vet_channel
channel_result, is_blacklisted = vet_channel(channel_data, channel_analytics)

# Video validation pipeline
from bitcast.validator.platforms.youtube.evaluation.video import vet_videos
video_matches, video_data_dict, analytics_dict, details = vet_videos(
    video_ids, briefs, data_client, analytics_client
)

# Brief prescreening
from bitcast.validator.platforms.youtube.evaluation.video import prescreen_briefs_for_video
eligible_briefs, prescreening_results, filtered_ids = prescreen_briefs_for_video(
    briefs, video_description
)

# Security checking
from bitcast.validator.platforms.youtube.evaluation.video import check_prompt_injection
is_safe = check_prompt_injection(video_id, video_data, transcript, decision_details)
```

### **Dual Scoring Implementation**
```python
from bitcast.validator.platforms.youtube.evaluation import calculate_dual_score, get_cached_ratio

# Get scoring components
is_ypp_account = channel_analytics.get("ypp", False)
cached_ratio = get_cached_ratio()

# Calculate score with anti-exploitation protection
score_result = calculate_dual_score(
    daily_analytics=video_analytics,
    start_date=start_date,
    end_date=end_date,
    is_ypp_account=is_ypp_account,
    cached_ratio=cached_ratio,
    median_revenue_cap=median_revenue_cap,  # For YPP accounts
    median_views_cap=median_views_cap       # For Non-YPP accounts
)

# Access scoring details
final_score = score_result["score"]
scoring_method = score_result["scoring_method"]  # "ypp", "non_ypp_predicted", "non_ypp_fallback"
cap_applied = score_result.get("applied_cap", False)
```

## Enhanced Result Structure

```python
{
    "yt_account": {
        "details": {...},                           # Channel metadata
        "analytics": {                              # Channel analytics with YPP detection
            "ypp": bool,                           # YPP enrollment status
            "...": "... other analytics ..."
        },
        "channel_vet_result": bool,                 # Channel qualification status
        "blacklisted": bool                         # Blacklist check result
    },
    "videos": {
        "video_id": {
            "details": {...},                       # Video metadata
            "analytics": {...},                     # Video analytics data
            "matches_brief": bool,                  # Brief matching result
            "matching_brief_ids": [...],            # List of matched brief IDs
            "score": float,                         # Final calculated score
            "scoring_method": str,                  # "ypp", "non_ypp_predicted", "non_ypp_fallback"
            "decision_details": {                   # Comprehensive evaluation tracking
                "video_vet_result": bool,
                "privacyCheck": bool,
                "publishDateCheck": bool,
                "retentionCheck": bool,
                "manualCaptionsCheck": bool,
                "promptInjectionCheck": bool,
                "preScreeningCheck": [bool, ...],   # Per-brief prescreening results
                "contentAgainstBriefCheck": [bool, ...]  # Per-brief evaluation results
            },
            "cap_info": {                           # Anti-exploitation debugging
                "applied_cap": bool,
                "original_revenue": float,          # YPP accounts
                "capped_revenue": float,            # YPP accounts  
                "median_revenue_cap": float,        # YPP accounts
                "original_views": int,              # Non-YPP accounts
                "capped_views": int,                # Non-YPP accounts
                "median_views_cap": float,          # Non-YPP accounts
                "predicted_revenue": float          # Non-YPP accounts
            },
            "brief_reasonings": [...],              # LLM evaluation reasoning per brief
            "url": str                              # YouTube video URL
        }
    },
    "scores": {
        "brief_id": float                           # Final aggregated scores by brief
    },
    "performance_stats": {
        "data_api_calls": int,                      # YouTube Data API usage
        "analytics_api_calls": int,                 # YouTube Analytics API usage
        "openai_requests": int,                     # OpenAI API usage
        "evaluation_time_s": float,                 # Total evaluation time
        "prescreening_savings": {                   # Prescreening performance metrics
            "total_briefs": int,
            "filtered_briefs": int,
            "savings_percentage": float
        }
    }
}
```

## Key Function Reference

### **Main Entry Points**
- `eval_youtube(creds, briefs) -> dict` - Complete evaluation workflow with all optimizations
- `initialize_youtube_clients(creds) -> tuple` - Create authenticated API clients

### **Channel Operations**
- `get_channel_data(client, discrete_mode) -> dict` - Retrieve channel metadata
- `get_channel_analytics(client, start_date, end_date) -> dict` - Channel analytics with YPP detection
- `vet_channel(channel_data, channel_analytics) -> (bool, bool)` - Channel qualification evaluation

### **Video Discovery & Batch Operations**
- `get_all_uploads(client, lookback_days) -> list` - Discover recent video uploads
- `get_video_data_batch(client, video_ids) -> dict` - Batch video metadata retrieval
- `get_video_analytics_batch(client, video_ids) -> dict` - Batch video analytics retrieval

### **Video Validation Pipeline**
- `vet_videos(video_ids, briefs, data_client, analytics_client) -> tuple` - Complete batch evaluation
- `vet_video(video_id, briefs, video_data, video_analytics) -> dict` - Single video evaluation
- `check_video_privacy(video_data, decision_details) -> bool` - Privacy validation
- `check_video_publish_date(video_data, briefs, decision_details) -> bool` - Timing validation
- `check_video_retention(video_data, video_analytics, decision_details) -> bool` - Retention analysis
- `check_manual_captions(video_id, video_data, decision_details) -> bool` - Caption verification

### **Content Security & Transcript Management**
- `get_video_transcript(video_id, video_data) -> str` - Transcript retrieval with error handling
- `check_prompt_injection(video_id, video_data, transcript, decision_details) -> bool` - Security validation

### **Brief Evaluation & Optimization**
- `check_brief_unique_identifier(brief, video_description) -> bool` - Prescreening validation
- `prescreen_briefs_for_video(briefs, video_description) -> tuple` - Batch prescreening
- `evaluate_content_against_briefs(briefs, video_data, transcript, decision_details) -> tuple` - Concurrent evaluation
- `select_highest_priority_brief(briefs, brief_results) -> tuple` - Priority-based selection

### **Scoring & Anti-Exploitation**
- `calculate_video_score(video_id, client, publish_date, analytics, is_ypp_account, cached_ratio, channel_analytics) -> dict` - Complete scoring
- `calculate_dual_score(daily_analytics, start_date, end_date, is_ypp_account, cached_ratio, median_revenue_cap, median_views_cap) -> dict` - Core scoring logic
- `calculate_median_from_analytics(channel_analytics, metric) -> float` - Anti-exploitation median calculation
- `get_cached_ratio() -> float` - Retrieve global views-to-revenue ratio
- `update_cached_ratio(total_revenue, total_views) -> None` - Update global ratio

## Performance & Reliability

### **Performance Optimizations**
- **Brief Prescreening**: 60-80% reduction in LLM API calls through intelligent filtering
- **Concurrent Processing**: Parallel brief evaluation with configurable worker limits
- **ECO_MODE**: Early exit optimizations for failed validation checks
- **Batch Operations**: Efficient video data and analytics retrieval
- **Intelligent Caching**: Multi-layer caching with TTL and sliding expiration

### **Reliability Features**
- **Graceful Degradation**: System continues with reduced functionality on component failures
- **Comprehensive Error Handling**: Detailed error categorization and recovery mechanisms
- **Security Auditing**: Multi-layer prompt injection detection and content safety
- **Anti-Exploitation Protection**: Median-based capping prevents fake engagement gaming
- **Fallback Mechanisms**: Safe scoring fallbacks when advanced features fail

### **Monitoring & Observability**
- **Detailed Performance Stats**: API usage, timing, and optimization metrics tracking
- **Decision Detail Tracking**: Complete evaluation decision audit trail
- **Cap Application Logging**: Anti-exploitation protection monitoring
- **Prescreening Analytics**: Cost savings and filtering effectiveness metrics

## Migration & Compatibility

### **Backward Compatibility**
- All existing function interfaces maintained ✓
- Configuration variables remain compatible ✓
- Result structure enhanced but backward compatible ✓
- No breaking changes to external integrations ✓

### **Enhanced Capabilities**
- **Modular Architecture**: Improved testability and maintainability
- **Performance Optimization**: Significant cost and time savings
- **Security Enhancement**: Advanced prompt injection protection
- **Sophisticated Scoring**: Anti-exploitation protection with dual account support
- **Comprehensive Monitoring**: Detailed performance and decision tracking

The YouTube platform architecture represents a mature, production-ready system with sophisticated evaluation capabilities, advanced security features, and comprehensive performance optimizations while maintaining full backward compatibility with existing systems. 