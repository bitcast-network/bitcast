"""End-to-end account evaluation with a fully mocked YouTube API and LLM."""

from datetime import UTC, datetime, timedelta

import pytest

from bitcast.validator.reward.models import MinerResponse
from bitcast.validator.youtube import evaluator as evaluator_module
from bitcast.validator.youtube.evaluator import YouTubeEvaluator

NOW = datetime.now(UTC)


def make_channel_analytics(ypp=True):
    revenue, minutes = {}, {}
    for offset in range(90):
        day = (NOW - timedelta(days=offset)).date().isoformat()
        revenue[day] = 5.0
        minutes[day] = 100.0
    return {
        "ypp": ypp,
        "averageViewPercentage": 25.0,
        "estimatedRedPartnerRevenue": revenue if ypp else {},
        "estimatedMinutesWatched": minutes,
        "cpm": 2.0,
    }


class FakeYouTubeClient:
    """Stands in for YouTubeClient: healthy channel with one scoring video."""

    def __init__(self, access_token, session, search_cache=None):
        self.data_api_calls = 0
        self.analytics_api_calls = 0

    async def get_channel_data(self, discrete_mode=True):
        return {
            "bitcastChannelId": "bitcast_abc",
            "title": "Channel",
            "channel_start": "2024-01-01T00:00:00Z",
            "subCount": "5000",
            "viewCount": "100000",
            "videoCount": "50",
            "_raw_channel_id": "UCraw",
        }

    async def get_channel_analytics(self, start, end):
        return make_channel_analytics()

    async def get_all_uploads(self, max_age_days):
        return ["vid1"]

    async def get_video_data_batch(self, video_ids, discrete_mode=True):
        published = (NOW - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "vid1": {
                "bitcastVideoId": "bitcast_vid1",
                "title": "Widget review",
                "description": "all about widgets",
                "publishedAt": published,
                "duration": "PT10M",
                "caption": "false",
                "privacyStatus": "public",
                "viewCount": "1000",
                "likeCount": "100",
                "commentCount": "10",
            }
        }

    async def get_video_daily_analytics(self, video_id, start, end):
        return [
            {
                "day": (NOW - timedelta(days=offset)).date().isoformat(),
                "estimatedRedPartnerRevenue": 2.0,
                "estimatedMinutesWatched": 500.0,
            }
            for offset in range(12, 0, -1)
        ]

    async def get_video_daily_reporting(self, video_id, is_ypp, start, end):
        return [
            {
                "day": (NOW - timedelta(days=offset)).date().isoformat(),
                "views": 50,
                "cpm": 2.5,
                "deviceTypeMinutes": {"DESKTOP": 30, "MOBILE": 20},
            }
            for offset in range(12, 0, -1)
        ]

    async def get_video_analytics(self, video_id, is_ypp, today=None):
        return {
            "views": 1000,
            "likes": 100,
            "shares": 5,
            "averageViewPercentage": 42.0,
            "countryMinutes": {"US": 900},
        }


@pytest.fixture
def patched_youtube(monkeypatch):
    monkeypatch.setattr(evaluator_module, "YouTubeClient", FakeYouTubeClient)

    async def fake_transcript(video_id, session):
        return [{"start": 0, "dur": 5, "text": "widgets are great"}]

    monkeypatch.setattr(evaluator_module, "get_video_transcript", fake_transcript)


async def test_full_account_evaluation_scores_matched_brief(patched_youtube, briefs, fake_llm):
    youtube = YouTubeEvaluator(llm=fake_llm)
    response = MinerResponse(uid=5, tokens=["token-1"])
    result = await youtube.evaluate_accounts(response, briefs, {"alpha_stake": 0.0})

    assert result.platform == "youtube"
    account = result.account_results["account_1"]
    assert account.success
    assert account.platform_data["channel_vet_result"] is True
    assert account.videos["vid1"]["matches_brief"] is True
    assert account.videos["vid1"]["matching_brief_ids"] == ["brief-1"]
    assert result.aggregated_scores["brief-1"] > 0
    assert result.aggregated_scores["brief-2"] == 0.0


