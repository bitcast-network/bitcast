"""Brief prescreening, LLM matching and winner selection."""

from datetime import timedelta

from bitcast.validator.youtube import brief_matcher

from ..conftest import FakeLLM


class TestUniqueIdentifier:
    def test_no_identifier_always_passes(self):
        assert brief_matcher.check_unique_identifier({"id": "b"}, "anything")
        assert brief_matcher.check_unique_identifier({"id": "b", "unique_identifier": "  "}, "anything")

    def test_identifier_matched_case_insensitively(self):
        brief = {"id": "b", "unique_identifier": "XYZ123"}
        assert brief_matcher.check_unique_identifier(brief, "get xyz123 today")
        assert not brief_matcher.check_unique_identifier(brief, "no code here")
        assert not brief_matcher.check_unique_identifier(brief, None)


class TestPublishDateRange:
    def test_within_range(self, today):
        brief = {
            "start_date": (today - timedelta(days=5)).isoformat(),
            "end_date": (today + timedelta(days=5)).isoformat(),
        }
        assert brief_matcher.check_publish_date_range(brief, f"{today.isoformat()}T12:00:00Z")

    def test_release_buffer_before_start(self, today):
        brief = {"start_date": today.isoformat(), "end_date": (today + timedelta(days=5)).isoformat()}
        buffered = today - timedelta(days=3)
        assert brief_matcher.check_publish_date_range(brief, f"{buffered.isoformat()}T00:00:00Z")
        too_early = today - timedelta(days=4)
        assert not brief_matcher.check_publish_date_range(brief, f"{too_early.isoformat()}T00:00:00Z")

    def test_end_of_day_inclusive(self, today):
        brief = {"start_date": (today - timedelta(days=5)).isoformat(), "end_date": today.isoformat()}
        assert brief_matcher.check_publish_date_range(brief, f"{today.isoformat()}T23:59:00Z")

    def test_bad_dates_fail(self):
        assert not brief_matcher.check_publish_date_range({"start_date": "nope"}, "2026-07-01T00:00:00Z")
        assert not brief_matcher.check_publish_date_range({}, "not-a-date")


class TestMatching:
    async def test_only_eligible_briefs_hit_the_llm(self, briefs):
        llm = FakeLLM(matching_ids={"brief-1", "brief-2"})
        video = {"duration": "PT5M", "description": "widgets"}
        matches, _, reasonings = await brief_matcher.match_briefs(llm, briefs, [True, False], video, "transcript")
        assert llm.calls == 1
        assert matches[1] is False
        assert "prescreening" in reasonings[1].lower()

    async def test_single_regular_winner_by_priority(self):
        briefs = [
            {"id": "low", "weight": 1},
            {"id": "high", "weight": 9},
            {"id": "pp", "format": "productPlacement", "weight": 1},
        ]
        llm = FakeLLM(matching_ids={"low", "high", "pp"})
        matches, _, _ = await brief_matcher.match_briefs(
            llm, briefs, [True] * 3, {"duration": "", "description": ""}, ""
        )
        assert matches == [False, True, True]

    async def test_boost_affects_priority(self):
        briefs = [{"id": "a", "weight": 3, "boost": 1.0}, {"id": "b", "weight": 2, "boost": 2.0}]
        llm = FakeLLM(matching_ids={"a", "b"})
        matches, _, _ = await brief_matcher.match_briefs(
            llm, briefs, [True, True], {"duration": "", "description": ""}, ""
        )
        assert matches == [False, True]  # 2*2.0 > 3*1.0

    async def test_no_matches(self, briefs):
        llm = FakeLLM(matching_ids=set())
        matches, _, _ = await brief_matcher.match_briefs(
            llm, briefs, [True, True], {"duration": "", "description": ""}, ""
        )
        assert matches == [False, False]
