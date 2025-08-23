"""Handles score aggregation across platforms and accounts."""

from typing import List, Dict, Any
import numpy as np
from ..interfaces.score_aggregator import ScoreAggregator
from ..models.score_matrix import ScoreMatrix
from ..models.evaluation_result import EvaluationResultCollection


class ScoreAggregationService(ScoreAggregator):
    """Default implementation of score aggregation."""
    
    def aggregate_scores(
        self, 
        evaluation_results: EvaluationResultCollection,
        briefs: List[Dict[str, Any]]
    ) -> ScoreMatrix:
        """
        Aggregate scores from all platforms and accounts.
        
        This replaces the complex logic in the current reward() function.
        """
        # Create mapping from UID to matrix index
        uid_to_index = {uid: idx for idx, uid in enumerate(evaluation_results.results.keys())}
        
        score_matrix = ScoreMatrix.create_empty(
            num_miners=len(evaluation_results.results),
            num_briefs=len(briefs)
        )
        
        for uid, result in evaluation_results.results.items():
            miner_idx = uid_to_index[uid]
            
            for brief_idx, brief in enumerate(briefs):
                brief_id = brief["id"]
                
                # Aggregate scores across all accounts for this brief
                total_score = self._aggregate_brief_scores(result, brief_id)
                score_matrix.set_score(miner_idx, brief_idx, total_score)
        
        return score_matrix
    
    def _aggregate_brief_scores(self, evaluation_result, brief_id: str) -> float:
        """
        Aggregate scores for a specific brief across all accounts.
        
        Note: This is platform-agnostic summation. Platform-specific transformations
        (scaling factors, boost multipliers) are applied at the platform level
        before aggregation, making this service work for any future platform.
        """
        total_score = 0.0
        
        # Sum pre-scaled scores from all account evaluations
        for account_data in evaluation_result.account_results.values():
            brief_score = account_data.scores.get(brief_id, 0.0)
            total_score += brief_score
        
        return total_score 