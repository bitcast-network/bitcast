"""Data models for evaluation results."""

from typing import Dict, Any, List
from dataclasses import dataclass, field


@dataclass
class AccountResult:
    """Result from evaluating a single account."""
    account_id: str
    platform_data: Dict[str, Any]
    videos: Dict[str, Any]
    scores: Dict[str, float]  # brief_id -> score
    performance_stats: Dict[str, Any]
    success: bool
    error_message: str = ""
    
    @classmethod
    def create_error_result(
        cls, 
        account_id: str, 
        error_message: str, 
        briefs: List[Dict[str, Any]]
    ) -> 'AccountResult':
        """Create an error result with zero scores."""
        return cls(
            account_id=account_id,
            platform_data={},
            videos={},
            scores={brief["id"]: 0.0 for brief in briefs},
            performance_stats={},
            success=False,
            error_message=error_message
        )


@dataclass
class EvaluationResult:
    """Complete evaluation result for a miner."""
    uid: int
    platform: str
    account_results: Dict[str, AccountResult] = field(default_factory=dict)
    aggregated_scores: Dict[str, float] = field(default_factory=dict)
    metagraph_info: Dict[str, Any] = field(default_factory=dict)
    
    def add_account_result(self, account_id: str, result: AccountResult):
        """Add an account result to this evaluation."""
        self.account_results[account_id] = result
    
    def get_total_score_for_brief(self, brief_id: str) -> float:
        """Get aggregated score for a specific brief."""
        return self.aggregated_scores.get(brief_id, 0.0)


class EvaluationResultCollection:
    """Collection of evaluation results for all miners."""
    
    def __init__(self):
        self.results: Dict[int, EvaluationResult] = {}
    
    def add_result(self, uid: int, result: EvaluationResult):
        """Add an evaluation result for a UID."""
        self.results[uid] = result
    
    def add_empty_result(self, uid: int, reason: str):
        """Add an empty result for a failed evaluation."""
        self.results[uid] = EvaluationResult(
            uid=uid, 
            platform="unknown",
            aggregated_scores={},
        )
    
    def get_result(self, uid: int) -> EvaluationResult:
        """Get result for a specific UID."""
        return self.results.get(uid) 