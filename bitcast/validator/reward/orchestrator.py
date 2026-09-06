"""Coordinates the reward pipeline: query -> evaluate -> aggregate -> constrain -> emit."""

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

import bittensor as bt
import numpy as np

from bitcast.config import BURN_UID, CREDENTIAL_BATCH_SIZE, MAX_ACCOUNTS_PER_SYNAPSE
from bitcast.protocol import AccessTokenSynapse
from bitcast.validator.reward import scaler
from bitcast.validator.reward.models import EmissionTarget, EvaluationResult, MinerResponse, ScoreMatrix
from bitcast.validator.reward.pricing import PricingService


class PlatformEvaluator(ABC):
    """Evaluates one platform's accounts (e.g. YouTube channels) against briefs."""

    supports_batching: bool = False

    @abstractmethod
    def platform_name(self) -> str:
        """Short platform identifier, e.g. ``"youtube"``."""

    @abstractmethod
    def can_evaluate(self, response: MinerResponse) -> bool:
        """Whether this evaluator understands the given miner response."""

    @abstractmethod
    async def evaluate_accounts(
        self, response: MinerResponse, briefs: list[dict], metagraph_info: dict
    ) -> EvaluationResult:
        """Evaluate every account in the response against the briefs."""

    async def evaluate_token_batch(
        self, uid: int, tokens: list[str], offset: int, briefs: list[dict], metagraph_info: dict
    ) -> EvaluationResult:
        """Evaluate a slice of tokens; only called when ``supports_batching``."""
        raise NotImplementedError

    def reset_cycle_state(self) -> None:  # noqa: B027 — optional hook, not abstract
        """Clear any per-cycle state (e.g. cross-miner video dedup)."""


@runtime_checkable
class ResultPublisher(Protocol):
    """Optional sink for per-miner evaluation data (dashboard transparency).

    ``runtime_checkable`` so tests can assert an implementation covers the whole
    surface; ``isinstance`` only verifies the methods exist, which is the point.
    """

    def new_run(self) -> str:
        """Start a new run id, grouping one reward cycle's payloads."""
        ...

    async def publish_account_results(self, result: EvaluationResult) -> None: ...

    async def publish_weight_corrections(self, corrections: list[dict]) -> None: ...


