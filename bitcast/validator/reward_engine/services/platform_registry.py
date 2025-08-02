"""Registry for managing platform evaluators."""

from typing import Dict, List, Optional
import bittensor as bt
from ..interfaces.platform_evaluator import PlatformEvaluator
from ..models.miner_response import MinerResponse


class PlatformRegistry:
    """Registry for managing and selecting platform evaluators."""
    
    def __init__(self):
        self._evaluators: Dict[str, PlatformEvaluator] = {}
    
    def register_evaluator(self, evaluator: PlatformEvaluator):
        """Register a platform evaluator."""
        platform_name = evaluator.platform_name()
        self._evaluators[platform_name] = evaluator
        bt.logging.info(f"Registered evaluator for platform: {platform_name}")
    
    def get_evaluator(self, platform_name: str) -> Optional[PlatformEvaluator]:
        """Get an evaluator for a specific platform."""
        return self._evaluators.get(platform_name)
    
    def get_evaluator_for_response(self, miner_response: MinerResponse) -> Optional[PlatformEvaluator]:
        """Find the appropriate evaluator for a miner response."""
        if not miner_response.is_valid:
            bt.logging.debug(f"Invalid miner response from UID {miner_response.uid}")
            return None
        
        # Optimized: Try evaluators in priority order (YouTube first)
        priority_platforms = ["youtube"]  # Add more as needed
        
        # Check priority platforms first
        for platform_name in priority_platforms:
            evaluator = self._evaluators.get(platform_name)
            if evaluator and evaluator.can_evaluate(miner_response):
                bt.logging.debug(f"Found priority evaluator {platform_name} for UID {miner_response.uid}")
                return evaluator
        
        # Check remaining evaluators
        for evaluator in self._evaluators.values():
            if evaluator.platform_name() not in priority_platforms:
                if evaluator.can_evaluate(miner_response):
                    bt.logging.debug(f"Found evaluator {evaluator.platform_name()} for UID {miner_response.uid}")
                    return evaluator
        
        bt.logging.warning(f"No evaluator found for miner response from UID {miner_response.uid}")
        return None
    
    def get_available_platforms(self) -> List[str]:
        """Get list of available platform names."""
        return list(self._evaluators.keys())
    
    def __len__(self) -> int:
        """Number of registered evaluators."""
        return len(self._evaluators)
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        platforms = ", ".join(self._evaluators.keys())
        return f"PlatformRegistry({platforms})" 