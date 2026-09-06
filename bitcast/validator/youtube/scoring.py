"""Channel vetting, video vetting and curve-based video scoring."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import bittensor as bt

from bitcast.config import (
    YT_LIFETIME_DEDUCTION,
    YT_LIFETIME_DEDUCTION_AD_READ,
    YT_LIFETIME_DEDUCTION_PRODUCT_PLACEMENT,
    YT_LOOKBACK,
    YT_MAX_SUBS,
    YT_MIN_CHANNEL_AGE,
    YT_MIN_CHANNEL_RETENTION,
    YT_MIN_MINS_WATCHED,
    YT_MIN_SUBS,
    YT_REWARD_DELAY,
    YT_ROLLING_WINDOW,
    YT_SCALING_FACTOR_AD_READ,
    YT_SCALING_FACTOR_DEDICATED,
    YT_SCALING_FACTOR_PRODUCT_PLACEMENT,
    YT_SCORING_WINDOW,
    YT_VIDEO_RELEASE_BUFFER,
)
from bitcast.validator.reward import scaler
from bitcast.validator.youtube.api import YouTubeClient
from bitcast.validator.youtube.timestamps import parse_timestamp

REVENUE_METRIC = "estimatedRedPartnerRevenue"
MINUTES_METRIC = "estimatedMinutesWatched"

_SCALING_FACTORS = {
    "dedicated": YT_SCALING_FACTOR_DEDICATED,
    "ad-read": YT_SCALING_FACTOR_AD_READ,
    "integration": YT_SCALING_FACTOR_AD_READ,
    "productPlacement": YT_SCALING_FACTOR_PRODUCT_PLACEMENT,
}
_LIFETIME_DEDUCTIONS = {
    "dedicated": YT_LIFETIME_DEDUCTION,
    "ad-read": YT_LIFETIME_DEDUCTION_AD_READ,
    "integration": YT_LIFETIME_DEDUCTION_AD_READ,
    "productPlacement": YT_LIFETIME_DEDUCTION_PRODUCT_PLACEMENT,
}


def format_scaling_factor(brief_format: str) -> float:
    """USD scaling factor for a brief format; unknown formats score as dedicated."""
    if brief_format not in _SCALING_FACTORS:
        bt.logging.warning(f"Unknown brief format '{brief_format}'; using dedicated scaling.")
    return _SCALING_FACTORS.get(brief_format, YT_SCALING_FACTOR_DEDICATED)


def format_lifetime_deduction(brief_format: str) -> float:
    """Lifetime USD deduction for a brief format; unknown formats use dedicated."""
    return _LIFETIME_DEDUCTIONS.get(brief_format, YT_LIFETIME_DEDUCTION)


# --- Channel vetting ---------------------------------------------------------


def vet_channel(channel_data: dict, channel_analytics: dict, today: date | None = None) -> tuple[bool, dict[str, bool]]:
    """Apply all channel acceptance gates; every check must pass.

    Acceptance requires affirmative YouTube Partner Program membership. There
    is no alternative route: alpha stake no longer substitutes for YPP.
    """
    today = today or datetime.now(UTC).date()
    checks: dict[str, bool] = {}

    checks["acceptance"] = bool(channel_analytics.get("ypp", False))

    channel_start = parse_timestamp(channel_data.get("channel_start", ""))
    age_days = (datetime.now(UTC) - channel_start).days if channel_start else 0
    checks["channel_age"] = age_days >= YT_MIN_CHANNEL_AGE

    sub_count = int(channel_data.get("subCount", 0) or 0)
    checks["min_subs"] = sub_count >= YT_MIN_SUBS
    checks["max_subs"] = sub_count <= YT_MAX_SUBS

    checks["retention"] = float(channel_analytics.get("averageViewPercentage", 0) or 0) >= YT_MIN_CHANNEL_RETENTION

    minutes = channel_analytics.get(MINUTES_METRIC, {}) or {}
    checks["minutes_watched"] = sum(minutes.values()) >= YT_MIN_MINS_WATCHED

    passed = all(checks.values())
    if not passed:
        failed = [name for name, ok in checks.items() if not ok]
        bt.logging.info(f"Channel vetting failed: {failed}")
    return passed, checks


# --- Video vetting -----------------------------------------------------------


def vet_video(video_data: dict, briefs: list[dict], today: date | None = None) -> dict[str, bool]:
    """Basic per-video gates that apply regardless of which brief is targeted."""
    today = today or datetime.now(UTC).date()
    published = parse_timestamp(video_data.get("publishedAt", ""))
    checks: dict[str, bool] = {}

    checks["public_video"] = video_data.get("privacyStatus") == "public"

    if briefs and published is not None:
        earliest_start = min(date.fromisoformat(brief["start_date"]) for brief in briefs)
        allowed_start = earliest_start - timedelta(days=YT_VIDEO_RELEASE_BUFFER)
        checks["publish_date"] = published.date() >= allowed_start
    else:
        checks["publish_date"] = published is not None

    age_cutoff = today - timedelta(days=YT_SCORING_WINDOW + YT_REWARD_DELAY)
    checks["age_limit"] = published is not None and published.date() >= age_cutoff

    checks["auto_captions_only"] = str(video_data.get("caption", "false")).lower() != "true"

    checks["video_vet_result"] = all(checks.values())
    return checks


# --- Video scoring ------------------------------------------------------------


def _scoring_windows(today: date) -> tuple[date, date, date, date]:
    """Two consecutive rolling windows offset by one day: T-10..T-4 and T-9..T-3."""
    day1_start = today - timedelta(days=YT_REWARD_DELAY + YT_ROLLING_WINDOW)
    day1_end = today - timedelta(days=YT_REWARD_DELAY + 1)
    day2_start = today - timedelta(days=YT_REWARD_DELAY + YT_ROLLING_WINDOW - 1)
    day2_end = today - timedelta(days=YT_REWARD_DELAY)
    return day1_start, day1_end, day2_start, day2_end


def _median_threshold(channel_analytics: dict, metric_key: str, today: date) -> float:
    """Median daily channel value of the metric over the T-60..T-30 window."""
    window_start, window_end = scaler.median_threshold_window(today)
    daily_values = channel_analytics.get(metric_key, {}) or {}
    return scaler.median_from_daily_values(daily_values, window_start, window_end)


async def calculate_video_score(
    client: YouTubeClient,
    video_id: str,
    published_at: str,
    is_ypp_account: bool,
    channel_analytics: dict,
    today: date | None = None,
) -> dict[str, Any]:
    """Score one video from the growth of its cumulative revenue curve.

    Only *positive* YouTube Partner Program revenue is scoreable. A non-YPP
    account scores zero without spending analytics quota, and a YPP video whose
    windowed revenue is not positive scores zero — watch time is never a
    substitute, and a net-negative total (chargebacks, revenue adjustments)
    must never reach the reward curve. Period 2 is proportionally scaled down
    to the channel's historical median to blunt engagement-buying.
    """
    today = today or datetime.now(UTC).date()
    if not is_ypp_account:
        return _score_result(0.0, "non_ypp_ineligible", 0.0, 0.0, [])

    published = parse_timestamp(published_at)
    query_start = published.date() if published else today - timedelta(days=YT_LOOKBACK)

    try:
        daily_analytics = await client.get_video_daily_analytics(video_id, query_start, today)
        total_revenue = sum(float(entry.get(REVENUE_METRIC, 0) or 0) for entry in daily_analytics)
        if total_revenue <= 0.0:
            return _score_result(0.0, "ypp_zero_revenue", 0.0, 0.0, daily_analytics)
        day1, day2 = _revenue_based_averages(daily_analytics, channel_analytics, today)
        return _score_result(scaler.calculate_curve_difference(day1, day2), "ypp", day1, day2, daily_analytics)
    except Exception as err:
        bt.logging.warning(f"Video scoring failed for {video_id}: {err!r}")
        return _score_result(0.0, "curve_error_fallback", 0.0, 0.0, [])


def _revenue_based_averages(daily_analytics: list[dict], channel_analytics: dict, today: date) -> tuple[float, float]:
    day1_start, day1_end, day2_start, day2_end = _scoring_windows(today)
    threshold = _median_threshold(channel_analytics, REVENUE_METRIC, today)
    return scaler.get_period_averages(
        daily_analytics, REVENUE_METRIC, day1_start, day1_end, day2_start, day2_end, YT_ROLLING_WINDOW, threshold
    )


def _score_result(score: float, method: str, day1: float, day2: float, daily_analytics: list[dict]) -> dict[str, Any]:
    return {
        "score": score,
        "scoring_method": method,
        "curve_input_day1": day1,
        "curve_input_day2": day2,
        "daily_analytics": daily_analytics,
    }


def calculate_brief_metrics(curve_day1: float, curve_day2: float, brief: dict) -> dict[str, float]:
    """USD target for one (video, brief) pair from the video's curve inputs."""
    brief_format = brief.get("format", "dedicated")
    boost_factor = brief.get("boost", 1.0)
    if not 0.1 <= boost_factor <= 10.0:
        bt.logging.warning(f"Unusual boost factor {boost_factor} on brief {brief.get('id')}")
    scaling_factor = format_scaling_factor(brief_format)
    lifetime_deduction = format_lifetime_deduction(brief_format)
    adjusted = scaler.calculate_adjusted_curve_difference(curve_day1, curve_day2, scaling_factor, lifetime_deduction)
    return {
        "usd_target": adjusted * scaling_factor * boost_factor,
        "scaling_factor": scaling_factor,
        "boost_factor": boost_factor,
        # Reporting fields, published per (video, brief). `base_score` is the
        # raw curve difference before the lifetime deduction; `limitation_status`
        # flips to limited_fifo in apply_video_limits.
        "base_score": scaler.calculate_curve_difference(curve_day1, curve_day2),
        "brief_boost": boost_factor,
        "limitation_status": "active",
    }


