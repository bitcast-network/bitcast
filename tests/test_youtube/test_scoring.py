"""YouTube channel/video vetting and curve-based scoring."""

from datetime import date, timedelta

import pytest

from bitcast.validator.youtube import scoring

TODAY = date(2026, 7, 13)


def make_channel_analytics(ypp=True, revenue_median=1.0, minutes_per_day=100.0):
    """90 days of channel history ending today."""
    revenue, minutes = {}, {}
    for offset in range(90):
        day = (TODAY - timedelta(days=offset)).isoformat()
        revenue[day] = revenue_median
        minutes[day] = minutes_per_day
    return {
        "ypp": ypp,
        "averageViewPercentage": 25.0,
        "estimatedRedPartnerRevenue": revenue if ypp else {},
        "estimatedMinutesWatched": minutes,
        "cpm": 2.0 if ypp else 0,
    }


class TestChannelVetting:
    """Only affirmative YPP membership makes a channel eligible."""

    def test_healthy_ypp_channel_passes(self):
        ok, checks = scoring.vet_channel(
            {"channel_start": "2024-01-01T00:00:00Z", "subCount": "500"},
            make_channel_analytics(),
            today=TODAY,
        )
        assert ok, checks

    def test_non_ypp_channel_fails_acceptance(self):
        ok, checks = scoring.vet_channel(
            {"channel_start": "2024-01-01T00:00:00Z", "subCount": "500"},
            make_channel_analytics(ypp=False),
            today=TODAY,
        )
        assert not ok and not checks["acceptance"]

    def test_missing_ypp_flag_fails_acceptance(self):
        analytics = make_channel_analytics()
        del analytics["ypp"]
        ok, checks = scoring.vet_channel(
            {"channel_start": "2024-01-01T00:00:00Z", "subCount": "500"}, analytics, today=TODAY
        )
        assert not ok and not checks["acceptance"]

    @pytest.mark.parametrize(
        ("field", "value", "failed_check"),
        [
            ("subCount", "50", "min_subs"),
            ("subCount", "600000", "max_subs"),
        ],
    )
    def test_subscriber_gates(self, field, value, failed_check):
        ok, checks = scoring.vet_channel(
            {"channel_start": "2024-01-01T00:00:00Z", field: value},
            make_channel_analytics(),
            today=TODAY,
        )
        assert not ok and not checks[failed_check]

    def test_young_channel_fails(self):
        from datetime import UTC, datetime

        recent = (datetime.now(UTC) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        ok, checks = scoring.vet_channel(
            {"channel_start": recent, "subCount": "500"}, make_channel_analytics(), today=TODAY
        )
        assert not ok and not checks["channel_age"]

    def test_low_retention_fails(self):
        analytics = make_channel_analytics()
        analytics["averageViewPercentage"] = 5.0
        ok, checks = scoring.vet_channel(
            {"channel_start": "2024-01-01T00:00:00Z", "subCount": "500"}, analytics, today=TODAY
        )
        assert not ok and not checks["retention"]


class TestVideoVetting:
    def base_video(self):
        return {
            "privacyStatus": "public",
            "publishedAt": f"{(TODAY - timedelta(days=5)).isoformat()}T10:00:00Z",
            "caption": "false",
        }

    def briefs(self):
        return [{"id": "b1", "start_date": (TODAY - timedelta(days=7)).isoformat()}]

    def test_valid_video_passes(self):
        checks = scoring.vet_video(self.base_video(), self.briefs(), today=TODAY)
        assert checks["video_vet_result"], checks

    def test_private_video_fails(self):
        video = dict(self.base_video(), privacyStatus="private")
        assert not scoring.vet_video(video, self.briefs(), today=TODAY)["public_video"]

    def test_old_video_fails_age_limit(self):
        video = dict(self.base_video(), publishedAt=f"{(TODAY - timedelta(days=30)).isoformat()}T00:00:00Z")
        assert not scoring.vet_video(video, self.briefs(), today=TODAY)["age_limit"]

    def test_video_published_at_age_boundary_passes(self):
        boundary = TODAY - timedelta(days=17)  # scoring window + reward delay
        video = dict(self.base_video(), publishedAt=f"{boundary.isoformat()}T00:00:00Z")
        old_brief = [{"id": "b1", "start_date": (TODAY - timedelta(days=30)).isoformat()}]
        assert scoring.vet_video(video, old_brief, today=TODAY)["age_limit"]

    def test_manual_captions_fail(self):
        video = dict(self.base_video(), caption="true")
        assert not scoring.vet_video(video, self.briefs(), today=TODAY)["auto_captions_only"]

    def test_video_before_all_briefs_fails(self):
        video = dict(self.base_video(), publishedAt=f"{(TODAY - timedelta(days=16)).isoformat()}T00:00:00Z")
        late_brief = [{"id": "b1", "start_date": (TODAY - timedelta(days=2)).isoformat()}]
        assert not scoring.vet_video(video, late_brief, today=TODAY)["publish_date"]


class FakeAnalyticsClient:
    """Serves canned per-day video analytics."""

    def __init__(self, daily):
        self.daily = daily

    async def get_video_daily_analytics(self, video_id, start, end):
        return self.daily


def growing_revenue_daily(days=12, revenue_per_day=1.0):
    """Revenue every day up to T-1 so period 2's cumulative outpaces period 1."""
    return [
        {
            "day": (TODAY - timedelta(days=offset)).isoformat(),
            "estimatedRedPartnerRevenue": revenue_per_day,
            "estimatedMinutesWatched": revenue_per_day * 1000,
        }
        for offset in range(days, 0, -1)
    ]


class TestVideoScoring:
    """Only positive Red-partner revenue is scoreable; there is no minutes proxy."""

    async def test_ypp_video_with_growing_revenue_scores_positive(self):
        client = FakeAnalyticsClient(growing_revenue_daily())
        result = await scoring.calculate_video_score(
            client,
            "vid1",
            f"{(TODAY - timedelta(days=12)).isoformat()}T00:00:00Z",
            is_ypp_account=True,
            channel_analytics=make_channel_analytics(revenue_median=10.0),
            today=TODAY,
        )
        assert result["scoring_method"] == "ypp"
        assert result["score"] > 0
        assert result["curve_input_day2"] > result["curve_input_day1"]

    async def test_ypp_zero_revenue_scores_zero(self):
        daily = [dict(entry, estimatedRedPartnerRevenue=0.0) for entry in growing_revenue_daily()]
        result = await scoring.calculate_video_score(
            client=FakeAnalyticsClient(daily),
            video_id="vid1",
            published_at=f"{(TODAY - timedelta(days=12)).isoformat()}T00:00:00Z",
            is_ypp_account=True,
            channel_analytics=make_channel_analytics(minutes_per_day=100000.0),
            today=TODAY,
        )
        assert result["scoring_method"] == "ypp_zero_revenue"
        assert result["score"] == 0.0
        assert result["curve_input_day1"] == 0.0
        assert result["curve_input_day2"] == 0.0

    async def test_net_negative_revenue_scores_zero(self):
        """Chargebacks/adjustments can make reported revenue net negative.

        Only *positive* affirmative YPP revenue is scoreable, so a negative
        total must take the same zero path as no revenue at all — it must never
        reach the reward curve.
        """
        daily = [dict(entry, estimatedRedPartnerRevenue=-1.0) for entry in growing_revenue_daily()]
        result = await scoring.calculate_video_score(
            client=FakeAnalyticsClient(daily),
            video_id="vid1",
            published_at=f"{(TODAY - timedelta(days=12)).isoformat()}T00:00:00Z",
            is_ypp_account=True,
            channel_analytics=make_channel_analytics(revenue_median=10.0),
            today=TODAY,
        )
        assert result["scoring_method"] == "ypp_zero_revenue"
        assert result["score"] == 0.0
        assert result["curve_input_day1"] == 0.0
        assert result["curve_input_day2"] == 0.0

    async def test_positive_days_cancelled_by_a_larger_refund_score_zero(self):
        """A late refund that outweighs the earnings nets negative overall."""
        daily = growing_revenue_daily()
        daily[-1] = dict(daily[-1], estimatedRedPartnerRevenue=-100.0)
        result = await scoring.calculate_video_score(
            client=FakeAnalyticsClient(daily),
            video_id="vid1",
            published_at=f"{(TODAY - timedelta(days=12)).isoformat()}T00:00:00Z",
            is_ypp_account=True,
            channel_analytics=make_channel_analytics(revenue_median=10.0),
            today=TODAY,
        )
        assert result["scoring_method"] == "ypp_zero_revenue"
        assert result["score"] == 0.0

    async def test_a_refund_that_leaves_net_positive_revenue_still_scores(self):
        """Guard the boundary: net > 0 keeps the normal revenue curve."""
        daily = growing_revenue_daily()
        daily[-1] = dict(daily[-1], estimatedRedPartnerRevenue=-0.5)
        result = await scoring.calculate_video_score(
            client=FakeAnalyticsClient(daily),
            video_id="vid1",
            published_at=f"{(TODAY - timedelta(days=12)).isoformat()}T00:00:00Z",
            is_ypp_account=True,
            channel_analytics=make_channel_analytics(revenue_median=10.0),
            today=TODAY,
        )
        assert result["scoring_method"] == "ypp"

    async def test_non_ypp_account_scores_zero_without_calling_the_api(self):
        class ExplodingClient:
            async def get_video_daily_analytics(self, *args):
                raise AssertionError("non-YPP accounts must not spend analytics quota")

        result = await scoring.calculate_video_score(
            client=ExplodingClient(),
            video_id="vid1",
            published_at=f"{(TODAY - timedelta(days=12)).isoformat()}T00:00:00Z",
            is_ypp_account=False,
            channel_analytics=make_channel_analytics(ypp=False, minutes_per_day=100000.0),
            today=TODAY,
        )
        assert result["scoring_method"] == "non_ypp_ineligible"
        assert result["score"] == 0.0
        assert result["daily_analytics"] == []

    async def test_high_minutes_never_substitute_for_revenue(self):
        """The removed proxy: huge watch time with zero revenue must score zero."""
        daily = [
            dict(entry, estimatedRedPartnerRevenue=0.0, estimatedMinutesWatched=10_000_000.0)
            for entry in growing_revenue_daily()
        ]
        result = await scoring.calculate_video_score(
            client=FakeAnalyticsClient(daily),
            video_id="vid1",
            published_at=f"{(TODAY - timedelta(days=12)).isoformat()}T00:00:00Z",
            is_ypp_account=True,
            channel_analytics=make_channel_analytics(minutes_per_day=10_000_000.0),
            today=TODAY,
        )
        assert result["score"] == 0.0

    async def test_api_failure_falls_back_to_zero(self):
        class BrokenClient:
            async def get_video_daily_analytics(self, *args):
                raise ConnectionError("api down")

        result = await scoring.calculate_video_score(
            BrokenClient(), "vid1", "", True, make_channel_analytics(), today=TODAY
        )
        assert result["scoring_method"] == "curve_error_fallback"
        assert result["score"] == 0.0

    async def test_median_scaling_caps_period_two(self):
        """A revenue spike above the historical median is scaled down."""
        spike = [dict(entry, estimatedRedPartnerRevenue=1000.0) for entry in growing_revenue_daily()]
        modest_median = make_channel_analytics(revenue_median=1.0)
        spiked = await scoring.calculate_video_score(
            FakeAnalyticsClient(spike),
            "vid1",
            f"{(TODAY - timedelta(days=12)).isoformat()}T00:00:00Z",
            True,
            modest_median,
            today=TODAY,
        )
        rich_median = make_channel_analytics(revenue_median=1000.0)
        unscaled = await scoring.calculate_video_score(
            FakeAnalyticsClient(spike),
            "vid1",
            f"{(TODAY - timedelta(days=12)).isoformat()}T00:00:00Z",
            True,
            rich_median,
            today=TODAY,
        )
        assert spiked["curve_input_day2"] < unscaled["curve_input_day2"]


class TestBriefMetrics:
    def test_formats_have_distinct_scaling(self):
        dedicated = scoring.calculate_brief_metrics(0.0, 5.0, {"id": "b", "format": "dedicated"})
        ad_read = scoring.calculate_brief_metrics(0.0, 5.0, {"id": "b", "format": "ad-read"})
        assert dedicated["scaling_factor"] == 1800
        assert ad_read["scaling_factor"] == 400

    def test_product_placement_pays_half_an_integration(self):
        """The rate the portal calculator quotes creators. Drifted to 1/4 once."""
        integration = scoring.calculate_brief_metrics(0.0, 5.0, {"id": "b", "format": "integration"})
        placement = scoring.calculate_brief_metrics(0.0, 5.0, {"id": "b", "format": "productPlacement"})
        assert placement["scaling_factor"] == integration["scaling_factor"] / 2
        assert placement["usd_target"] == pytest.approx(integration["usd_target"] / 2, rel=0.02)

    def test_metrics_carry_the_published_reporting_fields(self):
        """Four columns in video_matched_to_brief that v2 left empty."""
        metrics = scoring.calculate_brief_metrics(0.0, 5.0, {"id": "b", "format": "integration", "boost": 2.0})
        assert metrics["base_score"] > 0  # raw curve difference, pre-deduction
        assert metrics["brief_boost"] == 2.0
        assert metrics["limitation_status"] == "active"

    def test_boost_multiplies_target(self):
        base = scoring.calculate_brief_metrics(0.0, 5.0, {"id": "b"})
        boosted = scoring.calculate_brief_metrics(0.0, 5.0, {"id": "b", "boost": 2.0})
        assert boosted["usd_target"] == pytest.approx(2 * base["usd_target"])

    def test_unknown_format_scores_as_dedicated(self):
        unknown = scoring.calculate_brief_metrics(0.0, 5.0, {"id": "b", "format": "mystery"})
        dedicated = scoring.calculate_brief_metrics(0.0, 5.0, {"id": "b", "format": "dedicated"})
        assert unknown["usd_target"] == dedicated["usd_target"]


class TestVideoLimits:
    def make_video(self, published, usd):
        return {
            "matching_brief_ids": ["b1"],
            "details": {"publishedAt": published},
            "brief_metrics": {"b1": {"usd_target": usd}},
        }

    def test_fifo_keeps_oldest(self):
        videos = {
            "new": self.make_video("2026-07-05T00:00:00Z", 5.0),
            "old": self.make_video("2026-07-01T00:00:00Z", 10.0),
        }
        scores = {"b1": 15.0}
        scoring.apply_video_limits([{"id": "b1", "max_count": 1}], videos, scores)
        assert videos["old"]["brief_metrics"]["b1"]["usd_target"] == 10.0
        assert videos["new"]["brief_metrics"]["b1"]["usd_target"] == 0.0
        assert videos["new"]["brief_metrics"]["b1"]["limitation_status"] == "limited_fifo"
        assert videos["new"]["brief_metrics"]["b1"]["weight"] == 0.0
        assert scores["b1"] == 10.0

    def test_no_limit_leaves_everything(self):
        videos = {"v": self.make_video("2026-07-01T00:00:00Z", 5.0)}
        scores = {"b1": 5.0}
        scoring.apply_video_limits([{"id": "b1"}], videos, scores)
        assert scores["b1"] == 5.0
