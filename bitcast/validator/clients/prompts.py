"""
Prompt templates for brief evaluation.

This module contains all prompt templates used for evaluating video content against briefs.
Each version represents a different evaluation approach with backwards compatibility maintained.

How to add a new prompt version:
1. Create a new function generate_brief_evaluation_prompt_vX (where X is the version number)
2. Add the function to the PROMPT_GENERATORS registry
3. Update tests to validate the new version
4. Briefs can then specify "prompt_version": X to use the new format

The system defaults to version 1 for backwards compatibility with existing briefs.
"""

def generate_brief_evaluation_prompt_v1(brief, duration, description, transcript):
    """
    Generate the original (v1) prompt format for backwards compatibility.
    
    This is the legacy prompt format that focuses on basic brief evaluation
    without structured response requirements.
    """
    return (
        "///// BRIEF /////\n"
        f"{brief['brief']}\n"
        "///// VIDEO DETAILS /////\n"
        f"VIDEO DURATION: {duration}\n"
        f"VIDEO DESCRIPTION: {description}\n"
        f"VIDEO TRANSCRIPT: {transcript}\n\n"
        "///// YOUR TASK /////\n"
        "You are evaluating a video and its content (description + transcript) on behalf of its marketing sponsor. Your job is to decide whether the content meets the sponsor's brief. "
        "The video duration, description and transcript were taken directly from the video. "
        "This is a high-stakes decision — if the content does not meet the brief, the creator will not be paid. "
        "Carefully review the content against each requirement in the brief, step by step. At the end, provide a binary decision: "
        "YES if the content fully meets the brief. NO if any part of the brief is not adequately fulfilled. "
        "Be thorough and objective."
    )


def generate_brief_evaluation_prompt_v2(brief, duration, description, transcript):
    """
    Generate the enhanced (v2) prompt format with detailed evaluation criteria.
    
    This version includes:
    - Structured response format
    - Clear definitions for video types
    - Timestamp citation requirements
    - Additional validation gates
    - Stricter evaluation criteria
    """
    return (
        "///// SPONSOR BRIEF /////\n"
        f"{brief['brief']}\n\n"
        "///// VIDEO DETAILS /////\n"
        f"VIDEO DURATION: {duration}\n"
        f"VIDEO DESCRIPTION: {description}\n"
        f"VIDEO TRANSCRIPT (timestamps included):\n"
        f"{transcript}\n\n"
        "///// YOUR TASK /////\n"
        "You are the sponsor's review agent. Decide—objectively—whether this video **fully** satisfies the brief.\n"
        "Information that appears **only in the written description does NOT count** toward meeting a video‑content requirement **unless the brief explicitly states the item is description‑only** (e.g., \"include link in description\").\n\n"
        "**Key definitions**\n\n"
        "* **Dedicated video** ➜ The bulk of the runtime is clearly focused on the sponsor/topic.\n"
        "* **Pre‑roll ad** ➜ A brief shout‑out or segment that is not the main focus of the video.\n"
        "* **Silent / music‑only** ➜ If roughly half or more of the runtime has no spoken or on‑screen text relevant to the brief ➜ automatic **NO**.\n\n"
        "**Evaluation checklist**\n\n"
        "1. Go line‑by‑line through every requirement in the brief.\n"
        "2. For each item, mark **Met** or **Not Met** and cite key timestamp ranges (e.g. \"02:30‑03:45 explains feature X\").\n"
        "3. After the checklist, run these extra gates:\n"
        "   • **Video‑type check** – Dedicated, Pre‑roll, or Other? (Must match what is specified in brief).\n"
        "   • **Silent content check** – Too much silence/music?\n"
        "4. If **any** requirement or gate fails, final verdict = **NO**.\n\n"
        "**Response format (exactly):**\n\n"
        "```\n"
        "## Requirement‑by‑Requirement\n"
        "- Req 1: Met / Not Met – short note (timestamp)\n"
        "- Req 2: …\n"
        "...\n"
        "## Additional Gates\n"
        "- Video type: Dedicated / Pre‑roll / Other – explain briefly\n"
        "- Silent/music‑only issue? YES/NO – explain briefly\n"
        "## Verdict\n"
        "YES or NO\n"
        "```\n\n"
        "Be concise, cite timestamps, and remember: when in doubt, choose **NO** (creator gets paid only for full compliance)."
    )


# Registry of available prompt generators
PROMPT_GENERATORS = {
    1: generate_brief_evaluation_prompt_v1,
    2: generate_brief_evaluation_prompt_v2,
}


def get_prompt_generator(version):
    """
    Get the appropriate prompt generator for the specified version.
    
    Args:
        version (int): The prompt version to use
        
    Returns:
        callable: The prompt generator function
        
    Raises:
        ValueError: If the version is not supported
    """
    if version not in PROMPT_GENERATORS:
        raise ValueError(f"Unsupported prompt version: {version}. Available versions: {list(PROMPT_GENERATORS.keys())}")
    
    return PROMPT_GENERATORS[version]


def generate_brief_evaluation_prompt(brief, duration, description, transcript, version=1):
    """
    Generate a brief evaluation prompt using the specified version.
    
    Args:
        brief (dict): The brief dictionary containing evaluation criteria
        duration (str): Video duration
        description (str): Video description
        transcript (str): Video transcript
        version (int): Prompt version to use (defaults to 1 for backwards compatibility)
        
    Returns:
        str: The generated prompt
        
    Raises:
        ValueError: If the version is not supported
    """
    prompt_generator = get_prompt_generator(version)
    return prompt_generator(brief, duration, description, transcript) 