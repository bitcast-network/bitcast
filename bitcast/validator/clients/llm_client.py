"""
LLM Client factory and unified API.

This module provides the factory for selecting the appropriate LLM provider
based on configuration, and exposes the main evaluation functions used by
the rest of the codebase.

Usage:
    from bitcast.validator.clients.llm_client import (
        evaluate_content_against_brief,
        check_for_prompt_injection,
        get_llm_client,
        get_llm_request_count,
        reset_llm_request_count
    )
"""

import bittensor as bt
import requests
from typing import Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor

from bitcast.validator.utils.config import (
    LLM_PROVIDER,
    DISABLE_LLM_CACHING,
    OPENAI_CACHE_EXPIRY
)
from bitcast.validator.clients.base_client import (
    BaseLLMClient,
    crop_transcript,
    get_prompt_version,
    parse_llm_response,
    build_injection_prompt
)
from bitcast.validator.clients.prompts import generate_brief_evaluation_prompt


_PROVIDERS: Dict[str, type] = {}
_cached_client: BaseLLMClient = None


def _load_providers():
    """Lazy load providers to avoid circular imports."""
    if not _PROVIDERS:
        from bitcast.validator.clients.ChuteClient import ChuteClient
        from bitcast.validator.clients.OpenRouterClient import OpenRouterClient
        
        _PROVIDERS["chutes"] = ChuteClient
        _PROVIDERS["openrouter"] = OpenRouterClient


def get_llm_client() -> BaseLLMClient:
    """
    Get the configured LLM client instance.
    
    Returns:
        The LLM client based on LLM_PROVIDER config.
        
    Raises:
        ValueError: If the configured provider is not supported.
    """
    global _cached_client
    
    _load_providers()
    
    if LLM_PROVIDER not in _PROVIDERS:
        available = list(_PROVIDERS.keys())
        raise ValueError(f"Unsupported LLM provider: '{LLM_PROVIDER}'. Available: {available}")
    
    client_class = _PROVIDERS[LLM_PROVIDER]
    
    # Cache the client instance
    if _cached_client is None or not isinstance(_cached_client, client_class):
        _cached_client = client_class()
    
    return _cached_client


def get_llm_request_count() -> int:
    """Get the current LLM request count for the active provider."""
    return get_llm_client().request_count


def reset_llm_request_count() -> None:
    """Reset the LLM request counter for the active provider."""
    get_llm_client().reset_request_count()


def get_llm_cache():
    """Get the LLM cache from the active client."""
    client = get_llm_client()
    return client.get_cache()


def _make_single_brief_evaluation(client: BaseLLMClient, prompt_content: str) -> Dict[str, Any]:
    """Make a single LLM evaluation call for brief matching."""
    response = client._make_request(
        model=client.BRIEF_EVALUATION_MODEL,
        messages=[{"role": "user", "content": prompt_content}],
        temperature=0
    )
    
    content = response["choices"][0]["message"]["content"]
    parsed_result = parse_llm_response(content, "brief_evaluation")
    
    return {
        "meets_brief": parsed_result["meets_brief"],
        "reasoning": parsed_result["reasoning"]
    }


def evaluate_content_against_brief(brief: Dict, duration: str, description: str, transcript: str) -> Tuple[bool, str]:
    """
    Evaluate the transcript against the brief using the configured LLM provider.
    
    Returns a tuple of (bool, str) where bool indicates if content meets brief, str is reasoning.
    
    Runs three concurrent evaluations and applies optimistic logic (pass if any passes)
    to reduce false negatives from LLM non-determinism.
    """
    client = get_llm_client()
    transcript = crop_transcript(transcript)
    prompt_version = get_prompt_version(brief)
    prompt_content = generate_brief_evaluation_prompt(brief, duration, description, transcript, prompt_version)

    try:
        cache = None if DISABLE_LLM_CACHING else client.get_cache()
        if cache is not None and prompt_content in cache:
            cached_result = cache[prompt_content]
            meets_brief = cached_result["meets_brief"]
            reasoning = cached_result["reasoning"]
            
            with client._cache_lock:
                cache.set(prompt_content, cached_result, expire=OPENAI_CACHE_EXPIRY)
            
            emoji = "✅" if meets_brief else "❌"
            bt.logging.info(f"Meets brief '{brief['id']}' (v{prompt_version}): {meets_brief} {emoji} (cache)")
            return meets_brief, reasoning

        # Run three concurrent evaluations
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(_make_single_brief_evaluation, client, prompt_content) for _ in range(3)]
            results = [future.result() for future in futures]
        
        # Optimistic: pass if either passes
        meets_brief = any(r["meets_brief"] for r in results)
        reasoning = next((r["reasoning"] for r in results if r["meets_brief"]), results[0]["reasoning"])
        
        bt.logging.debug(f"Triple validation for '{brief['id']}': {results[0]['meets_brief']}, {results[1]['meets_brief']}, {results[2]['meets_brief']}")

        if cache is not None:
            with client._cache_lock:
                cache.set(prompt_content, {"meets_brief": meets_brief, "reasoning": reasoning}, expire=OPENAI_CACHE_EXPIRY)

        emoji = "✅" if meets_brief else "❌"
        bt.logging.info(f"Brief {brief['id']} (v{prompt_version}): {meets_brief} {emoji}")
        return meets_brief, reasoning

    except requests.exceptions.RequestException as e:
        bt.logging.error(f"{client.get_provider_name()} API error: {e}")
        return False, f"Error during evaluation: {str(e)}"
    except Exception as e:
        bt.logging.error(f"Unexpected error during brief evaluation: {e}")
        return False, f"Unexpected error: {str(e)}"


def check_for_prompt_injection(description: str, transcript: str) -> bool:
    """
    Check for potential prompt injection attempts within the video description and transcript.
    
    Returns True if any prompt injection is detected, otherwise False.
    """
    client = get_llm_client()
    transcript = crop_transcript(transcript)
    injection_prompt, injection_prompt_template = build_injection_prompt(description, transcript)

    try:
        cache = None if DISABLE_LLM_CACHING else client.get_cache()
        if cache is not None and injection_prompt_template in cache:
            injection_detected = cache[injection_prompt_template]
            
            # Implement sliding expiration - reset the 24-hour timer on access
            with client._cache_lock:
                cache.set(injection_prompt_template, injection_detected, expire=OPENAI_CACHE_EXPIRY)
            
            bt.logging.info(f"Prompt Injection: {injection_detected} (cache)")
            return injection_detected

        # Make request to LLM
        response = client._make_request(
            model=client.PROMPT_INJECTION_MODEL,
            messages=[{"role": "user", "content": injection_prompt}],
            temperature=0
        )
        
        # Parse text response
        content = response["choices"][0]["message"]["content"]
        parsed_result = parse_llm_response(content, "prompt_injection")
        injection_detected = parsed_result["injection_detected"]

        if cache is not None:
            with client._cache_lock:
                cache.set(injection_prompt_template, injection_detected, expire=OPENAI_CACHE_EXPIRY)

        bt.logging.info(f"Prompt Injection Check: {'Failed' if injection_detected else 'Passed'}")
        return injection_detected

    except requests.exceptions.RequestException as e:
        bt.logging.error(f"{client.get_provider_name()} API error during prompt injection check: {e}")
        return False
    except Exception as e:
        bt.logging.error(f"Unexpected error during prompt injection check: {e}")
        return False
