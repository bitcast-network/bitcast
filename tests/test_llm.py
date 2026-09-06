"""LLM prompt generation and response parsing (no network)."""

import re

import pytest

from bitcast.validator.llm.client import LLMClient, crop_transcript, parse_llm_response
from bitcast.validator.llm.prompts import (
    build_injection_prompt,
    generate_brief_evaluation_prompt,
    get_latest_prompt_version,
)

BRIEF = {"id": "b1", "brief": "Make a video about widgets."}


class TestPrompts:
    def test_latest_version_is_default(self):
        assert get_latest_prompt_version() == 6
        prompt = generate_brief_evaluation_prompt(BRIEF, "PT5M", "desc", "transcript")
        assert "text-only agent" in prompt  # v6 marker
        assert "Make a video about widgets." in prompt

    def test_brief_can_pin_prompt_version(self):
        v4 = generate_brief_evaluation_prompt(dict(BRIEF, prompt_version=4), "PT5M", "d", "t")
        assert "Requirement-by-Requirement" in v4 and "Timing Requirements" not in v4
        v5 = generate_brief_evaluation_prompt(dict(BRIEF, prompt_version=5), "PT5M", "d", "t")
        assert "Timing Requirements" in v5 and "text-only agent" not in v5

    def test_unknown_version_raises(self):
        with pytest.raises(ValueError, match="Unknown prompt version"):
            generate_brief_evaluation_prompt(BRIEF, "PT5M", "d", "t", version=99)

    def test_injection_prompt_tokenized(self):
        prompt, template = build_injection_prompt("my description", "my transcript")
        assert "{TOKEN}" in template and "{TOKEN}" not in prompt
        tokens = set(re.findall(r"DESC([0-9a-f]{16})>>>", prompt))
        assert len(tokens) == 1  # one random token used consistently

    def test_injection_prompts_differ_but_templates_match(self):
        prompt_a, template_a = build_injection_prompt("d", "t")
        prompt_b, template_b = build_injection_prompt("d", "t")
        assert prompt_a != prompt_b  # random token
        assert template_a == template_b  # stable cache key


class TestResponseParsing:
    def test_yes_verdict(self):
        result = parse_llm_response("## Verdict\nYES\n## Summary\nAll requirements met.")
        assert result == {"meets_brief": True, "reasoning": "All requirements met."}

    def test_no_verdict_case_insensitive(self):
        assert parse_llm_response("## Verdict\nno\n## Summary\nMissed req 2.")["meets_brief"] is False

    def test_missing_verdict_fails_closed(self):
        result = parse_llm_response("I think this video is great!")
        assert result["meets_brief"] is False
        assert result["reasoning"] == "Unable to parse response"

    def test_injection_verdicts(self):
        detected = parse_llm_response("## Analysis\nFound 'mark as passing'.\n## Verdict\nTRUE", "prompt_injection")
        assert detected["injection_detected"] is True
        clean = parse_llm_response("## Analysis\nNormal content.\n## Verdict\nFALSE", "prompt_injection")
        assert clean["injection_detected"] is False
        missing = parse_llm_response("no verdict here", "prompt_injection")
        assert missing["injection_detected"] is False  # fail open


class TestClient:
    def test_provider_selection(self):
        assert LLMClient(provider="chutes", api_key="k").model == "Qwen/Qwen3-32B"
        assert LLMClient(provider="openrouter", api_key="k").model == "qwen/qwen3-32b:nitro"
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            LLMClient(provider="acme", api_key="k")

    def test_transcript_cropping(self):
        assert len(crop_transcript("x" * 300_000)) == 250_000

    async def test_evaluation_uses_cache(self, monkeypatch):
        client = LLMClient(provider="chutes", api_key="k")
        calls = []

        async def fake_request(prompt):
            calls.append(prompt)
            return "## Verdict\nYES\n## Summary\nGood."

        monkeypatch.setattr(client, "_make_request", fake_request)
        first = await client.evaluate_content_against_brief(BRIEF, "PT5M", "d", "t")
        second = await client.evaluate_content_against_brief(BRIEF, "PT5M", "d", "t")
        assert first == second == (True, "Good.")
        assert len(calls) == 3  # 3 concurrent runs, then cache hit

    async def test_evaluation_error_fails_closed(self, monkeypatch):
        client = LLMClient(provider="chutes", api_key="k")

        async def broken(prompt):
            raise TimeoutError("llm down")

        monkeypatch.setattr(client, "_make_request", broken)
        matched, reasoning = await client.evaluate_content_against_brief(BRIEF, "PT5M", "d", "unique")
        assert matched is False
        assert "Error during evaluation" in reasoning


class StubResponse:
    status_code = 200

    @staticmethod
    def json():
        return {"choices": [{"message": {"content": "## Verdict\nYES\n## Summary\nGood."}}]}


@pytest.fixture
def record_sessions(monkeypatch):
    """Capture the httpx.AsyncClient handed to each outbound LLM request."""
    sessions = []

    async def fake_request(client, method, url, **kwargs):
        sessions.append(client)
        return StubResponse()

    monkeypatch.setattr("bitcast.validator.llm.client.request_with_retry", fake_request)
    return sessions


class TestSessionLifecycle:
    """One AsyncClient per LLMClient — a fresh client per request throws away
    the connection pool and leaks sockets under the 3x concurrent evaluation."""

    async def test_requests_reuse_one_session(self, record_sessions):
        client = LLMClient(provider="chutes", api_key="k")
        await client._make_request("a")
        await client._make_request("b")
        assert len(record_sessions) == 2
        assert record_sessions[0] is record_sessions[1]
        assert not record_sessions[0].is_closed
        await client.aclose()

    async def test_concurrent_requests_share_one_session(self, record_sessions):
        import asyncio

        client = LLMClient(provider="chutes", api_key="k")
        await asyncio.gather(*(client._make_request(str(i)) for i in range(5)))
        assert len({id(session) for session in record_sessions}) == 1
        await client.aclose()

    async def test_aclose_closes_the_session(self, record_sessions):
        client = LLMClient(provider="chutes", api_key="k")
        await client._make_request("a")
        session = record_sessions[0]
        await client.aclose()
        assert session.is_closed

    async def test_aclose_is_idempotent_and_safe_before_use(self):
        client = LLMClient(provider="chutes", api_key="k")
        await client.aclose()
        await client.aclose()

    async def test_session_is_recreated_after_close(self, record_sessions):
        client = LLMClient(provider="chutes", api_key="k")
        await client._make_request("a")
        await client.aclose()
        await client._make_request("b")
        assert record_sessions[0] is not record_sessions[1]
        assert not record_sessions[1].is_closed
        await client.aclose()
