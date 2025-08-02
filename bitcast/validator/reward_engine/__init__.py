"""
Reward calculation system for Bitcast validator.

This module provides a platform-agnostic reward calculation engine
with pluggable platform evaluators.
"""

from .orchestrator import RewardOrchestrator

__all__ = [
    "RewardOrchestrator",
]

__version__ = "1.0.0" 