class RewardOrchestrator:
    """Runs the full reward cycle and produces the normalized reward vector."""

    def __init__(
        self,
        evaluators: list[PlatformEvaluator],
        pricing: PricingService,
        publisher: ResultPublisher | None = None,
    ) -> None:
        self.evaluators = evaluators
        self.pricing = pricing
        self.publisher = publisher

    async def calculate_rewards(
        self, validator: Any, uids: list[int], briefs: list[dict]
    ) -> tuple[np.ndarray, list[dict]]:
        """Query, evaluate and score all miners against the active briefs.

        Returns a reward vector aligned with ``uids`` that sums to 1.0 (the
        burn UID absorbs any unallocated emission) and a per-miner stats list.
        """
        if not briefs:
            bt.logging.warning("No active briefs; falling back to full burn.")
            return self._burn_fallback(uids)

        try:
            results: dict[int, EvaluationResult] = {}
            for uid in uids:
                # Sequential on purpose: OAuth access tokens expire, so each
                # miner is queried just-in-time before its evaluation.
                response = await self._query_miner(validator, uid)
                result = await self._evaluate_miner(validator, response, briefs)
                results[uid] = result
                await self._publish_safe(result)

            score_matrix = self._aggregate_scores(results, briefs)
            for evaluator in self.evaluators:
                evaluator.reset_cycle_state()

            targets = await self._calculate_emission_targets(score_matrix, briefs)
            rewards, stats_list, pre_weights, post_weights = self._distribute(targets, results, briefs, uids)
            await self._publish_corrections_safe(results, pre_weights, post_weights, briefs)

            for result in results.values():
                result.account_results.clear()  # release video payloads
            return rewards, stats_list
        except Exception as err:
            bt.logging.error(f"Reward calculation failed: {err!r}; falling back to full burn.")
            return self._burn_fallback(uids)

    # --- Query ---------------------------------------------------------------

    async def _query_miner(self, validator: Any, uid: int) -> MinerResponse:
        try:
            responses = await validator.dendrite(
                axons=[validator.metagraph.axons[uid]],
                synapse=AccessTokenSynapse(),
                timeout=validator.config.neuron.timeout,
                deserialize=False,
            )
            return MinerResponse.from_synapse(uid, responses[0] if responses else None)
        except Exception as err:
            return MinerResponse.error(uid, str(err))

    # --- Evaluate ------------------------------------------------------------

    async def _evaluate_miner(self, validator: Any, response: MinerResponse, briefs: list[dict]) -> EvaluationResult:
        uid = response.uid
        zero_scores = {brief["id"]: 0.0 for brief in briefs}
        if uid == BURN_UID:
            return EvaluationResult(uid=uid, platform="burn", aggregated_scores=zero_scores)

        evaluator = self._evaluator_for(response)
        if evaluator is None:
            return EvaluationResult(uid=uid, platform="unknown", aggregated_scores=zero_scores)

        try:
            metagraph_info = self._metagraph_info(validator.metagraph, uid)
            total_tokens = len(response.tokens[:MAX_ACCOUNTS_PER_SYNAPSE])
            if total_tokens <= CREDENTIAL_BATCH_SIZE or not evaluator.supports_batching:
                return await evaluator.evaluate_accounts(response, briefs, metagraph_info)
            return await self._evaluate_in_batches(validator, uid, total_tokens, evaluator, briefs, metagraph_info)
        except Exception as err:
            bt.logging.warning(f"Evaluation failed for uid {uid}: {err!r}")
            return EvaluationResult(uid=uid, platform="error", aggregated_scores=zero_scores)

    def _evaluator_for(self, response: MinerResponse) -> PlatformEvaluator | None:
        if not response.is_valid:
            return None
        return next((evaluator for evaluator in self.evaluators if evaluator.can_evaluate(response)), None)

    async def _evaluate_in_batches(
        self,
        validator: Any,
        uid: int,
        total_tokens: int,
        evaluator: PlatformEvaluator,
        briefs: list[dict],
        metagraph_info: dict,
    ) -> EvaluationResult:
        """Evaluate a large token list in slices, re-querying to keep tokens fresh."""
        combined = EvaluationResult(
            uid=uid,
            platform=evaluator.platform_name(),
            metagraph_info=metagraph_info,
            aggregated_scores={brief["id"]: 0.0 for brief in briefs},
        )
        num_batches = (total_tokens + CREDENTIAL_BATCH_SIZE - 1) // CREDENTIAL_BATCH_SIZE
        for batch_idx in range(num_batches):
            fresh = await self._query_miner(validator, uid)
            offset = batch_idx * CREDENTIAL_BATCH_SIZE
            batch_tokens = fresh.tokens[offset : offset + CREDENTIAL_BATCH_SIZE]
            if not batch_tokens:
                break
            batch_result = await evaluator.evaluate_token_batch(uid, batch_tokens, offset, briefs, metagraph_info)
            combined.merge(batch_result)
        return combined

    @staticmethod
    def _metagraph_info(metagraph: Any, uid: int) -> dict:
        try:
            if metagraph is None or len(metagraph.S) <= uid:
                return {}
            return {
                "stake": float(metagraph.S[uid]),
                "alpha_stake": float(metagraph.alpha_stake[uid]) if len(metagraph.alpha_stake) > uid else 0.0,
                "incentive": float(metagraph.I[uid]),
                "emission": float(metagraph.E[uid]),
            }
        except (AttributeError, IndexError, TypeError):
            return {}

    # --- Aggregate and convert ------------------------------------------------

    @staticmethod
    def _aggregate_scores(results: dict[int, EvaluationResult], briefs: list[dict]) -> ScoreMatrix:
        """Sum per-account USD scores into a miners x briefs matrix (row order = uids order)."""
        matrix = ScoreMatrix.empty(len(results), len(briefs))
        for miner_idx, result in enumerate(results.values()):
            for brief_idx, brief in enumerate(briefs):
                total = sum(account.scores.get(brief["id"], 0.0) for account in result.account_results.values())
                matrix.matrix[miner_idx, brief_idx] = total
        return matrix

    async def _calculate_emission_targets(self, score_matrix: ScoreMatrix, briefs: list[dict]) -> list[EmissionTarget]:
        """Convert USD scores to weights as fractions of the daily emission budget."""
        usd_matrix = score_matrix.matrix
        try:
            total_daily_usd = await self.pricing.get_total_daily_usd()
            raw_weights = usd_matrix / total_daily_usd if total_daily_usd > 0 else np.zeros_like(usd_matrix)
        except Exception as err:
            bt.logging.warning(f"Emission pricing unavailable ({err!r}); zeroing weights.")
            raw_weights = np.zeros_like(usd_matrix)

        return [
            EmissionTarget(
                brief_id=brief["id"],
                usd_target=float(usd_matrix[:, brief_idx].sum()),
                per_miner_weights=raw_weights[:, brief_idx].tolist(),
                brief_format=brief.get("format", "dedicated"),
                boost_factor=brief.get("boost", 1.0),
            )
            for brief_idx, brief in enumerate(briefs)
        ]

    # --- Distribute -------------------------------------------------------------

    def _distribute(
        self,
        targets: list[EmissionTarget],
        results: dict[int, EvaluationResult],
        briefs: list[dict],
        uids: list[int],
    ) -> tuple[np.ndarray, list[dict], np.ndarray, np.ndarray]:
        pre_weights = np.zeros((len(uids), len(targets)), dtype=np.float64)
        for brief_idx, target in enumerate(targets):
            weights = target.per_miner_weights[: len(uids)]
            pre_weights[: len(weights), brief_idx] = weights

        post_weights = scaler.apply_emission_constraints(pre_weights, briefs)
        rewards = scaler.sum_to_final_rewards(post_weights, uids)
        rewards = scaler.allocate_subnet_treasury(rewards, uids)

        brief_emission_percentages = {
            brief["id"]: float(post_weights[:, brief_idx].sum()) for brief_idx, brief in enumerate(briefs)
        }
        stats_list = self._stats_list(results, uids, brief_emission_percentages)
        return rewards, stats_list, pre_weights, post_weights

    @staticmethod
    def _stats_list(
        results: dict[int, EvaluationResult], uids: list[int], brief_emission_percentages: dict[str, float]
    ) -> list[dict]:
        stats_list = []
        for uid in uids:
            result = results.get(uid)
            if result is None:
                stats_list.append({"uid": uid, "scores": {}})
                continue
            stats_list.append({"uid": uid, "scores": result.aggregated_scores, "metagraph": result.metagraph_info})
        if stats_list:
            stats_list[0]["brief_emission_percentages"] = brief_emission_percentages
        return stats_list

    # --- Publishing (optional) ----------------------------------------------

    @staticmethod
    def _add_alpha_targets(result: EvaluationResult, alpha_price_usd: float, total_daily_usd: float = 0.0) -> None:
        """Add the V1-compatible alpha target and emission weight to each metric.

        ``weight`` is the video-brief's share of the day's whole miner emission
        budget — reporting only, and not what gets submitted on chain.
        """
        for account in result.account_results.values():
            for video in account.videos.values():
                if not isinstance(video, dict):
                    continue
                for metrics in video.get("brief_metrics", {}).values():
                    if not isinstance(metrics, dict):
                        continue
                    usd_target = float(metrics.get("usd_target", 0.0) or 0.0)
                    metrics["alpha_target"] = usd_target / alpha_price_usd if alpha_price_usd > 0 else 0.0
                    metrics["weight"] = usd_target / total_daily_usd if total_daily_usd > 0 else 0.0

    async def _publish_safe(self, result: EvaluationResult) -> None:
        if self.publisher is None:
            return
        if result.platform == "youtube":
            try:
                self._add_alpha_targets(
                    result,
                    await self.pricing.get_alpha_price_usd(),
                    await self.pricing.get_total_daily_usd(),
                )
            except Exception as err:
                bt.logging.warning(
                    f"Alpha pricing unavailable for published YouTube metrics ({err!r}); zeroing alpha targets."
                )
                self._add_alpha_targets(result, 0.0)
        try:
            await self.publisher.publish_account_results(result)
        except Exception as err:
            bt.logging.warning(f"Publishing account results failed for uid {result.uid}: {err!r}")

    async def _publish_corrections_safe(
        self,
        results: dict[int, EvaluationResult],
        pre_weights: np.ndarray,
        post_weights: np.ndarray,
        briefs: list[dict],
    ) -> None:
        if self.publisher is None:
            return
        try:
            corrections = weight_corrections(results, pre_weights, post_weights, briefs)
            await self.publisher.publish_weight_corrections(corrections)
        except Exception as err:
            bt.logging.warning(f"Publishing weight corrections failed: {err!r}")

    # --- Fallback -----------------------------------------------------------

    @staticmethod
    def _burn_fallback(uids: list[int]) -> tuple[np.ndarray, list[dict]]:
        rewards = np.array([1.0 if uid == BURN_UID else 0.0 for uid in uids])
        stats_list = [{"uid": uid, "scores": {}} for uid in uids]
        return rewards, stats_list


