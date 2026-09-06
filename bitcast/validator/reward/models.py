"""Typed data models flowing through the reward engine."""

from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from bitcast.protocol import AccessTokenSynapse


class MinerResponse(BaseModel):
    """A miner's (possibly failed) answer to an access-token query."""

    uid: int
    tokens: list[str] = []
    is_valid: bool = True
    error_message: str = ""

    @property
    def has_tokens(self) -> bool:
        return len(self.tokens) > 0

    @classmethod
    def from_synapse(cls, uid: int, synapse: AccessTokenSynapse | None) -> "MinerResponse":
        if synapse is None:
            return cls(uid=uid, is_valid=False, error_message="No response received")
        return cls(uid=uid, tokens=synapse.YT_access_tokens or [])

    @classmethod
    def error(cls, uid: int, message: str) -> "MinerResponse":
        return cls(uid=uid, is_valid=False, error_message=message)


class AccountResult(BaseModel):
    """Evaluation outcome for a single platform account (one access token)."""

    account_id: str
    platform_data: dict[str, Any] = {}
    videos: dict[str, Any] = {}
    scores: dict[str, float] = {}  # brief_id -> USD score
    performance_stats: dict[str, Any] = {}
    success: bool = True
    error_message: str = ""

    @classmethod
    def error_result(cls, account_id: str, message: str, briefs: list[dict]) -> "AccountResult":
        return cls(
            account_id=account_id,
            scores={brief["id"]: 0.0 for brief in briefs},
            success=False,
            error_message=message,
        )


class EvaluationResult(BaseModel):
    """All account results for one miner, with per-brief score totals."""

    uid: int
    platform: str
    account_results: dict[str, AccountResult] = {}
    aggregated_scores: dict[str, float] = {}  # brief_id -> summed USD score
    metagraph_info: dict[str, Any] = {}

    def add_account_result(self, result: AccountResult) -> None:
        self.account_results[result.account_id] = result

    def merge(self, other: "EvaluationResult") -> None:
        """Fold another (batch) result into this one, summing brief scores."""
        for account_result in other.account_results.values():
            self.add_account_result(account_result)
        for brief_id, score in other.aggregated_scores.items():
            self.aggregated_scores[brief_id] = self.aggregated_scores.get(brief_id, 0.0) + score


class ScoreMatrix(BaseModel):
    """Thin serializable wrapper over the miners x briefs score matrix."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    matrix: np.ndarray

    @classmethod
    def empty(cls, num_miners: int, num_briefs: int) -> "ScoreMatrix":
        return cls(matrix=np.zeros((num_miners, num_briefs), dtype=np.float64))

    @property
    def num_miners(self) -> int:
        return self.matrix.shape[0]

    @property
    def num_briefs(self) -> int:
        return self.matrix.shape[1]

    def to_dict(self) -> dict[str, Any]:
        return {"matrix": self.matrix.tolist(), "num_miners": self.num_miners, "num_briefs": self.num_briefs}


class EmissionTarget(BaseModel):
    """Per-brief USD target and the weights each miner earned toward it."""

    brief_id: str
    usd_target: float
    per_miner_weights: list[float]
    brief_format: str = "dedicated"
    boost_factor: float = 1.0
