"""Safe structured telemetry for auditable validator score cycles.

This module deliberately emits only numeric scoring state.  It never accepts
creator, account, token, video, transcript, brief, or LLM data.  Loki labels
are validator-scoped and allowlisted so a per-miner event does not create a
high-cardinality label set.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from typing import Any

import numpy as np

_ALLOWED_LABELS = {
    "uid",
    "hotkey",
    "validator_uid",
    "validator_hotkey",
    "netuid",
    # SN93 carries two mechanisms on one metagraph: YouTube on 0, X on 1. Both
    # run on the same hotkey and the same UID, so without this label the two
    # validators' logs share an identical label-set and merge into one stream.
    "mechid",
    "neuron",
    "version",
}
_LABEL_VALUE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def sanitize_loki_labels(labels: dict[str, str] | None) -> dict[str, str]:
    """Return only bounded, validator-level Loki labels.

    This keeps label cardinality independent of the miner and ensures callers
    cannot accidentally put private/free-form content into Loki labels.
    """
    if not labels:
        return {}
    sanitized: dict[str, str] = {}
    for key, value in labels.items():
        text = str(value)
        if key in _ALLOWED_LABELS and _LABEL_VALUE.fullmatch(text):
            sanitized[key] = text
    return sanitized


class MinerScoreTelemetry:
    """Accumulates a bounded cycle snapshot and emits safe JSON lines on flush.

    A score update records raw rewards and EMA transitions.  If this validator
    submits weights in the following sync, the actual processed float weight
    and uint16 chain weight are joined by miner UID before the same cycle is
    emitted.  A telemetry exception is always isolated from validation.
    """

    def __init__(self, emit: Callable[[str], Any]) -> None:
        self._emit = emit
        self._samples: dict[int, dict[str, int | float | str]] = {}

    def record_scores(
        self,
        *,
        validator_uid: int,
        step: int,
        uids: list[int],
        rewards: np.ndarray,
        ema_before: np.ndarray,
        ema_after: np.ndarray,
    ) -> None:
        """Replace the pending snapshot with one safe entry per scored miner."""
        try:
            if not (len(uids) == len(rewards) == len(ema_before) == len(ema_after)):
                return
            cycle_id = f"{int(validator_uid)}:{int(step)}"
            samples: dict[int, dict[str, int | float | str]] = {}
            for uid, raw_reward, before, after in zip(uids, rewards, ema_before, ema_after, strict=True):
                miner_uid = int(uid)
                samples[miner_uid] = {
                    "event": "miner_score",
                    "schema_version": 1,
                    "validator_uid": int(validator_uid),
                    "cycle_id": cycle_id,
                    "cycle_step": int(step),
                    "miner_uid": miner_uid,
                    "raw_reward": _safe_float(raw_reward),
                    "ema_before": _safe_float(before),
                    "ema_after": _safe_float(after),
                }
            self._samples = samples
        except Exception:
            self._samples = {}

    def record_submitted_weights(
        self,
        *,
        processed_uids: np.ndarray,
        processed_weights: np.ndarray,
        uint_uids: np.ndarray,
        uint_weights: np.ndarray,
    ) -> None:
        """Join only successfully submitted chain weights to pending samples."""
        try:
            processed = {
                int(uid): _safe_float(weight) for uid, weight in zip(processed_uids, processed_weights, strict=True)
            }
            emitted = {int(uid): int(weight) for uid, weight in zip(uint_uids, uint_weights, strict=True)}
            for miner_uid, sample in self._samples.items():
                if miner_uid in processed and miner_uid in emitted:
                    sample["submitted_weight"] = processed[miner_uid]
                    sample["onchain_weight_uint16"] = emitted[miner_uid]
        except Exception:
            return

    def flush(self) -> None:
        """Emit and discard the current cycle; a logger failure is non-fatal."""
        samples, self._samples = self._samples, {}
        for sample in samples.values():
            try:
                self._emit(json.dumps(sample, separators=(",", ":"), allow_nan=False))
            except Exception:
                continue


def _safe_float(value: float | int | np.floating[Any]) -> float:
    """Convert metric values to finite JSON numbers without leaking input text."""
    converted = float(value)
    return round(converted, 12) if math.isfinite(converted) else 0.0
