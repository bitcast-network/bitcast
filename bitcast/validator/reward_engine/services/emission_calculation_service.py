"""Handles emission calculation - extracted from reward.py calculate_emission_targets and calculate_raw_weights."""

from typing import List, Dict, Any
import numpy as np
import bittensor as bt
from ..interfaces.emission_calculator import EmissionCalculator
from ..models.score_matrix import ScoreMatrix
from ..models.emission_target import EmissionTarget
from ...utils.config import (
    YT_SCALING_FACTOR_DEDICATED, 
    YT_SCALING_FACTOR_AD_READ, 
    YT_SMOOTHING_FACTOR
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
        # Optimize: Work directly with the matrix to avoid copies
        emission_targets_matrix = self._calculate_emission_targets_matrix(
            score_matrix.matrix, briefs
        )
        
        # Convert USD targets to raw weights in-place for efficiency
        raw_weights_matrix = self._calculate_raw_weights(emission_targets_matrix)
        
        # Create EmissionTarget objects for each brief
        targets = []
        for brief_idx, brief in enumerate(briefs):
            # Extract weights for this brief
            per_miner_weights = raw_weights_matrix[:, brief_idx] if brief_idx < raw_weights_matrix.shape[1] else []
            
            # Calculate USD target for this brief
            usd_target = float(np.sum(emission_targets_matrix[:, brief_idx])) if brief_idx < emission_targets_matrix.shape[1] else 0.0
            
            target = EmissionTarget(
                brief_id=brief["id"],
                usd_target=usd_target,
                allocation_details={
                    "per_miner_weights": per_miner_weights.tolist(),
                    "brief_format": brief.get("format", "dedicated")
                },
                scaling_factors={
                    "scaling_factor": self._get_scaling_factor(brief),
                    "boost_factor": brief.get("boost", 1.0),
                    "smoothing_factor": YT_SMOOTHING_FACTOR
                }
            )
            targets.append(target)
        
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
            return np.array([])
        
        # Work with a copy to avoid modifying the original
        emission_targets = scores_matrix.astype(np.float64, copy=True)
        
        # Process each brief (column) efficiently
        for brief_idx, brief in enumerate(briefs):
            if brief_idx >= emission_targets.shape[1]:
                continue
                
            # Apply scaling factor in-place
            scaling_factor = self._get_scaling_factor(brief)
            emission_targets[:, brief_idx] *= scaling_factor
            
            # Apply boost multiplier (before smoothing and clipping)
            boost_factor = brief.get("boost", 1.0)
            if boost_factor != 1.0:
                bt.logging.info(f"Applying boost {boost_factor}x to brief {brief.get('id', 'unknown')}")
            emission_targets[:, brief_idx] *= boost_factor
            
            # Store scaled scores before smoothing (for readjustment)
            scaled_scores = emission_targets[:, brief_idx].copy()
            
            # Apply smoothing with optimization for positive values
            positive_scores = np.maximum(emission_targets[:, brief_idx], 0)
            smoothed_scores = np.power(positive_scores, YT_SMOOTHING_FACTOR)
            
            # Readjust to maintain scaled proportions
            avg_scaled = np.mean(np.maximum(scaled_scores, 0))
            avg_smoothed = np.mean(smoothed_scores)
            
            if avg_smoothed > 0:
                emission_targets[:, brief_idx] = smoothed_scores * (avg_scaled / avg_smoothed)
            else:
                emission_targets[:, brief_idx] = smoothed_scores
        
        return emission_targets
    
    def _calculate_raw_weights(self, emission_targets_matrix: np.ndarray) -> np.ndarray:
        """
        Convert USD emission targets to raw weights.
        Optimized for memory efficiency.
        """
        if emission_targets_matrix.size == 0:
            return np.array([])
        
        try:
            alpha_price_usd = get_bitcast_alpha_price()
            total_daily_alpha = get_total_miner_emissions()
                        
            # Calculate conversion factor once
            conversion_factor = 1.0 / (alpha_price_usd * total_daily_alpha)
            
            # Convert USD targets to raw weights in-place
            raw_weights = emission_targets_matrix * conversion_factor
            
            bt.logging.debug(f"Max raw weight: {np.max(raw_weights):.6f}")
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