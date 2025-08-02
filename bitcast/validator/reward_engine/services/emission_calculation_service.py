"""Handles emission calculation - extracted from reward.py calculate_emission_targets and calculate_raw_weights."""

from typing import List, Dict, Any
import numpy as np
import bittensor as bt
from ..interfaces.emission_calculator import EmissionCalculator
from ..models.score_matrix import ScoreMatrix
from ..models.emission_target import EmissionTarget
from ...utils.config import (
    YT_SCALING_FACTOR_DEDICATED, 
    YT_SCALING_FACTOR_AD_READ
)
from ...utils.token_pricing import get_bitcast_alpha_price, get_total_miner_emissions


class EmissionCalculationService(EmissionCalculator):
    """Optimized emission calculation with reduced memory overhead."""
    
    def calculate_targets(
        self, 
        score_matrix: ScoreMatrix,
        briefs: List[Dict[str, Any]]
    ) -> List[EmissionTarget]:
        """
        Calculate emission targets from score matrix.
        """
        bt.logging.info(f"=== EMISSION CALCULATION START: {score_matrix.matrix.shape[0]} miners, {len(briefs)} briefs ===")
        
        # Convert scores to USD emission targets with scaling factors
        emission_targets_matrix = self._calculate_emission_targets_matrix(
            score_matrix.matrix, briefs
        )
        
        # Convert USD targets to raw weights using alpha price and total emissions
        raw_weights_matrix = self._calculate_raw_weights(emission_targets_matrix)
        
        # Create EmissionTarget objects for each brief
        targets = []
        total_usd_targets = 0.0
        total_weights = 0.0
        
        for brief_idx, brief in enumerate(briefs):
            # Extract weights for this brief
            per_miner_weights = raw_weights_matrix[:, brief_idx] if brief_idx < raw_weights_matrix.shape[1] else []
            
            # Calculate USD target for this brief
            usd_target = float(np.sum(emission_targets_matrix[:, brief_idx])) if brief_idx < emission_targets_matrix.shape[1] else 0.0
            
            brief_weight_sum = float(np.sum(per_miner_weights)) if len(per_miner_weights) > 0 else 0.0
            scaling_factor = self._get_scaling_factor(brief)
            boost_factor = brief.get("boost", 1.0)
            
            # Only log if there are significant targets or boosts
            if usd_target > 0.01 or boost_factor != 1.0:
                bt.logging.info(f"Brief {brief.get('id', f'brief_{brief_idx}')}: ${usd_target:.2f}, weight={brief_weight_sum:.4f}")
            
            target = EmissionTarget(
                brief_id=brief["id"],
                usd_target=usd_target,
                allocation_details={
                    "per_miner_weights": per_miner_weights.tolist(),
                    "brief_format": brief.get("format", "dedicated")
                },
                scaling_factors={
                    "scaling_factor": scaling_factor,
                    "boost_factor": boost_factor
                }
            )
            targets.append(target)
            total_usd_targets += usd_target
            total_weights += brief_weight_sum
        
        bt.logging.info(f"=== EMISSION CALCULATION COMPLETE: Total USD targets=${total_usd_targets:.2f}, Total weights={total_weights:.6f} ===")
        return targets
    
    def _calculate_emission_targets_matrix(
        self, 
        scores_matrix: np.ndarray, 
        briefs: List[Dict[str, Any]]
    ) -> np.ndarray:
        """
        Transform raw scores into USD daily emission targets.
        Optimized to reduce memory allocations.
        """
        if scores_matrix.size == 0:
            bt.logging.warning("Empty score matrix - returning empty array")
            return np.array([])
        
        # Work with a copy to avoid modifying the original
        emission_targets = scores_matrix.astype(np.float64, copy=True)
        
        for brief_idx, brief in enumerate(briefs):
            if brief_idx >= emission_targets.shape[1]:
                bt.logging.warning(f"Brief {brief_idx} exceeds matrix columns ({emission_targets.shape[1]}) - skipping")
                continue
            
            # Apply scaling factor in-place
            scaling_factor = self._get_scaling_factor(brief)
            emission_targets[:, brief_idx] *= scaling_factor
            
            # Apply boost multiplier
            boost_factor = brief.get("boost", 1.0)
            emission_targets[:, brief_idx] *= boost_factor
                    
        return emission_targets
    
    def _calculate_raw_weights(self, emission_targets_matrix: np.ndarray) -> np.ndarray:
        """
        Convert USD emission targets to raw weights.
        Optimized for memory efficiency.
        """
        if emission_targets_matrix.size == 0:
            bt.logging.warning("Empty emission targets matrix - returning empty array")
            return np.array([])
        
        try:
            alpha_price_usd = get_bitcast_alpha_price()
            total_daily_alpha = get_total_miner_emissions()
            
            # Calculate conversion factor once
            total_daily_usd = alpha_price_usd * total_daily_alpha
            conversion_factor = 1.0 / total_daily_usd
            
            # Convert USD targets to raw weights in-place
            raw_weights = emission_targets_matrix * conversion_factor
            
            return raw_weights
            
        except Exception as e:
            bt.logging.error(f"Error calculating raw weights: {e}")
            return np.zeros_like(emission_targets_matrix)
    
    def _get_scaling_factor(self, brief: Dict[str, Any]) -> float:
        """Get scaling factor based on brief format."""
        brief_format = brief.get("format", "dedicated")
        
        scaling_factors = {
            "dedicated": YT_SCALING_FACTOR_DEDICATED,
            "ad-read": YT_SCALING_FACTOR_AD_READ
        }
        
        factor = scaling_factors.get(brief_format, YT_SCALING_FACTOR_DEDICATED)
        if brief_format not in scaling_factors:
            bt.logging.warning(f"Unknown brief format '{brief_format}', using dedicated")
        
        return factor 