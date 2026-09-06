"""Unified async LLM client over the OpenRouter and Chute providers.

Both providers speak the OpenAI chat-completions dialect; only the endpoint,
model name and headers differ. Brief evaluations run three times concurrently
and pass if ANY run passes — this blunts false negatives from LLM
nondeterminism. Responses are markdown parsed by ``## Verdict`` section.
"""

import asyncio
import re
from pathlib import Path
from typing import Any, Protocol

import bittensor as bt
import httpx

from bitcast.config import LLM_CACHE_TTL, TRANSCRIPT_MAX_LENGTH, get_settings
from bitcast.http import request_with_retry
from bitcast.utils.cache import JsonlCache, TTLCache
from bitcast.validator.llm.prompts import build_injection_prompt, generate_brief_evaluation_prompt

PROVIDERS: dict[str, dict] = {
    "chutes": {
        "url": "https://llm.chutes.ai/v1/chat/completions",
        "model": "Qwen/Qwen3-32B",
        "extra_headers": {},
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "qwen/qwen3-32b:nitro",
        "extra_headers": {"HTTP-Referer": "https://bitcast.ai", "X-Title": "Bitcast Validator"},
    },
}

_EVALUATION_RUNS = 3
_MAX_TOKENS = 4096
_REQUEST_TIMEOUT = 90.0


class _Cache(Protocol):
    """Minimal slice of TTLCache / JsonlCache used by LLMClient."""

    def get(self, key: Any, default: Any = ...) -> Any: ...
    def set(self, key: Any, value: Any) -> None: ...


class LLMError(Exception):
    """An LLM request failed after retries."""


def crop_transcript(transcript: list | str) -> str:
    """Stringify and truncate a transcript to the model input budget."""
    return str(transcript)[:TRANSCRIPT_MAX_LENGTH]


def parse_llm_response(text: str, response_type: str = "brief_evaluation") -> dict:
    """Extract the verdict and reasoning from a markdown LLM response.

    Missing verdicts fail closed: NO for brief evaluations, FALSE (no
    injection) for injection checks.
    """
    if response_type == "prompt_injection":
        verdict = re.search(r"## Verdict\s*\n\s*(TRUE|FALSE)", text, re.IGNORECASE)
        if verdict is None:
            bt.logging.warning("Injection response had no parseable verdict; assuming no injection.")
        analysis = re.search(r"## Analysis\s*\n\s*(.*?)(?:\n##|\n```|$)", text, re.DOTALL | re.IGNORECASE)
        return {
            "injection_detected": verdict.group(1).upper() == "TRUE" if verdict else False,
            "reasoning": analysis.group(1).strip() if analysis else (text.strip() or "No reasoning provided"),
        }

    verdict = re.search(r"## Verdict\s*\n\s*(YES|NO)", text, re.IGNORECASE)
    summary = re.search(r"## Summary\s*\n\s*(.*?)(?:\n##|\n```|$)", text, re.DOTALL | re.IGNORECASE)
    return {
        "meets_brief": verdict.group(1).upper() == "YES" if verdict else False,
        "reasoning": summary.group(1).strip() if summary else "Unable to parse response",
    }


