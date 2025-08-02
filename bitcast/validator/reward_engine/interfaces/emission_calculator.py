"""Abstract interface for emission calculation strategies."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any


class EmissionCalculator(ABC):
    """Abstract interface for emission calculation strategies."""
    
    @abstractmethod
    def calculate_targets(
        self, 
        score_matrix: "ScoreMatrix",
        briefs: List[Dict[str, Any]]
    ) -> List["EmissionTarget"]:
        """Calculate emission targets based on score matrix and briefs."""
        pass 