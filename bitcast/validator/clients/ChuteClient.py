"""
Chutes API client implementation.

This module provides the Chutes-specific LLM client implementation
using the MiniMax model through the Chutes API.
"""

import bittensor as bt
import requests
from typing import Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential

from bitcast.validator.utils.config import CHUTES_API_KEY
from bitcast.validator.clients.base_client import BaseLLMClient


class ChuteClient(BaseLLMClient):
    """Chutes API client with integrated caching."""

    BRIEF_EVALUATION_MODEL = "Qwen/Qwen3-32B"
    PROMPT_INJECTION_MODEL = "Qwen/Qwen3-32B"
    API_URL = "https://llm.chutes.ai/v1/chat/completions"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
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
            
            response = requests.post(
                self.API_URL,
                headers=headers,
                json=payload,
                timeout=90
            )
            response.raise_for_status()
            
            return response.json()
            
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
