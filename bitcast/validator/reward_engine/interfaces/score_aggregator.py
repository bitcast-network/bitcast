"""Abstract interface for score aggregation strategies."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any


class ScoreAggregator(ABC):
    """Abstract interface for score aggregation strategies."""
    
    @abstractmethod
    def aggregate_scores(
        self, 
        evaluation_results: "EvaluationResultCollection",
        briefs: List[Dict[str, Any]]
    ) -> "ScoreMatrix":
        """Aggregate evaluation results into a score matrix."""
        pass 