def apply_video_limits(briefs: list[dict], videos: dict[str, dict], scores: dict[str, float]) -> None:
    """Enforce each brief's ``max_count`` FIFO: oldest videos keep their rewards.

    Mutates ``videos`` (zeroing usd targets of excess videos) and ``scores``
    (subtracting the removed totals).
    """
    for brief in briefs:
        max_count = brief.get("max_count")
        if max_count is None:
            continue
        max_videos = max(0, int(max_count))

        earning = [
            (video_id, video)
            for video_id, video in videos.items()
            if brief["id"] in video.get("matching_brief_ids", [])
            and video.get("brief_metrics", {}).get(brief["id"], {}).get("usd_target", 0) > 0
        ]
        if len(earning) <= max_videos:
            continue

        earning.sort(key=lambda pair: pair[1].get("details", {}).get("publishedAt", ""))
        for video_id, video in earning[max_videos:]:
            metrics = video["brief_metrics"][brief["id"]]
            scores[brief["id"]] -= metrics["usd_target"]
            metrics["usd_target"] = 0.0
            metrics["alpha_target"] = 0.0
            metrics["weight"] = 0.0
            metrics["limitation_status"] = "limited_fifo"
            bt.logging.info(f"FIFO limit: zeroed video {video_id} for brief {brief['id']}")
