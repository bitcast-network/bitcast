"""Main validation loop: fetch briefs, run the reward cycle, update scores."""

import asyncio
from typing import Any

import bittensor as bt

from bitcast.config import VALIDATOR_STEPS_INTERVAL, VALIDATOR_WAIT
from bitcast.events import log_event
from bitcast.utils.briefs import get_briefs
from bitcast.validator.reward.orchestrator import RewardOrchestrator


def get_all_uids(validator: Any) -> list[int]:
    """Every uid on the metagraph, burn UID (0) first."""
    return list(range(int(validator.metagraph.n)))


async def forward(validator: Any, orchestrator: RewardOrchestrator) -> None:
    """One validator step.

    Most steps just sleep; every ``VALIDATOR_STEPS_INTERVAL`` steps (~4 h) the
    full reward cycle runs: fetch briefs, query and evaluate all miners, and
    fold the resulting reward vector into the moving-average scores that
    ``sync()`` later sets on chain.
    """
    if validator.step % VALIDATOR_STEPS_INTERVAL != 0:
        await asyncio.sleep(VALIDATOR_WAIT)
        return

    bt.logging.info(f"Starting reward cycle at step {validator.step}")
    briefs_cache_path = getattr(validator, "briefs_cache_path", None)
    try:
        briefs = await get_briefs(cache_path=briefs_cache_path)
    except ConnectionError as err:
        bt.logging.error(f"Could not fetch briefs: {err}")
        briefs = []

    uids = get_all_uids(validator)
    if orchestrator.publisher is not None:
        orchestrator.publisher.new_run()

    rewards, stats_list = await orchestrator.calculate_rewards(validator, uids, briefs)

    earning = sum(1 for reward in rewards[1:] if reward > 0)
    bt.logging.info(f"Reward cycle complete: {len(briefs)} briefs, {earning} earning miners, burn={rewards[0]:.4f}")

    # Structured metric line for Grafana Loki dashboards.
    # LogQL can parse this via | json to chart per-validator comparisons.
    log_event(
        {
            "event": "reward_cycle",
            "step": validator.step,
            "briefs": len(briefs),
            "earning_miners": earning,
            "total_miners": len(uids),
            "burn": round(float(rewards[0]), 6),
            "videos_evaluated": len(stats_list),
        }
    )

    validator.update_scores(rewards, uids)
    await asyncio.sleep(VALIDATOR_WAIT)
