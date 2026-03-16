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

# Limit concurrent publishing tasks to bound memory usage
_publish_semaphore = asyncio.Semaphore(10)


async def _publish_with_semaphore(coro, uid: int, account_id: str) -> bool:
    """Run a publishing coroutine under the semaphore, logging failures."""
    async with _publish_semaphore:
        try:
            return await coro
        except Exception as e:
            bt.logging.error(f"Publishing failed for UID {uid} account {account_id}: {e}")
            return False


async def publish_miner_accounts(
    evaluation_result: EvaluationResult,
    run_id: str,
    wallet: bt.wallet
) -> None:
    """
    Publish all accounts for a single miner immediately after evaluation.

    Uses a bounded semaphore to limit concurrent publishing tasks and awaits
    all tasks so data references are released promptly.

    Args:
        evaluation_result: Complete evaluation result for a single miner
        run_id: Unique run identifier for this validation cycle
        wallet: Bittensor wallet for message signing
    """
    if not ENABLE_DATA_PUBLISH:
        return

    if not evaluation_result.account_results:
        return

    account_count = len(evaluation_result.account_results)
    bt.logging.info(f"🌊 Streaming {account_count} accounts for UID {evaluation_result.uid}")

    tasks = []

    for account_id, account_result in evaluation_result.account_results.items():
        payload = account_result.to_posting_payload(
            run_id=run_id,
            miner_uid=evaluation_result.uid,
            platform=evaluation_result.platform
        )

        coro = publish_single_account(
            run_id=run_id,
            wallet=wallet,
            account_data=payload["account_data"],
            endpoint=YOUTUBE_SUBMIT_ENDPOINT,
            miner_uid=evaluation_result.uid,
            account_id=account_id,
            platform=evaluation_result.platform
        )

        tasks.append(_publish_with_semaphore(coro, evaluation_result.uid, account_id))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = sum(1 for r in results if r is True)
    failures = len(results) - successes
    if failures:
        bt.logging.warning(f"UID {evaluation_result.uid}: {successes}/{len(results)} accounts published, {failures} failed")
    else:
        bt.logging.info(f"🚀 UID {evaluation_result.uid}: Published {successes} accounts")


async def publish_miner_accounts_safe(
    evaluation_result: EvaluationResult,
    run_id: str,
    wallet: bt.wallet
) -> None:
    """
    Safe wrapper for publish_miner_accounts that never raises exceptions.

    Args:
        evaluation_result: Complete evaluation result for a single miner
        run_id: Unique run identifier for this validation cycle
        wallet: Bittensor wallet for message signing
    """
    try:
        await publish_miner_accounts(evaluation_result, run_id, wallet)
    except Exception as e:
        bt.logging.error(f"Streaming publisher error for UID {evaluation_result.uid}: {e}")


def log_streaming_status(total_miners: int) -> None:
    """Log the streaming publishing status at the start of orchestrator cycle."""
    if ENABLE_DATA_PUBLISH:
        bt.logging.info(f"🌊 Streaming per-account publishing ENABLED for {total_miners} miners")
    else:
        bt.logging.info("📴 Streaming per-account publishing DISABLED")