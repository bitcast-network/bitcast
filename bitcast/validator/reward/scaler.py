"""Reward scaling mathematics: curve scoring, median-threshold scaling, emission constraints.

Pure functions ported from the v1 evaluation pipeline. The dampened square-root
curve turns raw daily revenue into diminishing-return scores; proportional
scaling caps a scoring period at the channel's historical median (v1's unwired
per-day "median capping" module was superseded by this); emission constraints
turn per-brief USD weights into a normalized reward vector with the burn UID
absorbing any unallocated remainder.
"""

import math
import statistics
from datetime import date, timedelta

import numpy as np

from bitcast.config import (
    BURN_UID,
    SUBNET_TREASURY_PERCENTAGE,
    SUBNET_TREASURY_UID,
    YT_CURVE_DAMPENING_FACTOR,
    YT_MIN_EMISSIONS,
    YT_SCORE_CAP_END_DAYS,
    YT_SCORE_CAP_START_DAYS,
)

# --- Curve scoring -----------------------------------------------------------


def calculate_curve_value(value: float) -> float:
    """Dampened square-root curve: sqrt(v) / (1 + d*sqrt(v)); 0 for non-positive input."""
    if value <= 0 or not math.isfinite(value):
        return 0.0
    sqrt_value = math.sqrt(value)
    return sqrt_value / (1 + YT_CURVE_DAMPENING_FACTOR * sqrt_value)


def calculate_curve_difference(day1_avg: float, day2_avg: float) -> float:
    """Score as growth along the curve between two period averages."""
    return calculate_curve_value(day2_avg) - calculate_curve_value(day1_avg)


def calculate_adjusted_curve_difference(
    day1_avg: float, day2_avg: float, scaling_factor: float, lifetime_deduction: float
) -> float:
    """Curve difference with a lifetime deduction applied as a curve-space threshold.

    Both period curve values are floored at ``lifetime_deduction / scaling_factor``
    so a video only earns once its curve value clears the deduction.
    """
    if scaling_factor <= 0 or lifetime_deduction <= 0:
        return calculate_curve_difference(day1_avg, day2_avg)
    threshold = lifetime_deduction / scaling_factor
    day1_curve = calculate_curve_value(day1_avg)
    day2_curve = calculate_curve_value(day2_avg)
    return max(day2_curve - threshold, 0) - max(day1_curve - threshold, 0)


# --- Daily-series helpers ----------------------------------------------------

DAY_FORMAT = "%Y-%m-%d"


def fill_missing_dates(daily: list[dict], start: date, end: date) -> list[dict]:
    """Zero-fill every metric for every day in [start, end], sorted by day."""
    metric_keys = {key for entry in daily for key in entry if key != "day"}
    by_day = {entry["day"]: entry for entry in daily}
    filled = []
    current = start
    while current <= end:
        day_str = current.strftime(DAY_FORMAT)
        entry = by_day.get(day_str, {})
        filled.append({"day": day_str, **{key: entry.get(key, 0) for key in metric_keys}})
        current += timedelta(days=1)
    return filled


def extract_date_range(daily: list[dict], start: date, end: date) -> list[dict]:
    """Entries whose day falls within [start, end]."""
    start_str, end_str = start.strftime(DAY_FORMAT), end.strftime(DAY_FORMAT)
    return [entry for entry in daily if start_str <= entry["day"] <= end_str]


def calculate_cumulative_totals(daily: list[dict], metric_key: str) -> list[dict]:
    """Append a running ``cumulative_<metric>`` field to each entry."""
    total = 0.0
    result = []
    for entry in daily:
        total += float(entry.get(metric_key, 0) or 0)
        result.append({**entry, f"cumulative_{metric_key}": total})
    return result


def rolling_average_endpoint(values: list[float], window: int) -> float:
    """Mean of the trailing ``window`` values at the end of the series; 0 if empty."""
    if not values:
        return 0.0
    tail = values[-window:] if window > 0 else values
    return sum(tail) / len(tail)


# --- Median-threshold (proportional) scaling ---------------------------------


def median_threshold_window(today: date) -> tuple[date, date]:
    """The historical window used for median thresholds: T-60 .. T-30."""
    return (
        today - timedelta(days=YT_SCORE_CAP_START_DAYS),
        today - timedelta(days=YT_SCORE_CAP_END_DAYS),
    )


def median_from_daily_values(daily_values: dict[str, float], start: date, end: date) -> float:
    """Median daily value over [start, end], counting missing days as zero."""
    values = []
    current = start
    while current <= end:
        values.append(float(daily_values.get(current.strftime(DAY_FORMAT), 0.0) or 0.0))
        current += timedelta(days=1)
    if not values:
        return 0.0
    return float(statistics.median(values))


