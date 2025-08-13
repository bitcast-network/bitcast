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
from typing import Dict, Any, Optional

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
    
    def _sign_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sign message data following publish_stats.py pattern exactly.
        Signs only the core account_data, not the metadata wrapper.
        
        Args:
            data: Full payload including metadata and account_data
            
        Returns:
            Dict containing signed payload with signature and signer
        """
        # Get hotkey for signing
        keypair = self.wallet.hotkey
        vali_hotkey = keypair.ss58_address
        
        # Extract core data to sign (equivalent to combined_payload in publish_stats.py)
        # Only sign the account_data portion, not the metadata
        account_data = data.get('account_data', {})
        core_data_to_sign = convert_numpy_types(account_data)
        
        # Extract timestamp from payload and strip 'Z' for signing
        # If no timestamp provided, generate one (similar to publish_stats.py pattern)
        payload_timestamp = data.get('time', '')
        if payload_timestamp:
            if payload_timestamp.endswith('Z'):
                timestamp = payload_timestamp[:-1]  # Remove 'Z' for signing
            else:
                timestamp = payload_timestamp
        else:
            # Generate timestamp when not provided in payload
            timestamp = datetime.utcnow().isoformat()
        
        # Create message to sign (format: hotkey:timestamp:core_data) - same as publish_stats.py
        message = f"{vali_hotkey}:{timestamp}:{json.dumps(core_data_to_sign, sort_keys=True)}"
        
        # Sign the message
        signature = keypair.sign(data=message)
        
        # Create final payload with same structure as publish_stats.py
        # Convert entire payload to handle NumPy types in metadata fields (like miner_uid)
        converted_payload = convert_numpy_types(data)
        signed_payload = {
            **converted_payload,  # Include all converted metadata (run_id, platform, etc.)
            "signature": signature.hex(),
            "signer": keypair.ss58_address
        }
        
        return signed_payload
    
    def _log_success(self, endpoint: str, data_type: str = "data") -> None:
        """Log successful publication."""
        bt.logging.info(f"Successfully published {data_type} to {endpoint}")
    
    def _log_error(self, endpoint: str, error: Exception, data_type: str = "data") -> None:
        """Log publication error."""
        bt.logging.error(f"Failed to publish {data_type} to {endpoint}: {error}")


class AccountDataPublisher(DataPublisher):
    """Implementation for publishing individual account data."""
    
    def __init__(self, wallet: bt.wallet, timeout_seconds: int = 10):
        """
        Initialize AccountDataPublisher.
        
        Args:
            wallet: Bittensor wallet for message signing
            timeout_seconds: HTTP request timeout
        """
        super().__init__(wallet, timeout_seconds)
    
    async def publish_account_data(self, run_id: str, 
        account_data: Dict[str, Any], 
        endpoint: str,
        miner_uid: int,
        account_id: str,
        platform: str = "youtube"
    ) -> bool:
        """
        Publish individual account data to endpoint.
        
        Args:
            account_data: Account-specific data payload
            endpoint: Target endpoint URL
            miner_uid: Miner UID for this account
            account_id: Account identifier (e.g., "account_1")
            platform: Platform name (default: "youtube")
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get current run ID
            
            # Create payload structure
            payload = {
                "run_id": run_id,
                "platform": platform,
                "miner_uid": miner_uid,
                "account_id": account_id,
                "vali_hotkey": self.wallet.hotkey.ss58_address,
                "time": datetime.utcnow().isoformat() + "Z",
                "account_data": account_data
            }
            
            # Publish the data
            return await self.publish_data(payload, endpoint)
            
        except Exception as e:
            self._log_error(endpoint, e, f"account data for {account_id}")
            return False
    
    async def publish_data(self, data: Dict[str, Any], endpoint: str) -> bool:
        """
        Publish data to specified endpoint with async HTTP POST.
        
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
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(endpoint, json=signed_payload) as response:
                    if response.status == 200:
                        try:
                            response_data = await response.json()
                            # Accept both "ok" and "success" as valid status values
                            if response_data.get("status") in ["ok", "success"]:
                                self._log_success(endpoint, "account data")
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
                        
        except asyncio.TimeoutError:
            self._log_error(endpoint, Exception("Request timeout"), "account data")
            return False
        except Exception as e:
            self._log_error(endpoint, e, "account data")
            return False


# Convenience functions for easy usage
_account_publisher: Optional[AccountDataPublisher] = None


def get_account_publisher(wallet: bt.wallet) -> AccountDataPublisher:
    """
    Get or create global AccountDataPublisher instance.
    
    Args:
        wallet: Bittensor wallet
        
    Returns:
        AccountDataPublisher: Global publisher instance
    """
    global _account_publisher
    
    if _account_publisher is None:
        _account_publisher = AccountDataPublisher(wallet)
    
    return _account_publisher


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
    Convenience function to publish single account data.
    
    Args:
        wallet: Bittensor wallet
        account_data: Account data to publish
        endpoint: Target endpoint URL
        miner_uid: Miner UID
        account_id: Account identifier
        platform: Platform name
        
    Returns:
        bool: True if successful, False otherwise
    """
    publisher = get_account_publisher(wallet)
    return await publisher.publish_account_data(run_id, 
        account_data, endpoint, miner_uid, account_id, platform
    )