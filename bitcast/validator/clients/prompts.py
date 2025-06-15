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
    Generate a prompt that forces the LLM to prove each brief item
    with an exact quote + timestamp or mark it Not Met.

    Improvements over the old version:
    • Instructs the model to auto-number the brief items.
    • Requires a 5-15-word quote for every Met claim.
    • Demands the raw `start` time (seconds) from the transcript as evidence.
    • States that uncertain or fabricated timestamps → Not Met.
    • Re-emphasises “description-only” items.
    """
    return (
        "///// SPONSOR BRIEF /////\n"
        f"{brief['brief']}\n\n"
        "///// VIDEO DETAILS /////\n"
        f"VIDEO DURATION: {duration}\n"
        f"VIDEO DESCRIPTION: {description}\n"
        "VIDEO TRANSCRIPT (list of dicts with 'start' (s), 'dur' (s), 'text'):\n"
        f"{transcript}\n\n"
        "///// YOUR TASK /////\n"
        "You are the sponsor's review agent. Decide—objectively—whether this video **fully** satisfies the brief.\n"
        "Information that appears **only in the written description does NOT count** toward meeting a video-content "
        "requirement **unless the requirement is specific to the description** (e.g., \"include link in "
        "description\").\n\n"
        "**Important Context**\n"
        "• The brief requirements are **minimum requirements** - creators are may choose to go deeper into the topic area - although this is not mandatory\n"
        "**Step-by-step instructions**\n\n"
        "1. **Auto-number** each requirement line in the brief (1, 2, 3 …) in the order it appears.\n"
        "2. For every numbered requirement:\n"
        "   • Search the `transcript` field.\n"
        "   • **For description-specific requirements** (e.g., \"include link in description\"): Search the video description.\n"
        "   • If you find evidence, mark **Met** and provide:\n"
        "       – a 5-15-word quote extracted verbatim from that line, and\n"
        "       – the corresponding `start` time (in seconds) or `start-to-start+dur` range.\n"
        "   • If no clear evidence or you are **uncertain**, mark **Not Met**.\n"
        "3. After the checklist, apply extra gates:\n"
        "   • **Video-type check** – Dedicated / Pre-roll / Other (must match brief):\n"
        "       - Dedicated: Calculate the total duration of segments directly about the sponsor's topic. If this is less than 80% of total video duration, mark as Not Met.\n"
        "       - Pre-roll: Short ad segment at the start of a video\n"
        "       - Other: Any other format\n"
        "   • **Silent content check** – Is over 50% of the video silent or music-only?\n"
        "4. **If any item or gate fails → Verdiction = NO.**\n\n"
        "**Important accuracy rules**\n"
        "• Do **not** invent timestamps. If a timestamp is uncertain, mark the item Not Met.\n"
        "• Fabricated quotes or timestamps automatically fail that item.\n"
        "• When in doubt, choose **NO**.\n"
        "• For video-type check, you MUST calculate the rough percentage of content about the sponsor's topic.\n\n"
        "**Response format (exactly):**\n"
        "```\n"
        "## Requirement-by-Requirement\n"
        "- Req 1: [requirement text] — Met / Not Met — \"quoted evidence\" (start-sec or range)\n"
        "- Req 2: ...\n"
        "...\n"
        "## Additional Gates\n"
        "- Video type: Dedicated / Pre-roll / Other — short note with rough percentage calculation\n"
        "- Silent/music-only issue? YES/NO — short note\n"
        "## Verdict\n"
        "YES or NO\n"
        "## Summary\n"
        "Brief 1 sentence explanation of why the video did or did not meet the brief requirements.\n"
        "```\n"
        "Be concise and remember: fabricated evidence = Not Met."
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