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
        # Strip brief_reasonings from decision_details before deep copy
        # to avoid copying paragraphs of LLM text per brief per video.
        stripped = []
        for video_data in self.videos.values():
            if isinstance(video_data, dict):
                dd = video_data.get("decision_details")
                if isinstance(dd, dict) and "brief_reasonings" in dd:
                    stripped.append((dd, dd.pop("brief_reasonings")))

        # Deep copy videos (nested structure requires deepcopy) and clean
        cleaned_videos = copy.deepcopy(self.videos)

        # Restore brief_reasonings on originals AND inject into cleaned copy
        for dd, reasonings in stripped:
            dd["brief_reasonings"] = reasonings
        for video_id in cleaned_videos:
            orig = self.videos.get(video_id)
            if isinstance(orig, dict):
                orig_dd = orig.get("decision_details")
                if isinstance(orig_dd, dict) and "brief_reasonings" in orig_dd:
                    cleaned_dd = cleaned_videos[video_id].get("decision_details")
                    if isinstance(cleaned_dd, dict):
                        cleaned_dd["brief_reasonings"] = orig_dd["brief_reasonings"]

        for video_id, video_data in cleaned_videos.items():
            if isinstance(video_data, dict) and "details" in video_data:
                if isinstance(video_data["details"], dict):
                    video_data["details"].pop("description", None)
                    video_data["details"].pop("transcript", None)

            if isinstance(video_data, dict) and "brief_metrics" in video_data:
                video_data["per_video_metrics"] = video_data["brief_metrics"]

        return {
            "account_data": {
                "yt_account": self.platform_data.copy(),
                "videos": cleaned_videos,
                "scores": self.scores.copy(),
                "performance_stats": self.performance_stats.copy(),
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
    
    def merge(self, other: 'EvaluationResult'):
        """Merge another EvaluationResult's accounts and scores into this one."""
        for account_id, account_result in other.account_results.items():
            self.add_account_result(account_id, account_result)
        for brief_id, score in other.aggregated_scores.items():
            self.aggregated_scores[brief_id] = self.aggregated_scores.get(brief_id, 0.0) + score
    
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