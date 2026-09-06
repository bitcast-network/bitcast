"""YouTubeEvaluator: evaluates each miner OAuth token's channel against briefs."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import bittensor as bt
import httpx

from bitcast.config import (
    DISCRETE_MODE,
    MAX_ACCOUNTS_PER_SYNAPSE,
    YT_LOOKBACK,
    YT_MAX_CONCURRENT_VIDEOS,
    get_settings,
)
from bitcast.validator.reward.models import AccountResult, EvaluationResult, MinerResponse
from bitcast.validator.reward.orchestrator import PlatformEvaluator
from bitcast.validator.youtube import scoring
from bitcast.validator.youtube.api import YouTubeClient, get_video_transcript
from bitcast.validator.youtube.brief_matcher import LLMMatcher, match_briefs, prescreen_briefs
from bitcast.validator.youtube.cache import CycleState, HistoricalVideoRegistry, SearchCache
from bitcast.validator.youtube.timestamps import parse_timestamp


class YouTubeEvaluator(PlatformEvaluator):
    """Evaluates miner-supplied YouTube accounts and scores their videos in USD."""

    supports_batching = True

    def __init__(
        self,
        llm: LLMMatcher,
        history: HistoricalVideoRegistry | None = None,
        search_cache_path: Path | None = None,
    ) -> None:
        self.llm = llm
        self.history = history
        self.search_cache = SearchCache(cache_path=search_cache_path)
        self.cycle_state = CycleState()

    def platform_name(self) -> str:
        return "youtube"

    def can_evaluate(self, response: MinerResponse) -> bool:
        return response.is_valid and response.has_tokens

    def reset_cycle_state(self) -> None:
        self.cycle_state.reset()

    def compact_search_cache(self) -> int:
        """Dedupe the on-disk JSONL search cache. No-op without a disk cache."""
        return self.search_cache.compact()

    async def evaluate_accounts(
        self, response: MinerResponse, briefs: list[dict], metagraph_info: dict
    ) -> EvaluationResult:
        tokens = response.tokens[:MAX_ACCOUNTS_PER_SYNAPSE]
        return await self.evaluate_token_batch(response.uid, tokens, 0, briefs, metagraph_info)

    async def evaluate_token_batch(
        self, uid: int, tokens: list[str], offset: int, briefs: list[dict], metagraph_info: dict
    ) -> EvaluationResult:
        result = EvaluationResult(
            uid=uid,
            platform="youtube",
            metagraph_info=metagraph_info,
            aggregated_scores={brief["id"]: 0.0 for brief in briefs},
        )
        async with httpx.AsyncClient() as session:
            for index, token in enumerate(tokens):
                account_id = f"account_{offset + index + 1}"
                account = await self._evaluate_account(session, account_id, token, briefs)
                result.add_account_result(account)
                for brief_id, score in account.scores.items():
                    result.aggregated_scores[brief_id] = result.aggregated_scores.get(brief_id, 0.0) + score
        return result

    # --- Per-account flow -----------------------------------------------------

    async def _evaluate_account(
        self,
        session: httpx.AsyncClient,
        account_id: str,
        access_token: str,
        briefs: list[dict],
    ) -> AccountResult:
        started = time.monotonic()
        client = YouTubeClient(access_token, session, self.search_cache)
        today = datetime.now(UTC).date()

        try:
            channel_data = await client.get_channel_data(DISCRETE_MODE)
            channel_analytics = await client.get_channel_analytics(today - timedelta(days=YT_LOOKBACK), today)
        except Exception as err:
            bt.logging.warning(f"Channel data unavailable for {account_id}: {err!r}")
            return AccountResult.error_result(account_id, str(err), briefs)

        vet_passed, channel_checks = scoring.vet_channel(channel_data, channel_analytics, today)
        raw_channel_id = channel_data.pop("_raw_channel_id", "")
        account = AccountResult(
            account_id=account_id,
            platform_data={
                "details": channel_data,
                "analytics": channel_analytics,
                "channel_vet_result": vet_passed,
                "channel_checks": channel_checks,
            },
            scores={brief["id"]: 0.0 for brief in briefs},
        )

        if vet_passed or not get_settings().eco_mode:
            videos, scores = await self._process_videos(client, session, raw_channel_id, channel_analytics, briefs)
            account.videos = videos
            if vet_passed:  # a failed channel keeps its video data but earns nothing
                account.scores = scores

        account.performance_stats = {
            "data_api_calls": client.data_api_calls,
            "analytics_api_calls": client.analytics_api_calls,
            "evaluation_time_s": round(time.monotonic() - started, 2),
        }
        return account

    async def _process_videos(
        self,
        client: YouTubeClient,
        session: httpx.AsyncClient,
        channel_id: str,
        channel_analytics: dict,
        briefs: list[dict],
    ) -> tuple[dict, dict[str, float]]:
        settings = get_settings()
        is_ypp = bool(channel_analytics.get("ypp", False))
        video_ids = await client.get_all_uploads(YT_LOOKBACK)

        if not settings.eco_mode and self.history is not None:
            for historical_id in self.history.videos_for_channel(channel_id):
                if historical_id not in video_ids:
                    video_ids.append(historical_id)

        video_data_map = await client.get_video_data_batch(video_ids, DISCRETE_MODE)
        videos: dict[str, dict] = {}
        scores: dict[str, float] = {brief["id"]: 0.0 for brief in briefs}

        # Videos within one channel are independent, so they run concurrently
        # under a bounded semaphore. Channels themselves stay sequential, which
        # is what keeps the cross-account "already scored" dedup meaningful —
        # within a channel the ids are unique, so there is nothing to race.
        pending = [
            video_id
            for video_id in video_ids
            if video_data_map.get(video_id) is not None and not self.cycle_state.is_video_scored(video_id)
        ]
        semaphore = asyncio.Semaphore(YT_MAX_CONCURRENT_VIDEOS)

        async def process(video_id: str) -> tuple[str, dict]:
            async with semaphore:
                return video_id, await self._process_single_video(
                    client,
                    session,
                    video_id,
                    video_data_map[video_id],
                    channel_id,
                    channel_analytics,
                    briefs,
                    is_ypp,
                    scores,
                )

        for video_id, entry in await asyncio.gather(*(process(vid) for vid in pending)):
            videos[video_id] = entry

        scoring.apply_video_limits(briefs, videos, scores)
        return videos, scores

    async def _process_single_video(
        self,
        client: YouTubeClient,
        session: httpx.AsyncClient,
        video_id: str,
        video_data: dict,
        channel_id: str,
        channel_analytics: dict,
        briefs: list[dict],
        is_ypp: bool,
        scores: dict[str, float],
    ) -> dict:
        entry: dict = {
            "details": video_data,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "matches_brief": False,
            "matching_brief_ids": [],
            # Reporting only — every evaluated video carries engagement figures,
            # matched or not, because the portal shows a creator all their videos.
            "analytics": await client.get_video_analytics(video_id, is_ypp),
        }
        # vet_video returns pure boolean gates; the evaluator then enriches the
        # same dict with per-brief prescreen flags and LLM reasoning strings.
        decision: dict[str, Any] = scoring.vet_video(video_data, briefs)
        decision["evaluated_brief_ids"] = [brief["id"] for brief in briefs]
        entry["decision_details"] = decision
        if not decision["video_vet_result"]:
            return entry

        eligible = prescreen_briefs(briefs, video_data)
        decision["preScreeningCheck"] = eligible
        if not any(eligible):
            decision["brief_reasonings"] = ["Failed prescreening (unique identifier or publish window)"] * len(briefs)
            return entry

        transcript = await get_video_transcript(video_id, session)
        if transcript is None:
            decision["transcript_available"] = False
            decision["video_vet_result"] = False
            return entry

        settings = get_settings()
        if not settings.disable_prompt_injection and await self.llm.check_for_prompt_injection(
            video_data.get("description", ""), transcript
        ):
            decision["prompt_injection_detected"] = True
            decision["video_vet_result"] = False
            return entry

        matches, llm_verdicts, reasonings = await match_briefs(self.llm, briefs, eligible, video_data, transcript)
        decision["brief_reasonings"] = reasonings
        decision["contentAgainstBriefCheck"] = llm_verdicts
        matching_brief_ids = [brief["id"] for brief, matched in zip(briefs, matches, strict=True) if matched]
        entry["matches_brief"] = bool(matching_brief_ids)
        entry["matching_brief_ids"] = matching_brief_ids
        if not matching_brief_ids:
            return entry

        score_info = await scoring.calculate_video_score(
            client, video_id, video_data.get("publishedAt", ""), is_ypp, channel_analytics
        )
        entry["base_score"] = score_info["score"]
        entry["scoring_method"] = score_info["scoring_method"]
        entry["daily_analytics"] = score_info["daily_analytics"]
        # Reporting-only companion series; never merged into daily_analytics,
        # which is the scoring input.
        published = parse_timestamp(video_data.get("publishedAt", ""))
        today = datetime.now(UTC).date()
        entry["daily_reporting"] = await client.get_video_daily_reporting(
            video_id, is_ypp, published.date() if published else today - timedelta(days=YT_LOOKBACK), today
        )

        brief_metrics: dict[str, dict] = {}
        for brief in briefs:
            if brief["id"] not in matching_brief_ids:
                continue
            metrics = scoring.calculate_brief_metrics(
                score_info["curve_input_day1"], score_info["curve_input_day2"], brief
            )
            brief_metrics[brief["id"]] = metrics
            scores[brief["id"]] += metrics["usd_target"]
        entry["brief_metrics"] = brief_metrics

        self.cycle_state.mark_video_scored(video_id)
        if self.history is not None:
            self.history.record_match(video_id, channel_id, matching_brief_ids[0])
        return entry
