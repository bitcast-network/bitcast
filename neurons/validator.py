"""Bitcast validator entry point: ``python -m neurons.validator``."""

import asyncio

import bittensor as bt

from bitcast.config import BitcastConfig, build_config, get_settings
from bitcast.loki import init_loki, shutdown_loki
from bitcast.sentry import init_sentry
from bitcast.utils.publisher import Publisher
from bitcast.validator import forward
from bitcast.validator.base import BaseValidatorNeuron
from bitcast.validator.llm.client import LLMClient
from bitcast.validator.reward.orchestrator import RewardOrchestrator
from bitcast.validator.reward.pricing import PricingService
from bitcast.validator.youtube.cache import HistoricalVideoRegistry
from bitcast.validator.youtube.evaluator import YouTubeEvaluator


class Validator(BaseValidatorNeuron):
    """Runs the Bitcast reward cycle and sets weights on chain."""

    def __init__(self, config: BitcastConfig) -> None:
        super().__init__(config)
        settings = get_settings()
        state = config.state_path()

        # Initialise Loki log aggregation with per-validator labels
        from bitcast import __version__

        init_loki(
            settings,
            labels={
                "uid": str(self.uid),
                "hotkey": self.wallet.hotkey.ss58_address,
                "netuid": str(config.netuid),
                "mechid": str(settings.mechid),
                "neuron": "validator",
                "version": __version__,
            },
        )

        history = None
        if not settings.eco_mode:
            history = HistoricalVideoRegistry(state / "historical_videos.jsonl")
        # LLM cache lives at state/cache/llm.jsonl — persists across restarts
        # on EFS as a plain JSONL file (NFS-safe, editable from cache-admin).
        self.llm = llm = LLMClient(cache_path=state / "cache" / "llm.jsonl")
        # YouTube search fallback cache — saves 100 API credits per channel
        # on cold start. Also JSONL for the same NFS-safety reasons.
        evaluator = YouTubeEvaluator(
            llm=llm,
            history=history,
            search_cache_path=state / "cache" / "youtube_search.jsonl",
        )
        publisher = Publisher(self.wallet) if settings.enable_data_publish else None
        pricing = PricingService(self.subtensor, netuid=config.netuid, mechid=settings.mechid)
        self.orchestrator = RewardOrchestrator(evaluators=[evaluator], pricing=pricing, publisher=publisher)
        # Cache path for briefs persistence — used by forward.py on each cycle.
        self.briefs_cache_path = state / "briefs.json"

        # Compact append-only JSONL caches on startup. Sliding-TTL refreshes
        # and per-restart dedup resets accumulate stale lines across runs;
        # compacting once per boot bounds file growth to one process lifetime.
        # Safe on a running validator (tmp + rename); EFS quirk: if another
        # process holds an open fd on the old inode it keeps the stale view,
        # but the validator is the only reader and it just opened these files.
        llm_before = llm.compact_cache()
        search_before = evaluator.compact_search_cache()
        history_before = history.compact() if history is not None else 0
        bt.logging.info(f"Cache compaction on boot: llm={llm_before} search={search_before} history={history_before}")

    async def forward(self) -> None:
        await forward.forward(self, self.orchestrator)


def main() -> None:
    bt.logging.set_console()
    config = build_config("validator")
    init_sentry(get_settings())
    bt.logging.info(f"Starting validator with config: {config}")

    async def _run() -> None:
        validator = Validator(config)
        try:
            await validator.run()
        finally:
            await validator.llm.aclose()
            await shutdown_loki()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