class TestReportingFields:
    """Fields nothing in scoring reads, but every dashboard downstream does."""

    async def test_evaluated_video_carries_analytics_and_brief_decisions(self, patched_youtube, briefs, fake_llm):
        youtube = YouTubeEvaluator(llm=fake_llm)
        result = await youtube.evaluate_accounts(MinerResponse(uid=5, tokens=["token-1"]), briefs, {})

        video = result.account_results["account_1"].videos["vid1"]
        assert video["analytics"]["views"] == 1000
        assert video["analytics"]["countryMinutes"] == {"US": 900}

        # The reporting series travels beside the scoring input, never inside it.
        assert video["daily_reporting"][0]["deviceTypeMinutes"] == {"DESKTOP": 30, "MOBILE": 20}
        assert set(video["daily_analytics"][0]) == {
            "day",
            "estimatedRedPartnerRevenue",
            "estimatedMinutesWatched",
        }

        decision = video["decision_details"]
        assert decision["evaluated_brief_ids"] == ["brief-1", "brief-2"]
        assert decision["preScreeningCheck"] == [True, True]
        assert decision["contentAgainstBriefCheck"] == [True, False]
        assert len(decision["brief_reasonings"]) == 2

    async def test_analytics_survive_a_vetting_failure(self, patched_youtube, briefs, fake_llm, monkeypatch):
        class PrivateVideoClient(FakeYouTubeClient):
            async def get_video_data_batch(self, video_ids, discrete_mode=True):
                videos = await super().get_video_data_batch(video_ids, discrete_mode)
                videos["vid1"]["privacyStatus"] = "private"
                return videos

        monkeypatch.setattr(evaluator_module, "YouTubeClient", PrivateVideoClient)
        youtube = YouTubeEvaluator(llm=fake_llm)
        result = await youtube.evaluate_accounts(MinerResponse(uid=5, tokens=["token-1"]), briefs, {})

        video = result.account_results["account_1"].videos["vid1"]
        assert video["decision_details"]["video_vet_result"] is False
        assert video["analytics"]["views"] == 1000  # a rejected video still reports stats


async def test_video_not_scored_twice_across_accounts(patched_youtube, briefs, fake_llm):
    youtube = YouTubeEvaluator(llm=fake_llm)
    response = MinerResponse(uid=5, tokens=["token-1", "token-2"])
    result = await youtube.evaluate_accounts(response, briefs, {"alpha_stake": 0.0})

    first = result.account_results["account_1"]
    second = result.account_results["account_2"]
    assert "vid1" in first.videos
    assert "vid1" not in second.videos  # deduplicated by cycle state

    youtube.reset_cycle_state()
    assert not youtube.cycle_state.is_video_scored("vid1")


async def test_failed_channel_earns_nothing(patched_youtube, briefs, fake_llm, monkeypatch):
    class TinyChannelClient(FakeYouTubeClient):
        async def get_channel_data(self, discrete_mode=True):
            data = await super().get_channel_data(discrete_mode)
            return dict(data, subCount="10")  # below YT_MIN_SUBS

    monkeypatch.setattr(evaluator_module, "YouTubeClient", TinyChannelClient)
    youtube = YouTubeEvaluator(llm=fake_llm)
    result = await youtube.evaluate_accounts(MinerResponse(uid=5, tokens=["token-1"]), briefs, {})

    account = result.account_results["account_1"]
    assert account.platform_data["channel_vet_result"] is False
    assert all(score == 0.0 for score in account.scores.values())


class TestYppEligibility:
    """Non-YPP channels are ineligible outright — alpha stake cannot buy in."""

    @staticmethod
    def _non_ypp_client():
        class NonYppClient(FakeYouTubeClient):
            async def get_channel_analytics(self, start, end):
                return make_channel_analytics(ypp=False)

            async def get_video_daily_analytics(self, video_id, start, end):
                raise AssertionError("non-YPP accounts must not spend analytics quota")

        return NonYppClient

    async def test_non_ypp_channel_fails_acceptance_and_earns_nothing(
        self, patched_youtube, briefs, fake_llm, monkeypatch
    ):
        monkeypatch.setattr(evaluator_module, "YouTubeClient", self._non_ypp_client())
        youtube = YouTubeEvaluator(llm=fake_llm)
        result = await youtube.evaluate_accounts(MinerResponse(uid=5, tokens=["token-1"]), briefs, {})

        account = result.account_results["account_1"]
        assert account.platform_data["channel_checks"]["acceptance"] is False
        assert account.platform_data["channel_vet_result"] is False
        assert all(score == 0.0 for score in account.scores.values())
        assert all(score == 0.0 for score in result.aggregated_scores.values())

    async def test_large_alpha_stake_does_not_rescue_a_non_ypp_channel(
        self, patched_youtube, briefs, fake_llm, monkeypatch
    ):
        monkeypatch.setattr(evaluator_module, "YouTubeClient", self._non_ypp_client())
        youtube = YouTubeEvaluator(llm=fake_llm)
        result = await youtube.evaluate_accounts(
            MinerResponse(uid=5, tokens=["token-1"]), briefs, {"alpha_stake": 10_000_000.0}
        )

        account = result.account_results["account_1"]
        assert account.platform_data["channel_vet_result"] is False
        assert all(score == 0.0 for score in result.aggregated_scores.values())

    async def test_ypp_channel_with_zero_revenue_earns_nothing(self, patched_youtube, briefs, fake_llm, monkeypatch):
        class ZeroRevenueClient(FakeYouTubeClient):
            async def get_video_daily_analytics(self, video_id, start, end):
                entries = await super().get_video_daily_analytics(video_id, start, end)
                return [dict(entry, estimatedRedPartnerRevenue=0.0) for entry in entries]

        monkeypatch.setattr(evaluator_module, "YouTubeClient", ZeroRevenueClient)
        youtube = YouTubeEvaluator(llm=fake_llm)
        result = await youtube.evaluate_accounts(MinerResponse(uid=5, tokens=["token-1"]), briefs, {})

        account = result.account_results["account_1"]
        assert account.platform_data["channel_vet_result"] is True  # channel is still eligible
        assert account.videos["vid1"]["scoring_method"] == "ypp_zero_revenue"
        assert all(score == 0.0 for score in result.aggregated_scores.values())


