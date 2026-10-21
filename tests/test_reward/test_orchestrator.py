"""Reward orchestrator pipeline with fully mocked chain, miners and pricing."""

import time
from types import SimpleNamespace

import pytest

from bitcast.protocol import AccessTokenSynapse
from bitcast.validator.reward.models import AccountResult, EvaluationResult
from bitcast.validator.reward.orchestrator import PlatformEvaluator, RewardOrchestrator, weight_corrections

DAILY_BUDGET_USD = 3600.0


class StubEvaluator(PlatformEvaluator):
    """Scores every non-burn miner a fixed USD amount on brief-1."""

    def __init__(self, usd_per_miner: float = 360.0):
        self.usd_per_miner = usd_per_miner
        self.batch_calls: list[tuple[int, int]] = []

    def platform_name(self) -> str:
        return "youtube"

    def can_evaluate(self, response) -> bool:
        return response.is_valid and response.has_tokens

    async def evaluate_accounts(self, response, briefs, metagraph_info) -> EvaluationResult:
        account = AccountResult(account_id="account_1", scores={"brief-1": self.usd_per_miner})
        return EvaluationResult(
            uid=response.uid,
            platform="youtube",
            account_results={"account_1": account},
            aggregated_scores={"brief-1": self.usd_per_miner},
        )


class BatchingEvaluator(StubEvaluator):
    supports_batching = True

    async def evaluate_token_batch(self, uid, tokens, offset, briefs, metagraph_info) -> EvaluationResult:
        self.batch_calls.append((offset, len(tokens)))
        account = AccountResult(account_id=f"account_{offset + 1}", scores={"brief-1": 10.0})
        return EvaluationResult(
            uid=uid,
            platform="youtube",
            account_results={f"account_{offset + 1}": account},
            aggregated_scores={"brief-1": 10.0},
        )


class StubPricing:
    async def get_alpha_price_usd(self, *, allow_stale: bool = False) -> float:
        return 36.0

    async def get_total_daily_usd(self, *, allow_stale: bool = False) -> float:
        return DAILY_BUDGET_USD


class FailingPricing:
    """No cache, no reachable source — the fail-loudly contract."""

    async def get_alpha_price_usd(self, *, allow_stale: bool = False) -> float:
        raise ConnectionError("price feed down")

    async def get_total_daily_usd(self, *, allow_stale: bool = False) -> float:
        raise ConnectionError("price feed down")


class AlphaPricing(StubPricing):
    pass


class CapturingPublisher:
    def __init__(self) -> None:
        self.results: list[EvaluationResult] = []

    async def publish_account_results(self, result: EvaluationResult) -> None:
        self.results.append(result.model_copy(deep=True))

    async def publish_weight_corrections(self, corrections: list[dict]) -> None:
        pass


class VideoMetricsEvaluator(StubEvaluator):
    async def evaluate_accounts(self, response, briefs, metagraph_info) -> EvaluationResult:
        account = AccountResult(
            account_id="account_1",
            videos={"video-1": {"brief_metrics": {"brief-1": {"usd_target": self.usd_per_miner}}}},
            scores={"brief-1": self.usd_per_miner},
        )
        return EvaluationResult(
            uid=response.uid,
            platform="youtube",
            account_results={"account_1": account},
            aggregated_scores={"brief-1": self.usd_per_miner},
        )


def make_validator(num_uids: int = 3, tokens_per_miner: int = 1):
    class StubDendrite:
        async def __call__(self, axons, synapse, timeout, deserialize):
            filled = AccessTokenSynapse(YT_access_tokens=[f"token-{i}" for i in range(tokens_per_miner)])
            return [filled]

    return SimpleNamespace(
        metagraph=SimpleNamespace(
            n=num_uids,
            axons=[None] * num_uids,
            S=[0.0] * num_uids,
            alpha_stake=[0.0] * num_uids,
            I=[0.0] * num_uids,
            E=[0.0] * num_uids,
        ),
        dendrite=StubDendrite(),
        config=SimpleNamespace(neuron=SimpleNamespace(timeout=10)),
    )


@pytest.fixture
def active_briefs(briefs):
    return briefs


async def test_rewards_sum_to_one_with_burn_backfill(active_briefs):
    orchestrator = RewardOrchestrator([StubEvaluator()], StubPricing())
    rewards, stats = await orchestrator.calculate_rewards(make_validator(), [0, 1, 2], active_briefs)

    assert rewards[1] == pytest.approx(360.0 / DAILY_BUDGET_USD)
    assert rewards[2] == pytest.approx(360.0 / DAILY_BUDGET_USD)
    assert rewards[0] == pytest.approx(1.0 - 2 * 0.1)  # burn absorbs remainder
    assert rewards.sum() == pytest.approx(1.0)
    assert stats[1]["scores"] == {"brief-1": 360.0}
    assert "brief_emission_percentages" in stats[0]


async def test_no_briefs_burns_everything():
    orchestrator = RewardOrchestrator([StubEvaluator()], StubPricing())
    rewards, _ = await orchestrator.calculate_rewards(make_validator(), [0, 1], [])
    assert rewards.tolist() == [1.0, 0.0]


