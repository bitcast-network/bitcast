"""
LLM Router - Routes inference requests to appropriate LLM client based on version.

This module acts as a router between OpenAI and Chutes clients, directing
requests based on prompt version:
- Versions 1-3: OpenAI (GPT-4o with structured outputs)
- Versions 4+: Chutes (DeepSeek-V3)
"""

import bittensor as bt
from bitcast.validator.clients import OpenaiClient, ChuteClient


def evaluate_content_against_brief(brief, duration, description, transcript):
    """
    Route brief evaluation to the appropriate LLM client based on prompt version.
    
    Args:
        brief (dict): Brief dictionary containing prompt_version field
        duration: Video duration
        description: Video description
        transcript: Video transcript
        
    Returns:
        tuple: (meets_brief: bool, reasoning: str)
    """
    prompt_version = brief.get('prompt_version', 1)
    
    if prompt_version >= 4:
        bt.logging.debug(f"Routing brief evaluation (v{prompt_version}) to Chutes/DeepSeek")
        return ChuteClient.evaluate_content_against_brief(brief, duration, description, transcript)
    else:
        bt.logging.debug(f"Routing brief evaluation (v{prompt_version}) to OpenAI")
        return OpenaiClient.evaluate_content_against_brief(brief, duration, description, transcript)


def check_for_prompt_injection(description, transcript):
    """
    Check for prompt injection attempts using Chutes/DeepSeek.
    
    Always uses Chutes for cost-effectiveness and consistency.
    
    Args:
        description: Video description
        transcript: Video transcript
        
    Returns:
        bool: True if injection detected, False otherwise
    """
    return ChuteClient.check_for_prompt_injection(description, transcript)
