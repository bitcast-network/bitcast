"""
Chutes API client implementation.

This module provides the Chutes-specific LLM client implementation
using the MiniMax model through the Chutes API.
"""

import time
import bittensor as bt
import requests
from typing import Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log
import logging

from bitcast.validator.utils.config import CHUTES_API_KEY
from bitcast.validator.clients.base_client import BaseLLMClient


class ChuteClient(BaseLLMClient):
    """Chutes API client with integrated caching."""

    BRIEF_EVALUATION_MODEL = "Qwen/Qwen3-32B"
    PROMPT_INJECTION_MODEL = "Qwen/Qwen3-32B"
    API_URL = "https://llm.chutes.ai/v1/chat/completions"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10), before_sleep=before_sleep_log(logging.getLogger("bittensor"), logging.WARNING))
    def _make_request(self, model: str, **kwargs) -> Dict[str, Any]:
        """Make Chutes API request with retry logic."""
        self.request_count += 1
        
        try:
            headers = {
                "Authorization": f"Bearer {CHUTES_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": model,
                "messages": kwargs.get("messages", []),
                "temperature": kwargs.get("temperature", 0),
                "max_tokens": kwargs.get("max_tokens", 4096)
            }
            
            start_time = time.time()
            response = requests.post(
                self.API_URL,
                headers=headers,
                json=payload,
                timeout=90
            )
            elapsed = time.time() - start_time
            response.raise_for_status()
            
            result = response.json()
            usage = result.get("usage", {})
            bt.logging.info(
                f"Chutes request completed in {elapsed:.1f}s "
                f"(model={model}, "
                f"prompt_tokens={usage.get('prompt_tokens', '?')}, "
                f"completion_tokens={usage.get('completion_tokens', '?')})"
            )
            return result
            
        except requests.exceptions.RequestException as e:
            bt.logging.warning(f"Chutes API error (attempting retry): {e}")
            raise
        except Exception as e:
            bt.logging.error(f"Unexpected error during Chutes request: {e}")
            raise

    def get_provider_name(self) -> str:
        return "chutes"


# Initialize cache
ChuteClient.initialize_cache()
