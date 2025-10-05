"""
Generic data publishing utilities for platform-agnostic account data posting.

This module provides abstract base classes and implementations for publishing
account data to external endpoints with message signing and error handling.
"""

import asyncio
import json
import aiohttp
import bittensor as bt
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional, Union, List
import time

from bitcast.validator.utils.publish_stats import convert_numpy_types


class DataPublisher(ABC):
    """Abstract base class for data publishing with message signing."""
    
    def __init__(self, wallet: bt.wallet, timeout_seconds: int = 10):
        """
        Initialize DataPublisher with validator wallet.
        
        Args:
            wallet: Bittensor wallet for message signing
            timeout_seconds: HTTP request timeout
        """
        self.wallet = wallet
        self.timeout_seconds = timeout_seconds
    
    @abstractmethod
    async def publish_data(self, data: Dict[str, Any], endpoint: str) -> bool:
        """
        Publish data to specified endpoint.
        
        Args:
            data: Data payload to publish
            endpoint: Target endpoint URL
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    def _get_expected_status_code(self) -> int:
        """
        Get the expected HTTP status code for successful requests.
        Override in subclasses for different endpoint behaviors.
        
        Returns:
            Expected HTTP status code (default: 200)
        """
        return 200
    
    def _sign_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sign message data using unified format that supports both legacy and new payload structures.
        
        Args:
            data: Full payload including metadata and core data
            
        Returns:
            Dict containing signed payload with signature and signer
        """
        # Get hotkey for signing
        keypair = self.wallet.hotkey
        signer = keypair.ss58_address
        
        # Extract core data to sign - supports both payload formats
        core_data_to_sign = self._extract_signable_data(data)
        
        # Generate timestamp for BOTH signing and payload (must be identical!)
        timestamp = datetime.utcnow().isoformat()
        
        # Create message to sign (format: signer:timestamp:core_data)
        message = f"{signer}:{timestamp}:{json.dumps(core_data_to_sign, sort_keys=True)}"
        
        # Sign the message
        signature = keypair.sign(data=message)
        
        # Create final payload with SAME timestamp used for signing
        converted_payload = convert_numpy_types(data)
        signed_payload = {
            **converted_payload,  # Include all metadata
            "time": timestamp,  # Use same timestamp as signature
            "signature": signature.hex(),
            "signer": signer,
            "vali_hotkey": signer  # Required for unified API format
        }
        
        return signed_payload
    
    def _extract_signable_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract the core data that should be signed from the payload.
        Supports both unified format ('payload' field) and legacy format ('account_data' field).
        
        Args:
            data: Full payload data
            
        Returns:
            Core data to include in signature
        """
        # Unified API format uses 'payload' field
        if 'payload' in data:
            return convert_numpy_types(data.get('payload', {}))
        
        # Legacy format uses 'account_data' field
        account_data = data.get('account_data', {})
        return convert_numpy_types(account_data)
    
    def _log_success(self, endpoint: str, data_type: str = "data") -> None:
        """Log successful publication."""
        bt.logging.info(f"Successfully published {data_type}")
    
    def _log_error(self, endpoint: str, error: Exception, data_type: str = "data") -> None:
        """Log publication error."""
        bt.logging.error(f"Failed to publish {data_type} to {endpoint}: {error}")


class UnifiedDataPublisher(DataPublisher):
    """Unified publisher for both YouTube and Weight Corrections using new API format."""
    
    def __init__(self, wallet: bt.wallet, timeout_seconds: int = 60):
        """
        Initialize UnifiedDataPublisher with timeout for async processing.
        
        Args:
            wallet: Bittensor wallet for message signing
            timeout_seconds: HTTP request timeout for async processing (default: 60s)
        """
        super().__init__(wallet, timeout_seconds)
    
    def _get_expected_status_code(self) -> int:
        """Return 202 Accepted for async processing."""
        return 202
    

    
    async def publish_unified_payload(
        self,
        payload_type: str,
        run_id: str,
        payload_data: Any,
        endpoint: str,
        miner_uid: Optional[int] = None
    ) -> bool:
        """
        Publish data using unified API format.
        
        Args:
            payload_type: "youtube" or "weight_corrections"
            run_id: Validation cycle identifier
            payload_data: The actual data (format depends on payload_type)
            endpoint: Target endpoint URL
            miner_uid: Optional miner UID
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create unified payload structure
            payload = {
                "payload_type": payload_type,
                "run_id": run_id,
                "payload": payload_data
            }
            
            # Add optional miner_uid if provided
            if miner_uid is not None:
                payload["miner_uid"] = miner_uid
            
            # Publish using unified format
            return await self.publish_data(payload, endpoint)
            
        except Exception as e:
            self._log_error(endpoint, e, f"{payload_type} data")
            return False
    
    async def publish_data(self, data: Dict[str, Any], endpoint: str) -> bool:
        """
        Publish data to specified endpoint with unified API format handling.
        
        Args:
            data: Data payload to publish
            endpoint: Target endpoint URL
            
        Returns:
            bool: True if successful, False otherwise
        """
        start_time = time.time()
        try:
            # Sign the message using corrected format
            signed_payload = self._sign_message(data)
            
            # Make async HTTP request with longer timeout
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    endpoint, 
                    json=signed_payload,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    }
                ) as response:
                    response_time = time.time() - start_time
                    if response.status == 202:  # Expect 202 Accepted for async processing
                        try:
                            response_data = await response.json()
                            # Check for success status in response
                            if response_data.get("status") == "success":
                                payload_type = signed_payload.get("payload_type", "unknown")
                                bt.logging.info(f"✅ Successfully published {payload_type} data (%.2fs)", response_time)
                                return True
                            else:
                                bt.logging.error(f"Server returned error: {response_data} (%.2fs)", response_time)
                                return False
                        except Exception as json_error:
                            bt.logging.error(f"Failed to parse response JSON: {json_error} (%.2fs)", response_time)
                            return False
                    elif response.status == 400:
                        error_text = await response.text()
                        bt.logging.error(f"400 Bad Request - Payload validation failed: {error_text} (%.2fs)", response_time)
                        return False
                    elif response.status == 401:
                        bt.logging.error(f"401 Unauthorized - Invalid signature/authentication (%.2fs)", response_time)
                        return False
                    elif response.status == 403:
                        bt.logging.error(f"403 Forbidden - Validator not authorized (%.2fs)", response_time)
                        return False
                    else:
                        error_text = await response.text()
                        bt.logging.error(f"HTTP {response.status} error from {endpoint}: {error_text} (%.2fs)", response_time)
                        return False
                        
        except asyncio.TimeoutError:
            response_time = time.time() - start_time
            bt.logging.warning(f"Request timed out after %.2fs - server queue may be processing", response_time)
            return False
        except Exception as e:
            response_time = time.time() - start_time
            bt.logging.error(f"Failed to publish unified data to {endpoint}: {e} (%.2fs)", response_time)
            return False





