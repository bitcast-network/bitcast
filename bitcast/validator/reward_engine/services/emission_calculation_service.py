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
        bt.logging.info("=== EMISSION CALCULATION START ===")
        bt.logging.info(f"Input: {score_matrix.matrix.shape[0]} miners, {len(briefs)} briefs")
        bt.logging.info(f"Score matrix shape: {score_matrix.matrix.shape}")
        bt.logging.info(f"Score matrix range: min={np.min(score_matrix.matrix):.6f}, max={np.max(score_matrix.matrix):.6f}, mean={np.mean(score_matrix.matrix):.6f}")
        
        # Step 1: Convert scores to USD emission targets with scaling factors
        bt.logging.info("Step 1: Converting scores to USD emission targets")
        emission_targets_matrix = self._calculate_emission_targets_matrix(
            score_matrix.matrix, briefs
        )
        
        # Step 2: Convert USD targets to raw weights using alpha price and total emissions
        bt.logging.info("Step 2: Converting USD targets to raw weights")
        raw_weights_matrix = self._calculate_raw_weights(emission_targets_matrix)
        
        # Step 3: Create EmissionTarget objects for each brief
        bt.logging.info("Step 3: Creating EmissionTarget objects")
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
            
            bt.logging.info(
                f"Brief {brief.get('id', f'brief_{brief_idx}')}: "
                f"format={brief.get('format', 'dedicated')}, "
                f"scaling_factor={scaling_factor}, boost_factor={boost_factor}x, "
                f"usd_target=${usd_target:.2f}, total_weight={brief_weight_sum:.6f}"
            )
            
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
        bt.logging.info("--- Converting Scores to USD Targets ---")
        
        if scores_matrix.size == 0:
            bt.logging.warning("Empty score matrix - returning empty array")
            return np.array([])
        
        bt.logging.info(f"Input scores matrix: shape={scores_matrix.shape}, non_zero_entries={np.count_nonzero(scores_matrix)}")
        
        # Work with a copy to avoid modifying the original
        emission_targets = scores_matrix.astype(np.float64, copy=True)
        bt.logging.info(f"Step 3a: Created emission targets matrix copy")
        
        # Process each brief (column) efficiently
        bt.logging.info(f"Step 3b: Processing {len(briefs)} briefs with scaling factors")
        
        for brief_idx, brief in enumerate(briefs):
            if brief_idx >= emission_targets.shape[1]:
                bt.logging.warning(f"Brief {brief_idx} exceeds matrix columns ({emission_targets.shape[1]}) - skipping")
                continue
            
            brief_id = brief.get('id', f'brief_{brief_idx}')
            original_sum = float(np.sum(emission_targets[:, brief_idx]))
                
            # Apply scaling factor in-place
            scaling_factor = self._get_scaling_factor(brief)
            emission_targets[:, brief_idx] *= scaling_factor
            after_scaling_sum = float(np.sum(emission_targets[:, brief_idx]))
            
            # Apply boost multiplier
            boost_factor = brief.get("boost", 1.0)
            if boost_factor != 1.0:
                bt.logging.info(f"Step 3c: Applying boost {boost_factor}x to brief {brief_id}")
            emission_targets[:, brief_idx] *= boost_factor
            final_sum = float(np.sum(emission_targets[:, brief_idx]))
            
            bt.logging.info(
                f"Brief {brief_id}: score_sum={original_sum:.6f} "
                f"-> scaled=${after_scaling_sum:.6f} -> boosted=${final_sum:.6f} "
                f"(scaling_factor={scaling_factor}, boost={boost_factor}x)"
            )
                    
        total_usd_emission = float(np.sum(emission_targets))
        bt.logging.info(f"Step 3d: Total USD emission targets: ${total_usd_emission:.2f}")
        return emission_targets
    
    def _calculate_raw_weights(self, emission_targets_matrix: np.ndarray) -> np.ndarray:
        """
        Convert USD emission targets to raw weights.
        Optimized for memory efficiency.
        """
        bt.logging.info("--- Converting USD Targets to Raw Weights ---")
        
        if emission_targets_matrix.size == 0:
            bt.logging.warning("Empty emission targets matrix - returning empty array")
            return np.array([])
        
        total_usd_targets = float(np.sum(emission_targets_matrix))
        bt.logging.info(f"Step 2a: Input USD targets total: ${total_usd_targets:.2f}")
        
        try:
            alpha_price_usd = get_bitcast_alpha_price()
            total_daily_alpha = get_total_miner_emissions()
            
            bt.logging.info(f"Step 2b: Market data - Alpha price: ${alpha_price_usd:.6f}, Daily emissions: {total_daily_alpha:.2f} alpha")
                        
            # Calculate conversion factor once
            total_daily_usd = alpha_price_usd * total_daily_alpha
            conversion_factor = 1.0 / total_daily_usd
            
            bt.logging.info(f"Step 2c: Total daily USD pool: ${total_daily_usd:.2f}, Conversion factor: {conversion_factor:.8f}")
            
            # Convert USD targets to raw weights in-place
            raw_weights = emission_targets_matrix * conversion_factor
            
            total_weights = float(np.sum(raw_weights))
            max_weight = float(np.max(raw_weights))
            non_zero_weights = np.count_nonzero(raw_weights)
            
            bt.logging.info(
                f"Step 2d: Raw weights calculated - Total: {total_weights:.6f}, "
                f"Max: {max_weight:.6f}, Non-zero entries: {non_zero_weights}/{raw_weights.size}"
            )
            
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