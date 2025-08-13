"""Main reward calculation orchestrator - replaces monolithic reward.py functions."""

from typing import List, Tuple, Dict, Any
import numpy as np
import bittensor as bt
from bitcast.validator.utils.briefs import get_briefs
from bitcast.validator.platforms.youtube.utils import state
from ..utils.run_manager import generate_current_run_id
from ..utils.streaming_publisher import publish_miner_accounts_safe, log_streaming_status

from .services.miner_query_service import MinerQueryService
from .services.platform_registry import PlatformRegistry
from .services.score_aggregation_service import ScoreAggregationService
from .services.emission_calculation_service import EmissionCalculationService
from .services.reward_distribution_service import RewardDistributionService
from .models.evaluation_result import EvaluationResultCollection, EvaluationResult
from .models.miner_response import MinerResponse


class RewardOrchestrator:
    """Coordinates the complete reward calculation workflow."""
    
    def __init__(
        self,
        miner_query_service: MinerQueryService = None,
        platform_registry: PlatformRegistry = None,
        score_aggregator: ScoreAggregationService = None,
        emission_calculator: EmissionCalculationService = None,
        reward_distributor: RewardDistributionService = None
    ):
        self.miner_query = miner_query_service or MinerQueryService()
        self.platforms = platform_registry or PlatformRegistry()
        self.score_aggregator = score_aggregator or ScoreAggregationService()
        self.emission_calculator = emission_calculator or EmissionCalculationService()
        self.reward_distributor = reward_distributor or RewardDistributionService()
    
    async def calculate_rewards(
        self, 
        validator_self, 
        uids: List[int]
    ) -> Tuple[np.ndarray, List[dict]]:
        """Main entry point for reward calculation workflow."""
        try:
            # 1. Get content briefs
            try:
                briefs = get_briefs()
            except ConnectionError as e:
                bt.logging.error(f"Failed to fetch content briefs: {e}")
                return self._no_briefs_fallback(uids)
                
            if not briefs:
                return self._no_briefs_fallback(uids)
            
            bt.logging.info(f"Processing {len(briefs)} briefs for {len(uids)} miners sequentially")
            
            # 2. Generate run ID for streaming per-account publishing  
            run_id = generate_current_run_id(validator_self.wallet)
            bt.logging.info(f"🔄 Generated run ID for validation cycle: {run_id}")
            
            # Log streaming publishing status
            log_streaming_status(len(uids))
            
            # 3. Process miners sequentially to prevent token expiration
            evaluation_results = EvaluationResultCollection()
            
            for uid in uids:
                # Query this miner just-in-time
                miner_response = await self.miner_query.query_single_miner(validator_self, uid)
                
                # Evaluate immediately while token is fresh
                result = await self._evaluate_single_miner(miner_response, briefs, validator_self.metagraph)
                evaluation_results.add_result(uid, result)
                
                # 🌊 STREAMING: Publish this miner's accounts immediately
                await publish_miner_accounts_safe(result, run_id, validator_self.wallet)
            
            # 4. Aggregate scores across platforms
            bt.logging.info("🔄 PHASE 4: Aggregating individual video scores into score matrix")
            score_matrix = self.score_aggregator.aggregate_scores(evaluation_results, briefs)
            bt.logging.info(f"Score aggregation complete: {score_matrix.matrix.shape} matrix created")
                        
            # 5. Reset state for next evaluation cycle
            state.reset_scored_videos()
            
            # 6. Calculate emission targets
            bt.logging.info("💰 PHASE 5: Converting scores to USD emission targets")
            emission_targets = self.emission_calculator.calculate_targets(score_matrix, briefs)
            
            # 7. Distribute final rewards
            bt.logging.info("🎯 PHASE 6: Distributing final rewards to miners")
            rewards, stats_list = self.reward_distributor.calculate_distribution(
                emission_targets, evaluation_results, briefs, uids
            )
            
            total_rewards = float(np.sum(rewards))
            non_zero_miners = np.count_nonzero(rewards)
            bt.logging.info(f"✅ Successfully calculated rewards: {total_rewards:.6f} total, {non_zero_miners}/{len(uids)} miners rewarded")
            return rewards, stats_list
            
        except Exception as e:
            bt.logging.error(f"Sequential reward calculation failed: {e}")
            return self._error_fallback(uids)
    
    async def _evaluate_single_miner(
        self, 
        miner_response: MinerResponse, 
        briefs: List[dict],
        metagraph
    ) -> EvaluationResult:
        """Evaluate a single miner's response immediately after querying."""
        uid = miner_response.uid
        
        try:
            # Special handling for burn UID
            if uid == 0:
                bt.logging.debug(f"Burn UID {uid}: setting scores to 0")
                return EvaluationResult(
                    uid=uid,
                    platform="burn",
                    aggregated_scores={brief["id"]: 0.0 for brief in briefs}
                )
            
            # Find platform evaluator for this response
            evaluator = self.platforms.get_evaluator_for_response(miner_response)
            
            if evaluator:
                bt.logging.debug(f"Using {evaluator.platform_name()} for UID {uid}")
                
                # Extract metagraph info and evaluate
                metagraph_info = self._extract_metagraph_info(metagraph, uid)
                result = await evaluator.evaluate_accounts(miner_response, briefs, metagraph_info)
                
                bt.logging.debug(f"Evaluated UID {uid}: {len(result.account_results)} accounts")
                return result
            else:
                bt.logging.warning(f"No evaluator found for UID {uid}")
                return EvaluationResult(
                    uid=uid,
                    platform="unknown",
                    aggregated_scores={brief["id"]: 0.0 for brief in briefs}
                )
                
        except Exception as e:
            bt.logging.error(f"Failed to evaluate UID {uid}: {e}")
            return EvaluationResult(
                uid=uid,
                platform="error",
                aggregated_scores={brief["id"]: 0.0 for brief in briefs}
            )
    
    def _extract_metagraph_info(self, metagraph, uid: int) -> Dict[str, Any]:
        """Extract relevant metagraph information for a UID."""
        if metagraph is None:
            return {}
        
        try:
            info = {}
            
            # Safely extract metagraph fields
            if hasattr(metagraph, 'S') and len(metagraph.S) > uid:
                info['stake'] = float(metagraph.S[uid])
            
            if hasattr(metagraph, 'alpha_stake') and len(metagraph.alpha_stake) > uid:
                info['alpha_stake'] = float(metagraph.alpha_stake[uid])
            else:
                info['alpha_stake'] = 0.0
            
            if hasattr(metagraph, 'I') and len(metagraph.I) > uid:
                info['incentive'] = float(metagraph.I[uid])
                
            if hasattr(metagraph, 'E') and len(metagraph.E) > uid:
                info['emission'] = float(metagraph.E[uid])
            
            return info
            
        except Exception as e:
            bt.logging.error(f"Failed to extract metagraph info for UID {uid}: {e}")
            return {}
    
    def _no_briefs_fallback(self, uids: List[int]) -> Tuple[np.ndarray, List[dict]]:
        """Handle case when no content briefs are available."""
        bt.logging.info("No briefs available - using fallback rewards")
        rewards = np.array([1.0 if uid == 0 else 0.0 for uid in uids])
        stats_list = [{"scores": {}, "uid": uid} for uid in uids]
        return rewards, stats_list
    
    def _error_fallback(self, uids: List[int]) -> Tuple[np.ndarray, List[dict]]:
        """Handle errors with safe fallback rewards."""
        bt.logging.error("Using error fallback - all rewards to burn UID")
        rewards = np.array([1.0 if uid == 0 else 0.0 for uid in uids])
        stats_list = [{"scores": {}, "uid": uid} for uid in uids]
        return rewards, stats_list