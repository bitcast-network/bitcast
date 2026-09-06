"""Weight processing and on-chain submission for the validator."""

import contextlib

import bittensor as bt
import numpy as np

from bitcast.chain.weight_utils import convert_weights_and_uids_for_emit, process_weights_for_netuid
from bitcast.events import log_event


def normalize_scores(scores: np.ndarray) -> np.ndarray:
    """L1-normalize scores into raw weights; zero/NaN norms yield the input unscaled."""
    norm = np.linalg.norm(scores, ord=1)
    if norm == 0 or np.isnan(norm):
        return scores.astype(np.float32)
    return (scores / norm).astype(np.float32)


def set_weights(validator) -> bool:
    """Convert the validator's score vector into chain weights and submit them.

    Uses the bittensor SDK's ``process_weights_for_netuid`` to enforce subnet
    hyperparameters (min allowed weights, max weight limit) before emitting.

    Returns:
        True if the extrinsic was accepted.
    """
    if np.isnan(validator.scores).any():
        bt.logging.warning("Scores contain NaN values; they will be treated as zero.")

    raw_weights = normalize_scores(np.nan_to_num(validator.scores, nan=0.0))
    processed_uids, processed_weights = process_weights_for_netuid(
        uids=validator.metagraph.uids,
        weights=raw_weights,
        netuid=validator.config.netuid,
        subtensor=validator.subtensor,
        metagraph=validator.metagraph,
    )
    uint_uids, uint_weights = convert_weights_and_uids_for_emit(uids=processed_uids, weights=processed_weights)

    response = validator.subtensor.set_weights(
        wallet=validator.wallet,
        netuid=validator.config.netuid,
        uids=uint_uids,
        weights=uint_weights,
        version_key=validator.spec_version,
        wait_for_inclusion=False,
        wait_for_finalization=False,
    )
    if response.success:
        telemetry = getattr(validator, "telemetry", None)
        if telemetry is not None:
            # Telemetry must never interfere with on-chain weight submission.
            with contextlib.suppress(Exception):
                telemetry.record_submitted_weights(
                    processed_uids=processed_uids,
                    processed_weights=processed_weights,
                    uint_uids=uint_uids,
                    uint_weights=uint_weights,
                )

        # Top-5 weights for Grafana dashboard (structured JSON).
        top_n = min(5, len(processed_weights))
        top_idx = np.argsort(processed_weights)[::-1][:top_n]
        top_weights = [
            {"uid": int(processed_uids[i]), "weight": round(float(processed_weights[i]), 6)} for i in top_idx
        ]
        max_weight = float(np.max(processed_weights)) if len(processed_weights) else 0.0
        bt.logging.info("set_weights on chain succeeded")
        log_event(
            {
                "event": "set_weights",
                "success": True,
                "num_weights": len(uint_weights),
                "max_weight": round(max_weight, 6),
                "top_weights": top_weights,
            }
        )
    else:
        bt.logging.error(f"set_weights failed: {response.message}")
        log_event({"event": "set_weights", "success": False, "error": str(response.message)})
    return bool(response.success)