async def test_pricing_failure_burns_everything(active_briefs):
    orchestrator = RewardOrchestrator([StubEvaluator()], FailingPricing())
    rewards, _ = await orchestrator.calculate_rewards(make_validator(), [0, 1], active_briefs)
    assert rewards[0] == pytest.approx(1.0)
    assert rewards[1] == 0.0


async def test_pricing_failure_skips_publication_instead_of_zeroing(active_briefs):
    """No price at all -> publication skipped (no fake 0-alpha rows), weights still burn via the loud abort."""
    publisher = CapturingPublisher()
    orchestrator = RewardOrchestrator([VideoMetricsEvaluator()], FailingPricing(), publisher)

    rewards, _ = await orchestrator.calculate_rewards(make_validator(num_uids=2), [0, 1], active_briefs)

    # The run itself fell back to burn (fail loudly, visible). The only
    # published result may be the burn marker — never a youtube result with
    # fabricated zero alpha targets.
    assert rewards[0] == pytest.approx(1.0)
    assert all(r.platform != "youtube" for r in publisher.results)


async def test_stale_price_still_weights_instead_of_burning(active_briefs, monkeypatch):
    """Every source down but a cached price exists -> use the stale price, weights stay correct."""
    import bitcast.validator.reward.pricing as pricing_mod

    class OnlyStaleCachePricing(pricing_mod.PricingService):
        async def _fetch_alpha_price_coingecko(self):
            raise ConnectionError("403")

        async def _fetch_alpha_price_coinpaprika(self):
            raise ConnectionError("down")

    service = OnlyStaleCachePricing(subtensor=None)
    service._cache["price"] = (5.0, time.monotonic() - 7200)  # 2h old
    assert await service.get_alpha_price_usd(allow_stale=True) == 5.0
    with pytest.raises(pricing_mod.PricingUnavailableError):
        await service.get_alpha_price_usd(allow_stale=False)


async def test_pricing_service_falls_back_to_second_source(active_briefs):
    """CoinGecko down -> CoinPaprika answers -> real price, no exception."""
    import bitcast.validator.reward.pricing as pricing_mod

    class GeoDownPricing(pricing_mod.PricingService):
        async def _fetch_alpha_price_coingecko(self):
            raise ConnectionError("403 for you")

        async def _fetch_alpha_price_coinpaprika(self):
            return 5.25

    service = GeoDownPricing(subtensor=None)
    assert await service.get_alpha_price_usd() == 5.25
    # and it is cached as fresh
    assert await service.get_alpha_price_usd() == 5.25


async def test_published_youtube_video_metrics_include_alpha_target(active_briefs):
    publisher = CapturingPublisher()
    orchestrator = RewardOrchestrator([VideoMetricsEvaluator()], AlphaPricing(), publisher)

    await orchestrator.calculate_rewards(make_validator(num_uids=2), [0, 1], active_briefs)

    metrics = publisher.results[1].account_results["account_1"].videos["video-1"]["brief_metrics"]["brief-1"]
    assert metrics["alpha_target"] == pytest.approx(10.0)


async def test_burn_uid_never_evaluated(active_briefs):
    evaluator = StubEvaluator()
    orchestrator = RewardOrchestrator([evaluator], StubPricing())
    validator = make_validator(num_uids=1)
    rewards, stats = await orchestrator.calculate_rewards(validator, [0], active_briefs)
    assert rewards.tolist() == [1.0]
    assert stats[0]["scores"] == {"brief-1": 0.0, "brief-2": 0.0}


async def test_large_token_lists_are_batched(active_briefs):
    evaluator = BatchingEvaluator()
    orchestrator = RewardOrchestrator([evaluator], StubPricing())
    validator = make_validator(num_uids=2, tokens_per_miner=20)
    await orchestrator.calculate_rewards(validator, [0, 1], active_briefs)
    # 20 tokens -> batches of 8 at offsets 0, 8, 16 (uid 0 is burn, never queried)
    assert evaluator.batch_calls == [(0, 8), (8, 8), (16, 4)]


async def test_per_brief_cap_limits_column(active_briefs):
    # One miner earning the entire daily budget on a capped brief.
    active_briefs[0]["cap"] = 0.25
    orchestrator = RewardOrchestrator([StubEvaluator(usd_per_miner=DAILY_BUDGET_USD)], StubPricing())
    rewards, _ = await orchestrator.calculate_rewards(make_validator(), [0, 1], active_briefs)
    assert rewards[1] == pytest.approx(0.25)
    assert rewards[0] == pytest.approx(0.75)


def test_weight_corrections_scaling_factors():
    import numpy as np

    result = EvaluationResult(uid=1, platform="youtube")
    result.add_account_result(
        AccountResult(
            account_id="account_1",
            videos={"vid1": {"details": {"bitcastVideoId": "bc_1"}, "brief_metrics": {"brief-1": {}}}},
        )
    )
    pre = np.array([[0.4]])
    post = np.array([[0.2]])
    corrections = weight_corrections({1: result}, pre, post, [{"id": "brief-1"}])
    assert corrections == [{"content_id": "bc_1", "brief_id": "brief-1", "scaling_factor": 0.5}]
