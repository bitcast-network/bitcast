"""Data models for evaluation results."""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import copy


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
    
    def to_posting_payload(
        self, 
        run_id: Optional[str] = None,
        miner_uid: Optional[int] = None,
        platform: str = "youtube"
    ) -> Dict[str, Any]:
        """
        Create posting payload for per-account data publishing.
        
        Args:
            run_id: Validation run identifier
            miner_uid: Miner UID for this account
            platform: Platform name (default: "youtube")
            
        Returns:
            Dict containing formatted payload for per-account posting
        """
        # Deep copy videos and clean descriptions
        cleaned_videos = copy.deepcopy(self.videos)
        for video_id, video_data in cleaned_videos.items():
            if isinstance(video_data, dict) and "details" in video_data:
                if isinstance(video_data["details"], dict):
                    # Remove description and transcript fields to reduce payload size
                    video_data["details"].pop("description", None)
                    video_data["details"].pop("transcript", None)
        
        return {
            "account_data": {
                "yt_account": copy.deepcopy(self.platform_data),
                "videos": cleaned_videos,
                "scores": copy.deepcopy(self.scores),
                "performance_stats": copy.deepcopy(self.performance_stats),
                "success": self.success,
                "error_message": self.error_message
            }
        }
    
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