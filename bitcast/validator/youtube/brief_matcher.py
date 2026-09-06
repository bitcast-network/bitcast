"""Brief matching: cheap prescreening gates, then LLM evaluation and selection."""

import asyncio
from datetime import date, datetime, time, timedelta
from typing import Protocol

import bittensor as bt

from bitcast.config import YT_VIDEO_RELEASE_BUFFER
from bitcast.validator.youtube.timestamps import parse_timestamp

_MAX_CONCURRENT_LLM_CALLS = 5


class LLMMatcher(Protocol):
    """The slice of the LLM client that brief matching depends on."""

    async def evaluate_content_against_brief(
        self, brief: dict, duration: str, description: str, transcript: list | str
    ) -> tuple[bool, str]: ...

    async def check_for_prompt_injection(self, description: str, transcript: list | str) -> bool: ...


def check_unique_identifier(brief: dict, description: str | None) -> bool:
    """Pass unless the brief requires an identifier the description lacks."""
    unique_identifier = brief.get("unique_identifier")
    if not unique_identifier or not str(unique_identifier).strip():
        return True
    if description is None:
        return False
    return str(unique_identifier).strip().lower() in description.lower()


def check_publish_date_range(brief: dict, published_at: str) -> bool:
    """The video must be published within [brief start - buffer, brief end 23:59:59]."""
    published = parse_timestamp(published_at)
    if published is None:
        return False
    try:
        allowed_start = date.fromisoformat(brief["start_date"]) - timedelta(days=YT_VIDEO_RELEASE_BUFFER)
        allowed_end = datetime.combine(date.fromisoformat(brief["end_date"]), time.max, tzinfo=published.tzinfo)
    except (KeyError, ValueError):
        return False
    return allowed_start <= published.date() and published <= allowed_end


def prescreen_briefs(briefs: list[dict], video_data: dict) -> list[bool]:
    """Per-brief eligibility before any transcript or LLM cost is paid."""
    description = video_data.get("description")
    published_at = video_data.get("publishedAt", "")
    return [
        check_unique_identifier(brief, description) and check_publish_date_range(brief, published_at)
        for brief in briefs
    ]


async def match_briefs(
    llm: LLMMatcher,
    briefs: list[dict],
    eligible: list[bool],
    video_data: dict,
    transcript: list | str,
) -> tuple[list[bool], list[bool], list[str]]:
    """LLM-evaluate the eligible briefs and select the winners.

    A video can win at most one regular brief — the matched brief with the
    highest priority (``weight * boost``) — plus every matched
    productPlacement brief.

    Returns ``(selected, llm_verdicts, reasonings)``. The raw LLM verdicts are
    reported alongside the selection so a brief the video satisfied but lost on
    priority is still visible downstream.
    """
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_LLM_CALLS)

    async def evaluate(brief: dict, is_eligible: bool) -> tuple[bool, str]:
        if not is_eligible:
            return False, "Failed prescreening (unique identifier or publish window)"
        async with semaphore:
            return await llm.evaluate_content_against_brief(
                brief, video_data.get("duration", ""), video_data.get("description", ""), transcript
            )

    results = await asyncio.gather(
        *(evaluate(brief, is_eligible) for brief, is_eligible in zip(briefs, eligible, strict=True))
    )
    raw_matches = [matched for matched, _ in results]
    reasonings = [reasoning for _, reasoning in results]
    return _select_matches(briefs, raw_matches), raw_matches, reasonings


def _select_matches(briefs: list[dict], raw_matches: list[bool]) -> list[bool]:
    selected = [False] * len(briefs)
    best_regular_idx: int | None = None
    best_priority = float("-inf")

    for idx, (brief, matched) in enumerate(zip(briefs, raw_matches, strict=True)):
        if not matched:
            continue
        if brief.get("format") == "productPlacement":
            selected[idx] = True
            continue
        priority = brief.get("weight", 0) * brief.get("boost", 1.0)
        if priority > best_priority:
            best_priority = priority
            best_regular_idx = idx

    if best_regular_idx is not None:
        selected[best_regular_idx] = True
        if sum(raw_matches) > sum(selected):
            bt.logging.info("Multiple regular briefs matched; keeping highest priority only.")
    return selected
