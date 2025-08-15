"""Weight corrections calculation service for post-constraint scaling factors."""

from typing import Dict, Any, List
import numpy as np
import bittensor as bt
from ..models.evaluation_result import EvaluationResultCollection


class WeightCorrectionsService:
    """Calculates scaling factors applied during reward distribution constraints."""
    
    def calculate_corrections(
        self, 
        evaluation_results: EvaluationResultCollection,
        pre_constraint_weights: np.ndarray,  # From emission calculation
        post_constraint_weights: np.ndarray, # From reward distribution
        briefs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Calculate scaling factors for each content/brief combination.
        
        Args:
            evaluation_results: Collection of all miner evaluation results
            pre_constraint_weights: Raw weights before caps/scaling (miners x briefs)
            post_constraint_weights: Final weights after all constraints (miners x briefs)
            briefs: List of brief configurations
            
        Returns:
            List of corrections: [{"content_id": str, "brief_id": str, "scaling_factor": float}]
        """
        corrections = []
        
        # Build brief_id to index mapping
        brief_id_to_idx = {brief["id"]: idx for idx, brief in enumerate(briefs)}
        
        # Process each miner's results
        for uid_idx, (uid, evaluation_result) in enumerate(evaluation_results.results.items()):
            if not evaluation_result or not evaluation_result.account_results:
                continue
                
            # Process each account for this miner
            for account_result in evaluation_result.account_results.values():
                self._process_account_corrections(
                    account_result, 
                    uid_idx,
                    brief_id_to_idx,
                    pre_constraint_weights,
                    post_constraint_weights,
                    corrections
                )
        
        bt.logging.info(f"Generated {len(corrections)} weight corrections")
        return corrections
    
    def _process_account_corrections(
        self,
        account_result,
        uid_idx: int,
        brief_id_to_idx: Dict[str, int],
        pre_constraint_weights: np.ndarray,
        post_constraint_weights: np.ndarray,
        corrections: List[Dict[str, Any]]
    ) -> None:
        """Process corrections for a single account."""
        
        for video_id, video_data in account_result.videos.items():
            if not isinstance(video_data, dict):
                continue
                
            # Extract content_id (platform-agnostic identifier)
            content_id = self._extract_content_id(video_data, video_id)
            
            # Process each brief this video matched
            brief_metrics = video_data.get("brief_metrics", {})
            
            for brief_id, metrics in brief_metrics.items():
                if brief_id not in brief_id_to_idx:
                    continue
                    
                brief_idx = brief_id_to_idx[brief_id]
                
                # Calculate scaling factor from weight matrices
                scaling_factor = self._calculate_scaling_factor(
                    uid_idx, brief_idx, pre_constraint_weights, post_constraint_weights
                )
                
                # Add correction entry
                corrections.append({
                    "content_id": content_id,
                    "brief_id": brief_id,
                    "scaling_factor": scaling_factor
                })
    
    def _extract_content_id(self, video_data: Dict[str, Any], fallback_video_id: str) -> str:
        """Extract platform-agnostic content_id from video data."""
        if isinstance(video_data, dict) and "details" in video_data:
            details = video_data["details"]
            if isinstance(details, dict):
                return details.get("bitcastVideoId", fallback_video_id)
        
        return fallback_video_id
    
    def _calculate_scaling_factor(
        self,
        uid_idx: int,
        brief_idx: int,
        pre_constraint_weights: np.ndarray,
        post_constraint_weights: np.ndarray
    ) -> float:
        """
        Calculate scaling factor by comparing pre and post constraint weights.
        
        Returns:
            float: Scaling factor (0.0-2.0+)
                - 1.0 = No scaling applied
                - 0.0-0.99 = Weight reduced by constraints
                - 0.0 = Content was limited/blacklisted
                - 1.01+ = Weight increased (rare, minimum scaling)
        """
        # Handle matrix bounds checking
        if (uid_idx >= pre_constraint_weights.shape[0] or 
            brief_idx >= pre_constraint_weights.shape[1] or
            uid_idx >= post_constraint_weights.shape[0] or 
            brief_idx >= post_constraint_weights.shape[1]):
            return 0.0
            
        pre_weight = float(pre_constraint_weights[uid_idx, brief_idx])
        post_weight = float(post_constraint_weights[uid_idx, brief_idx])
        
        # Handle edge cases
        if pre_weight == 0.0:
            return 0.0  # No original weight
            
        scaling_factor = post_weight / pre_weight
        
        # Ensure reasonable bounds (protect against numerical issues)
        return max(0.0, min(scaling_factor, 10.0))