# Convenience functions for easy usage


async def publish_unified_data(
    payload_type: str,
    run_id: str, 
    wallet: bt.wallet,
    payload_data: Union[Dict[str, Any], List[Dict[str, Any]]],
    endpoint: str,
    miner_uid: Optional[int] = None
) -> bool:
    """
    Convenience function to publish data using unified API format.
    
    Args:
        payload_type: "youtube" or "weight_corrections"
        run_id: Validation cycle identifier
        wallet: Bittensor wallet
        payload_data: The actual data payload
        endpoint: Target endpoint URL
        miner_uid: Optional miner UID
        
    Returns:
        bool: True if successful, False otherwise
    """
    publisher = UnifiedDataPublisher(wallet)
    return await publisher.publish_unified_payload(
        payload_type, run_id, payload_data, endpoint, miner_uid
    )


async def publish_single_account(
    run_id: str, 
    wallet: bt.wallet,
    account_data: Dict[str, Any],
    endpoint: str,
    miner_uid: int,
    account_id: str,
    platform: str = "youtube"
) -> bool:
    """
    Convenience function to publish single account data using unified API format.
    
    Args:
        run_id: Validation cycle identifier
        wallet: Bittensor wallet
        account_data: Account data to publish
        endpoint: Target endpoint URL
        miner_uid: Miner UID
        account_id: Account identifier
        platform: Platform name (should be "youtube" for unified format)
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Use unified format directly
    unified_payload_data = {
        "account_data": account_data,
        "account_id": account_id
    }
    
    publisher = UnifiedDataPublisher(wallet)
    return await publisher.publish_unified_payload(
        payload_type="youtube",
        run_id=run_id,
        payload_data=unified_payload_data,
        endpoint=endpoint,
        miner_uid=miner_uid
    )