def calculate_scaling_factor(period_average: float, threshold: float) -> float | None:
    """Factor that scales a period average down to the threshold.

    Returns None when no scaling is needed (average within threshold);
    0.0 when the threshold itself is non-positive.
    """
    if threshold <= 0.0:
        return 0.0
    if period_average <= threshold:
        return None
    return threshold / period_average


def apply_proportional_scaling(daily: list[dict], metric_key: str, threshold: float) -> list[dict]:
    """Scale a period's daily metric so its average does not exceed the threshold."""
    values = [float(entry.get(metric_key, 0) or 0) for entry in daily]
    if not values:
        return daily
    period_average = sum(values) / len(values)
    factor = calculate_scaling_factor(period_average, threshold)
    if factor is None:
        return daily
    return [{**entry, metric_key: float(entry.get(metric_key, 0) or 0) * factor} for entry in daily]


def get_period_averages(
    daily_analytics: list[dict],
    metric_key: str,
    day1_start: date,
    day1_end: date,
    day2_start: date,
    day2_end: date,
    window: int,
    period2_median_threshold: float | None = None,
) -> tuple[float, float]:
    """Rolling averages of the cumulative metric at the end of two scoring periods.

    Pipeline: zero-fill the full date range, proportionally scale period 2 down
    to the median threshold (anti-exploitation), accumulate, then take the
    trailing ``window``-day rolling average of the cumulative series in each
    period.
    """
    try:
        data_days = [entry["day"] for entry in daily_analytics if "day" in entry]
        overall_start = min([day1_start] + [date.fromisoformat(day) for day in data_days])
        overall_end = max(day2_end, day1_end)
        filled = fill_missing_dates(daily_analytics, overall_start, overall_end)

        if period2_median_threshold is not None:
            period2 = extract_date_range(filled, day2_start, day2_end)
            scaled = apply_proportional_scaling(period2, metric_key, period2_median_threshold)
            scaled_by_day = {entry["day"]: entry for entry in scaled}
            filled = [scaled_by_day.get(entry["day"], entry) for entry in filled]

        cumulative = calculate_cumulative_totals(filled, metric_key)
        cumulative_key = f"cumulative_{metric_key}"

        def period_endpoint(start: date, end: date) -> float:
            period = extract_date_range(cumulative, start, end)
            return rolling_average_endpoint([entry[cumulative_key] for entry in period], window)

        return period_endpoint(day1_start, day1_end), period_endpoint(day2_start, day2_end)
    except (KeyError, ValueError, TypeError):
        return 0.0, 0.0


# --- Emission constraints and final reward vector ----------------------------


def apply_emission_constraints(weights_matrix: np.ndarray, briefs: list[dict]) -> np.ndarray:
    """Cap each brief column at its ``cap`` and the grand total at 1.0.

    Order matters: per-brief caps first, then the (currently zero) global
    floor, then normalize down if the total exceeds the full emission budget.
    Totals below 1.0 are left as-is — the burn UID absorbs the remainder.
    """
    result = weights_matrix.copy()

    for brief_idx, brief in enumerate(briefs):
        brief_cap = brief.get("cap", 1.0)
        brief_sum = result[:, brief_idx].sum()
        if brief_sum > brief_cap:
            result[:, brief_idx] *= brief_cap / brief_sum

    total = result.sum()
    if 0 < total < YT_MIN_EMISSIONS:
        result *= YT_MIN_EMISSIONS / total
        total = result.sum()

    if total > 1.0:
        result /= total
    return result


def sum_to_final_rewards(weights_matrix: np.ndarray, uids: list[int]) -> np.ndarray:
    """Sum each miner's weights across briefs; the burn UID absorbs the remainder to 1.0."""
    rewards = weights_matrix.sum(axis=1)
    burn_idx = next((i for i, uid in enumerate(uids) if uid == BURN_UID), None)
    if burn_idx is not None:
        other_sum = rewards.sum() - rewards[burn_idx]
        rewards[burn_idx] = max(1.0 - other_sum, 0.0)
    return rewards


def allocate_subnet_treasury(rewards: np.ndarray, uids: list[int]) -> np.ndarray:
    """Move up to ``SUBNET_TREASURY_PERCENTAGE`` from the burn UID to the treasury UID."""
    if len(rewards) == 0 or SUBNET_TREASURY_PERCENTAGE <= 0:
        return rewards
    uids_array = np.asarray(uids)
    burn_matches = np.where(uids_array == BURN_UID)[0]
    treasury_matches = np.where(uids_array == SUBNET_TREASURY_UID)[0]
    if len(burn_matches) == 0 or len(treasury_matches) == 0:
        return rewards
    result = rewards.copy()
    allocation = min(SUBNET_TREASURY_PERCENTAGE, result[burn_matches[0]])
    result[burn_matches[0]] -= allocation
    result[treasury_matches[0]] += allocation
    return result
