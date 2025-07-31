"""YouTube-specific platform evaluator - wraps existing YouTube logic."""

from typing import Any, Dict, List

import bittensor as bt
from google.oauth2.credentials import Credentials

from bitcast.validator.reward_engine.interfaces.platform_evaluator import (
    PlatformEvaluator,
)
from bitcast.validator.reward_engine.models.evaluation_result import (
    AccountResult,
    EvaluationResult,
)
from bitcast.validator.reward_engine.models.miner_response import MinerResponse
from bitcast.validator.utils.config import (
    MAX_ACCOUNTS_PER_SYNAPSE,
    YT_MIN_ALPHA_STAKE_THRESHOLD,
)

from .main import eval_youtube  # Existing function


class YouTubeEvaluator(PlatformEvaluator):
    """Evaluates YouTube accounts using existing YouTube evaluation logic."""
    
    def platform_name(self) -> str:
        return "youtube"
    
    def can_evaluate(self, miner_response: MinerResponse) -> bool:
        """Check if response contains YouTube access tokens."""
        return (
            miner_response is not None and 
            miner_response.is_valid and
            miner_response.has_yt_tokens
        )
    
    def get_supported_token_types(self) -> List[str]:
        return ["YT_access_tokens"]
    
    async def evaluate_accounts(
        self, 
        miner_response: MinerResponse, 
        briefs: List[Dict[str, Any]],
        metagraph_info: Dict[str, Any]
    ) -> EvaluationResult:
        """
        Evaluate YouTube accounts - replaces logic from reward() function.
        """
        result = EvaluationResult(
            uid=miner_response.uid,
            platform=self.platform_name(),
            metagraph_info=metagraph_info,
            aggregated_scores={brief["id"]: 0.0 for brief in briefs}
        )
        
        # Process YouTube access tokens (existing logic)
        yt_tokens = miner_response.YT_access_tokens[:MAX_ACCOUNTS_PER_SYNAPSE]
        
        if len(miner_response.YT_access_tokens) > MAX_ACCOUNTS_PER_SYNAPSE:
            bt.logging.info(f"Limiting to {MAX_ACCOUNTS_PER_SYNAPSE} accounts per synapse (received {len(miner_response.YT_access_tokens)})")
        
        for i, yt_access_token in enumerate(yt_tokens):
            account_id = f"account_{i+1}"
            
            if yt_access_token:
                bt.logging.info(f"Processing {account_id} for UID {miner_response.uid}")
                account_result = await self._process_youtube_account(
                    yt_access_token, briefs, metagraph_info, account_id
                )
                result.add_account_result(account_id, account_result)
                
                # Aggregate scores
                for brief_id, score in account_result.scores.items():
                    result.aggregated_scores[brief_id] += score
            else:
                bt.logging.warning(f"Empty token found at index {i} for UID {miner_response.uid}")
                # Add empty account result for failed tokens
                empty_result = AccountResult.create_error_result(
                    account_id, "Empty access token", briefs
                )
                result.add_account_result(account_id, empty_result)
        
        return result
    
    async def _process_youtube_account(
        self, 
        access_token: str, 
        briefs: List[Dict[str, Any]],
        metagraph_info: Dict[str, Any],
        account_id: str
    ) -> AccountResult:
        """Process a single YouTube account."""
        try:
            creds = Credentials(token=access_token)
            
            # Check minimum stake threshold
            min_stake = self._check_min_stake(metagraph_info)
            
            # Use existing eval_youtube function
            account_stats = eval_youtube(creds, briefs, min_stake)
            
            return AccountResult(
                account_id=account_id,
                platform_data=account_stats.get("yt_account", {}),
                videos=account_stats.get("videos", {}),
                scores=account_stats.get("scores", {brief["id"]: 0.0 for brief in briefs}),
                performance_stats=account_stats.get("performance_stats", {}),
                success=True
            )
            
        except Exception as e:
            bt.logging.error(f"Error processing YouTube account {account_id}: {e}")
            return AccountResult.create_error_result(account_id, str(e), briefs)
    
    def _check_min_stake(self, metagraph_info: Dict[str, Any]) -> bool:
        """Check if miner meets minimum alpha stake threshold."""
        alpha_stake = metagraph_info.get("alpha_stake", 0.0)
        return float(alpha_stake) >= YT_MIN_ALPHA_STAKE_THRESHOLD 