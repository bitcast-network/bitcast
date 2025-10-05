"""
Streaming Per-Account Publisher - Publishes account data immediately after miner evaluation.

This module implements streaming per-account publishing that runs completely independently
from the monolithic publishing system. Account data is published immediately after each
miner evaluation, distributing server load throughout the 4-hour cycle.
"""

import bittensor as bt
import asyncio

from .config import ENABLE_DATA_PUBLISH, YOUTUBE_SUBMIT_ENDPOINT
from .data_publisher import publish_unified_data, publish_single_account
from ..reward_engine.models.evaluation_result import EvaluationResult


async def publish_miner_accounts(
    evaluation_result: EvaluationResult,
    run_id: str,
    wallet: bt.wallet
) -> None:
    """
    Publish all accounts for a single miner immediately after evaluation (fire and forget).
    
    Args:
        evaluation_result: Complete evaluation result for a single miner
        run_id: Unique run identifier for this validation cycle
        wallet: Bittensor wallet for message signing
    """
    # Early return if per-account publishing is disabled
    if not ENABLE_DATA_PUBLISH:
        return
    
    # Early return if no account results to publish
    if not evaluation_result.account_results:
        return
    
    account_count = len(evaluation_result.account_results)
    bt.logging.info(f"🌊 Streaming {account_count} accounts for UID {evaluation_result.uid} (fire and forget)")
    
    # Create tasks for all account postings for this miner
    tasks = []
    
    for account_id, account_result in evaluation_result.account_results.items():
        # Generate posting payload
        payload = account_result.to_posting_payload(
            run_id=run_id,
            miner_uid=evaluation_result.uid,
            platform=evaluation_result.platform
        )
        
        # Create publishing task
        task = publish_single_account(
            run_id=run_id,
            wallet=wallet,
            account_data=payload["account_data"],
            endpoint=YOUTUBE_SUBMIT_ENDPOINT,
            miner_uid=evaluation_result.uid,
            account_id=account_id,
            platform=evaluation_result.platform
        )
        
        tasks.append(task)
    
    # Fire and forget: Launch all account publishing tasks without waiting for results
    try:
        for task in tasks:
            asyncio.create_task(task)
        
        bt.logging.info(f"🚀 UID {evaluation_result.uid}: Launched {len(tasks)} publishing tasks")
        
    except Exception as e:
        bt.logging.error(f"Error launching publishing tasks for UID {evaluation_result.uid}: {e}")


def publish_miner_accounts_safe(
    evaluation_result: EvaluationResult,
    run_id: str,
    wallet: bt.wallet
) -> None:
    """
    Safe wrapper for publish_miner_accounts that never raises exceptions (fire and forget).
    
    Args:
        evaluation_result: Complete evaluation result for a single miner
        run_id: Unique run identifier for this validation cycle
        wallet: Bittensor wallet for message signing
    """
    try:
        # Fire and forget: Launch the publishing without waiting
        asyncio.create_task(publish_miner_accounts(evaluation_result, run_id, wallet))
    except Exception as e:
        bt.logging.error(f"Streaming publisher error for UID {evaluation_result.uid}: {e}")


def log_streaming_status(total_miners: int) -> None:
    """Log the streaming publishing status at the start of orchestrator cycle."""
    if ENABLE_DATA_PUBLISH:
        bt.logging.info(f"🌊 Streaming per-account publishing ENABLED for {total_miners} miners")
    else:
        bt.logging.info("📴 Streaming per-account publishing DISABLED")