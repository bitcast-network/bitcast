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
    ) -> Tuple[np.ndarray, List[dict], np.ndarray, np.ndarray]:
        """Calculate final reward distribution from emission targets."""
        try:
            # Convert emission targets to raw weights matrix
            raw_weights_matrix = self._extract_raw_weights_matrix(emission_targets, len(uids))
            
            # Store pre-constraint weights for corrections calculation
            pre_constraint_weights = raw_weights_matrix.copy()
            
            # Normalize weights into final rewards
            rewards, rewards_matrix, brief_emission_percentages = self._normalize_weights(raw_weights_matrix, briefs, uids)
            
            # Create stats from evaluation results
            stats_list = self._create_stats_list(evaluation_results, uids, brief_emission_percentages)
            
            # Apply community reserve allocation
            final_rewards = allocate_community_reserve(rewards, uids)
            
            return final_rewards, stats_list, pre_constraint_weights, rewards_matrix
            
        except Exception as e:
            bt.logging.error(f"Error in reward distribution: {e}")
            return self._error_fallback(uids)
    
    def _extract_raw_weights_matrix(
        self, 
        emission_targets: List[EmissionTarget], 
        num_miners: int
    ) -> np.ndarray:
        """Extract raw weights matrix from emission targets."""
        bt.logging.info("--- Extracting Raw Weights Matrix ---")
        
        if not emission_targets:
            bt.logging.warning("No emission targets - returning empty matrix")
            return np.zeros((num_miners, 0))
        
        num_briefs = len(emission_targets)
        matrix = np.zeros((num_miners, num_briefs), dtype=np.float64)
        
        for brief_idx, target in enumerate(emission_targets):
            weights = target.allocation_details.get("per_miner_weights", [])
            brief_id = target.brief_id
            brief_total = 0.0
            non_zero_count = 0
            
            for miner_idx, weight in enumerate(weights):
                if miner_idx < num_miners and weight != 0:
                    matrix[miner_idx, brief_idx] = weight
                    brief_total += weight
                    non_zero_count += 1
            
            # Only log briefs with significant activity
            if brief_total > 0.001 or non_zero_count > 0:
                bt.logging.info(f"Brief {brief_id}: {non_zero_count} miners, ${target.usd_target:.2f}")
        
        return matrix
    
    def _normalize_weights(
        self, 
        weights_matrix: np.ndarray, 
        briefs: List[Dict[str, Any]], 
        uids: List[int]
    ) -> Tuple[np.ndarray, np.ndarray, Dict[str, float]]:
        """Normalize weights into final reward distribution."""
        if weights_matrix.size == 0:
            bt.logging.warning("Empty weights matrix - returning zero rewards")
            return np.zeros(len(uids)), np.zeros((len(uids), 0)), {}
        
        # Apply caps and global constraints
        normalized = self._apply_emission_constraints(weights_matrix, briefs)
        
        # Sum to get final rewards
        rewards = self._sum_to_final_rewards(normalized, uids)
        
        final_total = float(np.sum(rewards))
        final_non_zero = np.count_nonzero(rewards)
        max_reward = float(np.max(rewards)) if len(rewards) > 0 else 0.0
        
        bt.logging.info(f"Final rewards: {final_non_zero}/{len(uids)} miners, total={final_total:.4f}, max={max_reward:.6f}")
        
        # Calculate brief emission percentages for stats
        brief_emission_percentages = {}
        for brief_idx, brief in enumerate(briefs):
            brief_percentage = normalized[:, brief_idx].sum()
            brief_id = brief.get('id', f'brief_{brief_idx}')
            brief_emission_percentages[brief_id] = brief_percentage
            bt.logging.info(f"Brief {brief_id}: {brief_percentage:.6f} total emission percentage")
        
        return rewards, normalized, brief_emission_percentages
    
    def _apply_emission_constraints(
        self, 
        scores_matrix: np.ndarray, 
        briefs: List[Dict[str, Any]]
    ) -> np.ndarray:
        """Apply brief caps and global constraints to ensure proper emission allocation."""
        if scores_matrix.size == 0:
            return scores_matrix
        
        result = scores_matrix.copy()
        
        # Apply individual brief caps
        for brief_idx, brief in enumerate(briefs):
            brief_cap = brief.get("cap", 1.0)  # Default from BA response
            brief_sum = result[:, brief_idx].sum()
            
            if brief_sum > brief_cap:
                scale_factor = brief_cap / brief_sum
                result[:, brief_idx] *= scale_factor
                # Log when brief exceeds cap (BA requirement)
                bt.logging.info(f"Brief '{brief.get('id', 'unknown')}' exceeded cap {brief_cap:.4f}, "
                               f"scaled down by factor {scale_factor:.4f}")
        
        # Apply global minimum scaling if total < YT_MIN_EMISSIONS
        total_sum = result.sum()
        if total_sum > 0 and total_sum < YT_MIN_EMISSIONS:
            global_min_scale_factor = YT_MIN_EMISSIONS / total_sum
            result = result * global_min_scale_factor
            bt.logging.info(f"Applied global minimum scaling factor {global_min_scale_factor:.4f} "
                           f"(total was {total_sum:.4f}, minimum is {YT_MIN_EMISSIONS})")
            total_sum = result.sum()  # Update total_sum after minimum scaling
        
        # Apply global maximum scaling if total > 1.0
        if total_sum > 1.0:
            global_scale_factor = 1.0 / total_sum
            result = result / total_sum
            bt.logging.info(f"Applied global scaling factor {global_scale_factor:.4f} (total was {total_sum:.4f})")
        
        # Log emission percentages per brief (BA requirement)
        for brief_idx, brief in enumerate(briefs):
            brief_percentage = result[:, brief_idx].sum()
            bt.logging.info(f"Brief '{brief.get('id', 'unknown')}' claiming {brief_percentage:.4f} "
                           f"({brief_percentage * 100:.2f}%) of total emissions")
        
        return result
    
    def _sum_to_final_rewards(self, scores_matrix: np.ndarray, uids: List[int]) -> np.ndarray:
        """Sum normalized scores to final rewards, ensuring total = 1 and UID 0 is not negative."""
        if scores_matrix.size == 0:
            return np.zeros(len(uids))
        
        # Sum each miner's scores across briefs
        rewards = scores_matrix.sum(axis=1)
        
        # Ensure total rewards sum to 1 by adjusting UID 0, but never negative
        uid_0_idx = next((i for i, uid in enumerate(uids) if uid == 0), None)
        if uid_0_idx is not None:
            other_sum = sum(rewards[i] for i in range(len(rewards)) if i != uid_0_idx)
            rewards[uid_0_idx] = max(1.0 - other_sum, 0.0)
        
        return rewards
    
    def _create_stats_list(
        self,
        evaluation_results: EvaluationResultCollection,
        uids: List[int],
        brief_emission_percentages: Dict[str, float] = None
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
        
        # Add brief emission percentages to the first stats entry (BA requirement)
        if stats_list and brief_emission_percentages:
            stats_list[0]["brief_emission_percentages"] = brief_emission_percentages
        
        return stats_list
    
    def _error_fallback(self, uids: List[int]) -> Tuple[np.ndarray, List[dict], np.ndarray, np.ndarray]:
        """Simple error fallback that gives all rewards to UID 0."""
        rewards = np.array([1.0 if uid == 0 else 0.0 for uid in uids])
        stats_list = [{"scores": {}, "uid": uid} for uid in uids]
        # Return empty pre-constraint weights matrix for error case
        pre_constraint_weights = np.zeros((len(uids), 0))
        post_constraint_weights = np.zeros((len(uids), 0))
        return rewards, stats_list, pre_constraint_weights, post_constraint_weights 