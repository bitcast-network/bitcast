"""Signed publishing of evaluation data to the Bitcast dashboard API.

Every payload is signed with the validator's hotkey so the dashboard can
verify provenance. Publishing is transparency-only: failures never affect
scoring and are logged, not raised.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import bittensor as bt
import httpx
import numpy as np

from bitcast.config import Settings, get_settings
from bitcast.http import request_with_retry
from bitcast.validator.reward.models import AccountResult, EvaluationResult

_PUBLISH_TIMEOUT = 60.0
_MAX_CONCURRENT_PUBLISHES = 10
_EXPECTED_STATUS = 202


def convert_numpy_types(obj: Any) -> Any:
    """Recursively convert numpy scalars/arrays into JSON-serializable natives."""
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [convert_numpy_types(item) for item in obj]
    return obj


def account_posting_payload(account: AccountResult) -> dict:
    """Dashboard payload for one account, without bulky LLM/transcript text."""
    videos = {}
    for video_id, video in account.videos.items():
        if not isinstance(video, dict):
            continue
        cleaned = {key: value for key, value in video.items() if key != "brief_metrics"}
        details = cleaned.get("details")
        if isinstance(details, dict):
            cleaned["details"] = {k: v for k, v in details.items() if k not in ("description", "transcript")}
        cleaned["per_video_metrics"] = video.get("brief_metrics", {})
        videos[video_id] = cleaned
    return {
        "yt_account": account.platform_data.copy(),
        "videos": videos,
        "scores": account.scores.copy(),
        "performance_stats": account.performance_stats.copy(),
        "success": account.success,
        "error_message": account.error_message,
    }


class Publisher:
    """Publishes per-account results and weight corrections for one validator run."""

    def __init__(self, wallet: Any, settings: Settings | None = None) -> None:
        self.wallet = wallet
        self.settings = settings or get_settings()
        self.run_id = self._generate_run_id()
        self._semaphore = asyncio.Semaphore(_MAX_CONCURRENT_PUBLISHES)

    def _generate_run_id(self) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        return f"vali_{self.wallet.hotkey.ss58_address}_{timestamp}"

    def new_run(self) -> str:
        """Start a new run id; call once per reward cycle."""
        self.run_id = self._generate_run_id()
        return self.run_id

    def _sign(self, payload: dict) -> dict:
        """Attach hotkey signature, signer and timestamp to a payload."""
        signer = self.wallet.hotkey.ss58_address
        timestamp = datetime.now(UTC).replace(tzinfo=None).isoformat()
        core = payload.get("payload", payload)
        message = f"{signer}:{timestamp}:{json.dumps(core, sort_keys=True)}"
        signature = self.wallet.hotkey.sign(data=message)
        return {
            **payload,
            "time": timestamp,
            "signature": signature.hex(),
            "signer": signer,
            "vali_hotkey": signer,
        }

    async def _publish(self, payload_type: str, payload_data: Any, endpoint: str, miner_uid: int | None = None) -> bool:
        payload: dict = {"payload_type": payload_type, "run_id": self.run_id, "payload": payload_data}
        if miner_uid is not None:
            payload["miner_uid"] = miner_uid
        signed = self._sign(convert_numpy_types(payload))

        try:
            async with httpx.AsyncClient() as client:
                response = await request_with_retry(
                    client, "POST", endpoint, json=signed, timeout=_PUBLISH_TIMEOUT, label="publish"
                )
                if response.status_code != _EXPECTED_STATUS:
                    bt.logging.warning(f"Publish to {endpoint} returned {response.status_code}")
                    return False
                body = response.json()
                return body.get("status") == "success"
        except (httpx.HTTPError, TimeoutError, json.JSONDecodeError) as err:
            bt.logging.warning(f"Publish to {endpoint} failed: {err}")
            return False

    async def publish_account_results(self, result: EvaluationResult) -> None:
        """Publish every account of a miner's evaluation result concurrently."""

        async def publish_one(account_id: str, account: AccountResult) -> None:
            async with self._semaphore:
                await self._publish(
                    payload_type="youtube",
                    payload_data={"account_data": account_posting_payload(account), "account_id": account_id},
                    endpoint=self.settings.youtube_submit_endpoint,
                    miner_uid=result.uid,
                )

        await asyncio.gather(
            *(publish_one(account_id, account) for account_id, account in result.account_results.items())
        )

    async def publish_weight_corrections(self, corrections: list[dict]) -> None:
        """Publish post-constraint scaling factors for transparency."""
        await self._publish(
            payload_type="weight_corrections",
            payload_data=corrections,
            endpoint=self.settings.weight_corrections_endpoint,
        )
