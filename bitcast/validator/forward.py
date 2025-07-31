import time
import bittensor as bt

# New reward system imports
from bitcast.validator.reward_engine.orchestrator import RewardOrchestrator
from bitcast.validator.platforms.youtube.youtube_evaluator import YouTubeEvaluator

from bitcast.utils.uids import get_all_uids
from bitcast.validator.utils.publish_stats import publish_stats
from bitcast.validator.utils.briefs import get_briefs
from bitcast.validator.utils.config import VALIDATOR_WAIT, VALIDATOR_STEPS_INTERVAL

# Singleton for efficiency
_reward_orchestrator = None


def get_reward_orchestrator() -> RewardOrchestrator:
    """Get reward orchestrator singleton."""
    global _reward_orchestrator
    if _reward_orchestrator is None:
        # Create services with dependency injection
        from bitcast.validator.reward_engine.services.miner_query_service import MinerQueryService
        from bitcast.validator.reward_engine.services.platform_registry import PlatformRegistry
        from bitcast.validator.reward_engine.services.score_aggregation_service import ScoreAggregationService
        from bitcast.validator.reward_engine.services.emission_calculation_service import EmissionCalculationService
        from bitcast.validator.reward_engine.services.reward_distribution_service import RewardDistributionService
        
        # Create platform registry and register YouTube evaluator
        platform_registry = PlatformRegistry()
        youtube_evaluator = YouTubeEvaluator()
        platform_registry.register_evaluator(youtube_evaluator)
        
        # Create orchestrator with all services
        _reward_orchestrator = RewardOrchestrator(
            miner_query_service=MinerQueryService(),
            platform_registry=platform_registry,
            score_aggregator=ScoreAggregationService(),
            emission_calculator=EmissionCalculationService(),
            reward_distributor=RewardDistributionService()
        )
    
    return _reward_orchestrator


async def forward(self):
    """Forward function using the new modular reward system."""
    if self.step % VALIDATOR_STEPS_INTERVAL != 0:
        time.sleep(VALIDATOR_WAIT)
        return

    bt.logging.info(f"Starting forward pass at step {self.step}")

    try:
        # Get all miner UIDs
        miner_uids = get_all_uids(self)
        
        # Use the new reward orchestrator
        orchestrator = get_reward_orchestrator()
        rewards, yt_stats_list = await orchestrator.calculate_rewards(self, miner_uids)

        # Log the rewards for monitoring purposes
        bt.logging.info("UID Rewards:")
        for i, (uid, reward) in enumerate(zip(miner_uids, rewards)):
            bt.logging.info(f"UID {uid}: {reward}")
            yt_stats_list[i]["reward"] = float(reward)

        # Extract blacklisted UIDs from the stats
        blacklisted_uids = []
        for uid, yt_stats in zip(miner_uids, yt_stats_list):
            if yt_stats.get("yt_account", {}).get("blacklisted", False):
                blacklisted_uids.append(uid)
                bt.logging.info(f"UID {uid} is blacklisted")

        # Update the scores based on the rewards
        self.update_scores(rewards, miner_uids, blacklisted_uids)

        publish_stats(self.wallet, yt_stats_list, miner_uids)
        
    except Exception as e:
        bt.logging.error(f"Error in forward pass: {e}")

    time.sleep(VALIDATOR_WAIT)