def weight_corrections(
    results: dict[int, EvaluationResult],
    pre_weights: np.ndarray,
    post_weights: np.ndarray,
    briefs: list[dict],
) -> list[dict]:
    """Per-video scaling factors showing how emission constraints altered raw weights."""
    brief_id_to_idx = {brief["id"]: idx for idx, brief in enumerate(briefs)}
    corrections = []
    for miner_idx, result in enumerate(results.values()):
        for video_id, video_data in (
            (vid, data)
            for account in result.account_results.values()
            for vid, data in account.videos.items()
            if isinstance(data, dict)
        ):
            content_id = video_data.get("details", {}).get("bitcastVideoId", video_id)
            for brief_id in video_data.get("brief_metrics", {}):
                brief_idx = brief_id_to_idx.get(brief_id)
                if brief_idx is None:
                    continue
                factor = _scaling_factor(miner_idx, brief_idx, pre_weights, post_weights)
                corrections.append({"content_id": content_id, "brief_id": brief_id, "scaling_factor": factor})
    return corrections


def _scaling_factor(miner_idx: int, brief_idx: int, pre: np.ndarray, post: np.ndarray) -> float:
    if miner_idx >= pre.shape[0] or brief_idx >= pre.shape[1]:
        return 0.0
    pre_weight = float(pre[miner_idx, brief_idx])
    if pre_weight == 0.0:
        return 0.0
    return max(0.0, min(float(post[miner_idx, brief_idx]) / pre_weight, 10.0))
