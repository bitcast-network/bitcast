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
│   ├── curve_based_scoring.py  # Main curve-based scoring orchestration
│   ├── curve_scoring.py        # Core curve calculation functions
│   ├── data_processing.py      # Data utilities for curve scoring
│   ├── median_capping.py       # T-60 to T-30 median cap calculations
│   ├── score_cap.py            # Legacy median cap utilities
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
5. **Scoring & Anti-Exploitation**: Curve-based scoring (YPP/Non-YPP) → Median capping → Diminishing returns calculation

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
def vet_videos(video_ids, briefs, youtube_data_client, youtube_analytics_client, is_ypp_account=True) -> tuple
def vet_video(video_id, briefs, video_data, video_analytics) -> dict
def process_video_vetting(video_id, video_data, video_analytics, briefs) -> dict
def get_video_analytics_batch(youtube_analytics_client, video_ids, is_ypp_account=True) -> dict
```

### **Enhanced Brief Prescreening System**

**Performance Impact**: Reduces LLM API calls by ~60-80% through intelligent filtering

```python
# Optimized prescreening workflow (moved before expensive operations)
1. Extract unique_identifier from brief
2. Search video description (case-insensitive)  
3. Check publish date validation
4. Filter out non-matching briefs before transcript fetch and LLM evaluation
5. Only process eligible briefs through expensive transcript and content analysis
```

**Benefits**:
- Significant cost reduction for LLM API usage and transcript API calls
- Faster evaluation cycles with early exit for non-matching videos
- Maintained accuracy with intelligent filtering
- Skips both transcript fetch and prompt injection check when no briefs match

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

## Curve-Based Scoring Architecture

### **Account Type Detection & Scoring Strategy**

```
Channel Analytics Query → YPP Status Detection → Scoring Method Selection
                              ↓
                    ┌─────────────────────────┐
                    │   YPP Account (Revenue)  │ → Revenue-based curve scoring
                    │   Non-YPP (MinutesWatched)│ → Estimated revenue curve scoring
                    └─────────────────────────┘
                              ↓
                    Apply Anti-Exploitation Caps → Final Score
```

### **Curve-Based Scoring Formula**
```python
# Core diminishing returns curve formula
def calculate_curve_value(value):
    return SQRT(value) / (1 + DAMPENING_FACTOR * SQRT(value))

# Score calculation: difference between two consecutive 7-day periods
day1_avg = 7_day_cumulative_average(T-10 to T-4)  # Earlier period
day2_avg = 7_day_cumulative_average(T-9 to T-3)   # Later period  
score = calculate_curve_value(day2_avg) - calculate_curve_value(day1_avg)
```

### **YPP Account Scoring** (Actual Revenue)
```python
# Standard YPP accounts with revenue > 0: "ypp_curve_based"
# 1. Apply median capping to daily revenue (T-60 to T-30 median)
# 2. Calculate cumulative revenue totals
# 3. Calculate 7-day rolling averages for both periods
# 4. Apply curve formula to difference
metric = "estimatedRedPartnerRevenue"
day1_avg, day2_avg = get_period_averages(daily_analytics, metric, ...)
score = calculate_curve_difference(day1_avg, day2_avg)
```

### **YPP Zero-Revenue Account Scoring** (Stake-Based)
```python
# YPP accounts with revenue = 0 are evaluated based on stake requirements:
# - If min_stake = True: "ypp_zero_revenue" (uses Non-YPP scoring method)
# - If min_stake = False: "ypp_zero_revenue_no_stake" (score = 0)

if total_revenue == 0.0 and min_stake:
    # Route to Non-YPP scoring method with YPP zero-revenue identifier
    score = calculate_non_ypp_curve_score(...)
    scoring_method = "ypp_zero_revenue"
else:
    # No stake requirements met
    score = 0.0
    scoring_method = "ypp_zero_revenue_no_stake"
```

### **Non-YPP Account Scoring** (Estimated Revenue)
```python
# Standard non-YPP accounts: "non_ypp_curve_based"
# 1. Apply median capping to daily minutes watched (T-60 to T-30 median)  
# 2. Calculate cumulative minutes watched totals
# 3. Calculate 7-day rolling averages for both periods
# 4. Convert to estimated revenue using hardcoded multiplier
# 5. Apply curve formula to difference
metric = "estimatedMinutesWatched"
day1_avg, day2_avg = get_period_averages(daily_analytics, metric, ...)
day1_revenue = day1_avg * YT_NON_YPP_REVENUE_MULTIPLIER  # 0.00005
day2_revenue = day2_avg * YT_NON_YPP_REVENUE_MULTIPLIER
score = calculate_curve_difference(day1_revenue, day2_revenue)
```

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

### **Curve-Based Scoring Implementation**
```python
from bitcast.validator.platforms.youtube.evaluation import calculate_video_score

# Get scoring components
is_ypp_account = channel_analytics.get("ypp", False)
channel_analytics = result["yt_account"]["analytics"]

# Calculate score with integrated anti-exploitation protection and curve formula
score_result = calculate_video_score(
    video_id=video_id,
    youtube_analytics_client=analytics_client,
    video_publish_date=video_publish_date,
    existing_analytics=existing_analytics,
    is_ypp_account=is_ypp_account,
    channel_analytics=channel_analytics
)

# Access scoring details
final_score = score_result["score"]
scoring_method = score_result["scoring_method"]  # "ypp_curve_based", "non_ypp_curve_based", "ypp_zero_revenue", "ypp_zero_revenue_no_stake"
day1_avg = score_result.get("day1_average", 0)
day2_avg = score_result.get("day2_average", 0)
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
            "scoring_method": str,                  # "ypp_curve_based", "non_ypp_curve_based", "ypp_zero_revenue", "ypp_zero_revenue_no_stake"
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
        "chutes_requests": int,                     # Chutes API usage
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
- `calculate_video_score(video_id, client, publish_date, analytics, is_ypp_account, channel_analytics, bitcast_video_id) -> dict` - Complete curve-based scoring
- `calculate_curve_based_score(daily_analytics, start_date, end_date, is_ypp_account, channel_analytics, video_id) -> dict` - Core curve scoring logic
- `calculate_curve_value(value) -> float` - Diminishing returns curve calculation
- `calculate_curve_difference(day1_avg, day2_avg) -> float` - Score difference on curve
- `apply_median_caps_to_analytics(daily_analytics, channel_analytics, is_ypp_account) -> list` - Anti-exploitation capping
- `get_period_averages(daily_analytics, metric_key, day1_start, day1_end, day2_start, day2_end, window_size, channel_analytics, is_ypp_account) -> tuple` - Rolling average calculation

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