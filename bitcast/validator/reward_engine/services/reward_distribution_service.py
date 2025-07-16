"""Handles final reward distribution - extracted from reward.py normalization and allocation logic."""

from typing import List, Dict, Any, Tuple
import numpy as np
import bittensor as bt
from ..models.emission_target import EmissionTarget
from ..models.evaluation_result import EvaluationResultCollection
from ...utils.config import YT_MIN_EMISSIONS
from ...rewards_scaling import allocate_community_reserve


class RewardDistributionService:
    """Handles final reward calculation and distribution."""
    
    def calculate_distribution(
        self,
        emission_targets: List[EmissionTarget],
        evaluation_results: EvaluationResultCollection,
        briefs: List[Dict[str, Any]],
        uids: List[int]
    ) -> Tuple[np.ndarray, List[dict]]:
        """Calculate final reward distribution from emission targets."""
        try:
            # Convert emission targets to raw weights matrix
            raw_weights_matrix = self._extract_raw_weights_matrix(emission_targets, len(uids))
            
            # Normalize weights into final rewards
            rewards, rewards_matrix = self._normalize_weights(raw_weights_matrix, briefs, uids)
            
            # Create stats from evaluation results
            stats_list = self._create_stats_list(evaluation_results, uids)
            
            # Apply community reserve allocation
            final_rewards = allocate_community_reserve(rewards, uids)
            
            return final_rewards, stats_list
            
        except Exception as e:
            bt.logging.error(f"Error in reward distribution: {e}")
            return self._error_fallback(uids)
    
    def _extract_raw_weights_matrix(
        self, 
        emission_targets: List[EmissionTarget], 
        num_miners: int
    ) -> np.ndarray:
        """Extract raw weights matrix from emission targets."""
        if not emission_targets:
            return np.zeros((num_miners, 0))
        
        num_briefs = len(emission_targets)
        matrix = np.zeros((num_miners, num_briefs), dtype=np.float64)
        
        for brief_idx, target in enumerate(emission_targets):
            weights = target.allocation_details.get("per_miner_weights", [])
            for miner_idx, weight in enumerate(weights):
                if miner_idx < num_miners:
                    matrix[miner_idx, brief_idx] = weight
        
        return matrix
    
    def _normalize_weights(
        self, 
        weights_matrix: np.ndarray, 
        briefs: List[Dict[str, Any]], 
        uids: List[int]
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Normalize weights into final reward distribution."""
        if weights_matrix.size == 0:
            return np.zeros(len(uids)), np.zeros((len(uids), 0))
        
        # Step 1: Clip scores per brief
        clipped = self._clip_brief_scores(weights_matrix)
        
        # Step 2: Normalize across briefs
        normalized = self._normalize_across_briefs(clipped, briefs)
        
        # Step 3: Sum to get final rewards
        rewards = self._sum_to_final_rewards(normalized, uids)
        
        return rewards, normalized
    
    def _clip_brief_scores(self, scores_matrix: np.ndarray) -> np.ndarray:
        """Clip each brief's scores to valid range."""
        result = scores_matrix.astype(np.float64, copy=True)
        
        for col_idx in range(result.shape[1]):
            col_sum = result[:, col_idx].sum()
            
            if col_sum == 0:
                continue
            elif col_sum > 1:
                result[:, col_idx] /= col_sum  # Scale down
            elif col_sum < YT_MIN_EMISSIONS:
                result[:, col_idx] *= (YT_MIN_EMISSIONS / col_sum)  # Scale up
        
        return result
    
    def _normalize_across_briefs(
        self, 
        scores_matrix: np.ndarray, 
        briefs: List[Dict[str, Any]]
    ) -> np.ndarray:
        """Normalize scores across briefs using brief weights."""
        if scores_matrix.size == 0:
            return scores_matrix
        
        # Get brief weights (default to 100 if not specified)
        brief_weights = np.array([brief.get("weight", 100) for brief in briefs])
        
        # Simple case: all weights equal -> just divide by number of briefs
        if np.all(brief_weights == brief_weights[0]):
            return scores_matrix / len(briefs)
        
        # Complex case: apply weighted normalization
        total_weight = np.sum(brief_weights)
        weight_factors = brief_weights / total_weight
        return scores_matrix * weight_factors[np.newaxis, :]
    
    def _sum_to_final_rewards(self, scores_matrix: np.ndarray, uids: List[int]) -> np.ndarray:
        """Sum normalized scores to final rewards, ensuring total = 1."""
        if scores_matrix.size == 0:
            return np.zeros(len(uids))
        
        # Sum each miner's scores across briefs
        rewards = scores_matrix.sum(axis=1)
        
        # Ensure total rewards sum to 1 by adjusting UID 0
        uid_0_idx = next((i for i, uid in enumerate(uids) if uid == 0), None)
        if uid_0_idx is not None:
            other_sum = sum(rewards[i] for i in range(len(rewards)) if i != uid_0_idx)
            rewards[uid_0_idx] = 1.0 - other_sum
        
        return rewards
    
    def _create_stats_list(
        self,
        evaluation_results: EvaluationResultCollection,
        uids: List[int]
    ) -> List[dict]:
        """Create simplified stats list from evaluation results."""
        stats_list = []
        
        for uid in uids:
            eval_result = evaluation_results.get_result(uid)
            
            if eval_result:
                # Convert evaluation result to stats format
                stats = {
                    "scores": eval_result.aggregated_scores,
                    "uid": uid
                }
                
                # Add account details
                for account_id, account_result in eval_result.account_results.items():
                    stats[account_id] = {
                        "yt_account": account_result.platform_data,
                        "videos": account_result.videos,
                        "scores": account_result.scores,
                        "performance_stats": account_result.performance_stats
                    }
                
                # Add metagraph info if available
                if eval_result.metagraph_info:
                    stats["metagraph"] = eval_result.metagraph_info
            else:
                # Minimal stats for missing results
                stats = {"scores": {}, "uid": uid}
            
            stats_list.append(stats)
        
        return stats_list
    
    def _error_fallback(self, uids: List[int]) -> Tuple[np.ndarray, List[dict]]:
        """Simple error fallback that gives all rewards to UID 0."""
        rewards = np.array([1.0 if uid == 0 else 0.0 for uid in uids])
        stats_list = [{"scores": {}, "uid": uid} for uid in uids]
        return rewards, stats_list 