class LLMClient:
    """Async chat-completions client bound to one provider (chutes/openrouter)."""

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        cache_path: Path | None = None,
    ) -> None:
        settings = get_settings()
        self.provider = (provider or settings.llm_provider).lower()
        if self.provider not in PROVIDERS:
            raise ValueError(f"Unknown LLM provider: {self.provider}")
        self._config = PROVIDERS[self.provider]
        self.api_key = api_key or (
            settings.chutes_api_key if self.provider == "chutes" else settings.openrouter_api_key
        )
        self.model = self._config["model"]
        self.request_count = 0
        self._caching_enabled = not settings.disable_llm_caching
        # When cache_path is provided we persist to a JSONL file (validator in
        # prod on EFS); otherwise we keep the cache in-memory only (tests,
        # ephemeral use). JSONL is NFS-safe — no SQLite/WAL coordination.
        cache: _Cache | None = None
        if self._caching_enabled:
            if cache_path is not None:
                cache = JsonlCache(cache_path, ttl=LLM_CACHE_TTL, sliding=True)
            else:
                cache = TTLCache(ttl=LLM_CACHE_TTL, sliding=True)
        self._cache: _Cache | None = cache
        # One pooled session for the client's lifetime. Created lazily on the
        # first request so construction stays sync and loop-independent.
        self._session: httpx.AsyncClient | None = None
        self._session_lock = asyncio.Lock()

    def compact_cache(self) -> int:
        """Dedupe the on-disk JSONL. No-op when caching is disabled or in-memory only."""
        if isinstance(self._cache, JsonlCache):
            return self._cache.compact()
        return 0

    async def _get_session(self) -> httpx.AsyncClient:
        """Return the pooled session, opening one if absent or already closed."""
        if self._session is None or self._session.is_closed:
            async with self._session_lock:
                if self._session is None or self._session.is_closed:
                    self._session = httpx.AsyncClient()
        return self._session

    async def aclose(self) -> None:
        """Close the pooled session. Idempotent; safe before any request."""
        session, self._session = self._session, None
        if session is not None and not session.is_closed:
            await session.aclose()

    async def __aenter__(self) -> "LLMClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def _make_request(self, prompt: str) -> str:
        """One chat completion; returns the message content. Retried via request_with_retry."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self._config["extra_headers"],
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": _MAX_TOKENS,
        }
        self.request_count += 1
        response = await request_with_retry(
            await self._get_session(),
            "POST",
            self._config["url"],
            json=payload,
            headers=headers,
            timeout=_REQUEST_TIMEOUT,
            label=f"{self.provider} chat",
        )
        if response.status_code >= 400:
            raise LLMError(f"{self.provider} returned {response.status_code}: {response.text[:300]}")
        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def evaluate_content_against_brief(
        self, brief: dict, duration: str, description: str, transcript: list | str
    ) -> tuple[bool, str]:
        """Decide whether a video fully satisfies a brief.

        Runs three concurrent evaluations and passes if any run passes.
        Returns ``(meets_brief, reasoning)``; failures return ``(False, error)``.
        """
        prompt = generate_brief_evaluation_prompt(brief, duration, description, crop_transcript(transcript))
        if self._cache is not None:
            cached = self._cache.get(prompt)
            if cached is not None:
                return cached

        try:
            responses = await asyncio.gather(*(self._make_request(prompt) for _ in range(_EVALUATION_RUNS)))
        except (TimeoutError, LLMError, httpx.HTTPError) as err:
            return False, f"Error during evaluation: {err}"

        results = [parse_llm_response(response) for response in responses]
        meets_brief = any(result["meets_brief"] for result in results)
        reasoning = next((r["reasoning"] for r in results if r["meets_brief"]), results[0]["reasoning"])
        bt.logging.info(f"Brief {brief.get('id')}: {'✅ matched' if meets_brief else '❌ not matched'}")

        if self._cache is not None:
            self._cache.set(prompt, (meets_brief, reasoning))
        return meets_brief, reasoning

    async def check_for_prompt_injection(self, description: str, transcript: list | str) -> bool:
        """Audit creator content for evaluation-manipulation attempts.

        Fails open (returns False) on errors, matching v1 behaviour. Cached by
        the tokenless template so the random delimiter doesn't bust the cache.
        """
        prompt, template = build_injection_prompt(description, crop_transcript(transcript))
        if self._cache is not None:
            cached = self._cache.get(template)
            if cached is not None:
                return cached

        try:
            response = await self._make_request(prompt)
        except (TimeoutError, LLMError, httpx.HTTPError) as err:
            bt.logging.warning(f"Prompt-injection check failed ({err}); treating as clean.")
            return False

        detected = parse_llm_response(response, "prompt_injection")["injection_detected"]
        if self._cache is not None:
            self._cache.set(template, detected)
        return detected
