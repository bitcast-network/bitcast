"""Reward scaling math: curves, period averages, constraints, burn backfill."""

from datetime import date

import numpy as np
import pytest

from bitcast.config import YT_CURVE_DAMPENING_FACTOR
from bitcast.validator.reward import scaler


class TestCurveScoring:
    def test_curve_value_zero_and_negative(self):
        assert scaler.calculate_curve_value(0) == 0.0
        assert scaler.calculate_curve_value(-5) == 0.0
        assert scaler.calculate_curve_value(float("nan")) == 0.0
        assert scaler.calculate_curve_value(float("inf")) == 0.0

    def test_curve_value_formula(self):
        value = 100.0
        expected = 10.0 / (1 + YT_CURVE_DAMPENING_FACTOR * 10.0)
        assert scaler.calculate_curve_value(value) == pytest.approx(expected)

    def test_curve_has_diminishing_returns(self):
        gain_low = scaler.calculate_curve_value(10) - scaler.calculate_curve_value(0)
        gain_high = scaler.calculate_curve_value(110) - scaler.calculate_curve_value(100)
        assert gain_high < gain_low

    def test_curve_difference(self):
        assert scaler.calculate_curve_difference(0, 100) == pytest.approx(scaler.calculate_curve_value(100))
        assert scaler.calculate_curve_difference(100, 100) == 0.0

    def test_adjusted_difference_applies_threshold(self):
        scaling, deduction = 1800.0, 100.0
        threshold = deduction / scaling
        expected = max(scaler.calculate_curve_value(100) - threshold, 0)
        assert scaler.calculate_adjusted_curve_difference(0, 100, scaling, deduction) == pytest.approx(expected)

    def test_adjusted_difference_without_deduction_falls_back(self):
        assert scaler.calculate_adjusted_curve_difference(0, 100, 1800, 0) == pytest.approx(
            scaler.calculate_curve_difference(0, 100)
        )

    def test_adjusted_difference_below_threshold_is_zero(self):
        # Tiny revenue never clears the lifetime deduction threshold.
        assert scaler.calculate_adjusted_curve_difference(0, 0.0001, 1800, 100) == 0.0


class TestPeriodAverages:
    def test_growth_produces_higher_second_period(self):
        daily = [{"day": f"2026-07-{d:02d}", "m": 10} for d in range(1, 11)]
        day1, day2 = scaler.get_period_averages(
            daily, "m", date(2026, 7, 1), date(2026, 7, 5), date(2026, 7, 6), date(2026, 7, 10), 3
        )
        assert day2 > day1 > 0

    def test_missing_days_are_zero_filled(self):
        daily = [{"day": "2026-07-01", "m": 10}]
        day1, day2 = scaler.get_period_averages(
            daily, "m", date(2026, 7, 1), date(2026, 7, 3), date(2026, 7, 4), date(2026, 7, 6), 3
        )
        # cumulative stays flat after the single spike
        assert day1 > 0 and day2 == pytest.approx(10.0)

    def test_bad_input_returns_zeros(self):
        assert scaler.get_period_averages(
            [{"bad": 1}], "m", date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3), date(2026, 7, 4), 3
        ) == (0.0, 0.0)


class TestProportionalScaling:
    def test_scales_down_to_threshold(self):
        period = [{"day": "2026-07-01", "m": 30.0}, {"day": "2026-07-02", "m": 10.0}]
        scaled = scaler.apply_proportional_scaling(period, "m", 10.0)
        average = sum(entry["m"] for entry in scaled) / len(scaled)
        assert average == pytest.approx(10.0)
        # relative shape preserved
        assert scaled[0]["m"] / scaled[1]["m"] == pytest.approx(3.0)

    def test_within_threshold_untouched(self):
        period = [{"day": "2026-07-01", "m": 5.0}]
        assert scaler.apply_proportional_scaling(period, "m", 10.0) == period

    def test_zero_threshold_zeroes_period(self):
        period = [{"day": "2026-07-01", "m": 5.0}]
        assert all(entry["m"] == 0.0 for entry in scaler.apply_proportional_scaling(period, "m", 0.0))

    def test_median_pads_missing_days_with_zeros(self):
        # 1 real value among 3 days -> median 0
        assert scaler.median_from_daily_values({"2026-05-01": 4.0}, date(2026, 4, 30), date(2026, 5, 2)) == 0.0
        full = {f"2026-05-{d:02d}": 4.0 for d in range(1, 4)}
        assert scaler.median_from_daily_values(full, date(2026, 5, 1), date(2026, 5, 3)) == 4.0


class TestEmissionConstraints:
    def test_per_brief_cap_and_global_normalize(self):
        matrix = np.array([[0.5, 0.9], [0.7, 0.3]])
        briefs = [{"id": "a", "cap": 0.6}, {"id": "b"}]
        result = scaler.apply_emission_constraints(matrix, briefs)
        # col a capped 1.2 -> 0.6, col b capped 1.2 -> 1.0, total 1.6 -> 1.0
        assert result[:, 0].sum() == pytest.approx(0.6 / 1.6)
        assert result[:, 1].sum() == pytest.approx(1.0 / 1.6)
        assert result.sum() == pytest.approx(1.0)

    def test_below_budget_left_unscaled(self):
        matrix = np.array([[0.1, 0.2], [0.05, 0.1]])
        briefs = [{"id": "a"}, {"id": "b"}]
        assert np.allclose(scaler.apply_emission_constraints(matrix, briefs), matrix)

    def test_burn_uid_absorbs_remainder(self):
        rewards = scaler.sum_to_final_rewards(np.array([[0.2], [0.3]]), [0, 7])
        assert rewards[0] == pytest.approx(0.7)
        assert rewards.sum() == pytest.approx(1.0)

    def test_burn_never_negative(self):
        rewards = scaler.sum_to_final_rewards(np.array([[0.0], [1.5]]), [0, 7])
        assert rewards[0] == 0.0

    def test_no_burn_uid_leaves_rewards(self):
        rewards = scaler.sum_to_final_rewards(np.array([[0.2], [0.3]]), [5, 7])
        assert rewards.tolist() == [0.2, 0.3]

    def test_treasury_allocation_inert_at_zero_percentage(self):
        rewards = np.array([0.8, 0.1, 0.1])
        assert scaler.allocate_subnet_treasury(rewards, [0, 1, 2]).tolist() == rewards.tolist()
