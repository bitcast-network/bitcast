"""Abstract interface for platform-specific content evaluation."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any


class PlatformEvaluator(ABC):
    """Abstract interface for platform-specific content evaluation."""
    
    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform identifier (e.g., 'youtube', 'tiktok')."""
        pass
    
    @abstractmethod
    def can_evaluate(self, miner_response: Any) -> bool:
        """Check if this evaluator can process the given miner response."""
        pass
    
    @abstractmethod
    async def evaluate_accounts(
        self, 
        miner_response: Any, 
        briefs: List[Dict[str, Any]],
        metagraph_info: Dict[str, Any]
    ) -> "EvaluationResult":
        """Evaluate all accounts in the miner response against briefs."""
        pass
    
    @abstractmethod
    def get_supported_token_types(self) -> List[str]:
        """Return list of supported access token types."""
        pass 