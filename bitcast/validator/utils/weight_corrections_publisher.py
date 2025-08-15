"""Weight corrections publisher for post-constraint scaling factors."""

import asyncio
from typing import Dict, Any, List
import bittensor as bt
from .data_publisher import DataPublisher


class WeightCorrectionsPublisher(DataPublisher):
    """Publishes weight corrections data in fire-and-forget mode."""
    
    def __init__(self, wallet: bt.wallet):
        """Initialize publisher with wallet."""
        super().__init__(wallet)
        
    async def publish_data(self, data: Dict[str, Any], endpoint: str) -> bool:
        """
        Publish data to specified endpoint (required implementation of abstract method).
        
        Args:
            data: Data payload to publish
            endpoint: Target endpoint URL
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Sign the message
            signed_payload = self._sign_message(data)
            
            # Make async HTTP request
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(endpoint, json=signed_payload) as response:
                    if response.status == 200:
                        try:
                            response_data = await response.json()
                            # Accept both "ok" and "success" as valid status values
                            if response_data.get("status") in ["ok", "success"]:
                                return True
                            else:
                                bt.logging.error(f"Server returned error: {response_data}")
                                return False
                        except Exception as json_error:
                            bt.logging.error(f"Failed to parse response JSON: {json_error}")
                            return False
                    else:
                        bt.logging.error(f"HTTP {response.status} error from {endpoint}")
                        return False
                        
        except Exception as e:
            bt.logging.error(f"Publishing failed: {e}")
            return False
        
    async def publish_corrections(
        self,
        corrections: List[Dict[str, Any]],
        run_id: str,
        endpoint: str
    ) -> None:
        """
        Publish weight corrections payload (fire-and-forget).
        
        Args:
            corrections: List of corrections with content_id, brief_id, scaling_factor
            run_id: Validation run identifier  
            endpoint: Corrections endpoint URL
            
        Note:
            This is fire-and-forget - no return value, no error handling.
            Failures are logged but don't propagate.
        """
        try:
            payload = self._build_corrections_payload(corrections, run_id)
            
            bt.logging.info(f"🔄 Publishing {len(corrections)} weight corrections to {endpoint}")
            
            # Fire-and-forget: publish without checking return value
            await self.publish_data(payload, endpoint)
            
            bt.logging.info(f"✅ Weight corrections published for run {run_id}")
            
        except Exception as e:
            # Log but don't propagate errors (fire-and-forget)
            bt.logging.warning(f"⚠️ Weight corrections publishing failed: {e}")
    
    def _build_corrections_payload(
        self, 
        corrections: List[Dict[str, Any]], 
        run_id: str
    ) -> Dict[str, Any]:
        """Build the corrections payload according to spec."""
        from datetime import datetime
        return {
            "payload_type": "weight_corrections",
            "run_id": run_id,
            "vali_hotkey": self.wallet.hotkey.ss58_address,
            "time": datetime.utcnow().isoformat() + "Z",
            "corrections": corrections
        }


async def publish_weight_corrections(
    corrections: List[Dict[str, Any]],
    run_id: str,
    wallet: bt.wallet,
    endpoint: str
) -> None:
    """
    Convenience function to publish weight corrections (fire-and-forget).
    
    Args:
        corrections: List of corrections with content_id, brief_id, scaling_factor
        run_id: Validation run identifier
        wallet: Bittensor wallet for message signing
        endpoint: Corrections endpoint URL
        
    Note:
        This function never raises exceptions - it's truly fire-and-forget.
    """
    try:
        publisher = WeightCorrectionsPublisher(wallet)
        await publisher.publish_corrections(corrections, run_id, endpoint)
    except Exception as e:
        # Ultimate fallback - should never reach here due to publisher error handling
        bt.logging.error(f"💥 Critical weight corrections publishing error: {e}")