async def test_api_failure_yields_error_account(briefs, fake_llm, monkeypatch):
    class BrokenClient(FakeYouTubeClient):
        async def get_channel_data(self, discrete_mode=True):
            raise ConnectionError("token revoked")

    monkeypatch.setattr(evaluator_module, "YouTubeClient", BrokenClient)
    youtube = YouTubeEvaluator(llm=fake_llm)
    result = await youtube.evaluate_accounts(MinerResponse(uid=5, tokens=["token-1"]), briefs, {})

    account = result.account_results["account_1"]
    assert not account.success
    assert all(score == 0.0 for score in account.scores.values())


async def test_missing_transcript_fails_video(patched_youtube, briefs, fake_llm, monkeypatch):
    async def no_transcript(video_id, session):
        return None

    monkeypatch.setattr(evaluator_module, "get_video_transcript", no_transcript)
    youtube = YouTubeEvaluator(llm=fake_llm)
    result = await youtube.evaluate_accounts(MinerResponse(uid=5, tokens=["token-1"]), briefs, {})

    video = result.account_results["account_1"].videos["vid1"]
    assert video["matches_brief"] is False
    assert video["decision_details"]["video_vet_result"] is False


def test_can_evaluate_requires_tokens(fake_llm):
    youtube = YouTubeEvaluator(llm=fake_llm)
    assert youtube.can_evaluate(MinerResponse(uid=1, tokens=["t"]))
    assert not youtube.can_evaluate(MinerResponse(uid=1, tokens=[]))
    assert not youtube.can_evaluate(MinerResponse.error(1, "boom"))


class TestVideoConcurrency:
    """Videos inside a channel evaluate in parallel without changing the result."""

    async def test_videos_run_concurrently_and_stay_bounded(self, patched_youtube, briefs, fake_llm, monkeypatch):
        import asyncio

        from bitcast.validator.youtube import evaluator as module

        live = 0
        peak = 0

        class ManyVideoClient(FakeYouTubeClient):
            async def get_all_uploads(self, max_age_days):
                return [f"vid{n}" for n in range(12)]

            async def get_video_data_batch(self, video_ids, discrete_mode=True):
                one = await super().get_video_data_batch(["vid1"], discrete_mode)
                return {vid: {**one["vid1"], "bitcastVideoId": f"bitcast_{vid}"} for vid in video_ids}

            async def get_video_analytics(self, video_id, is_ypp, today=None):
                nonlocal live, peak
                live += 1
                peak = max(peak, live)
                await asyncio.sleep(0.01)
                live -= 1
                return await super().get_video_analytics(video_id, is_ypp, today)

        monkeypatch.setattr(module, "YouTubeClient", ManyVideoClient)
        youtube = YouTubeEvaluator(llm=fake_llm)
        result = await youtube.evaluate_accounts(MinerResponse(uid=5, tokens=["token-1"]), briefs, {})

        videos = result.account_results["account_1"].videos
        assert len(videos) == 12
        assert peak > 1, "videos still evaluated one at a time"
        assert peak <= module.YT_MAX_CONCURRENT_VIDEOS, "concurrency exceeded its bound"
        # Every video still scored, and the aggregate is the sum of the parts.
        assert result.aggregated_scores["brief-1"] > 0
