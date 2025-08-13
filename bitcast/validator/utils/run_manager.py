"""
Run ID generation and management for validation cycles.

This module provides functionality to generate unique run IDs based on validator hotkey
and timestamp, ensuring each 4-hour validation cycle has a unique identifier.
"""

import bittensor as bt
from datetime import datetime
from typing import Optional
import threading


class RunManager:
    """Manages run ID generation and persistence for validation cycles."""
    
    def __init__(self, wallet: bt.wallet):
        """
        Initialize RunManager with validator wallet.
        
        Args:
            wallet: Bittensor wallet containing validator hotkey
        """
        self.wallet = wallet
        self.current_run_id: Optional[str] = None
        self._lock = threading.Lock()
    
    def generate_run_id(self) -> str:
        """
        Generate a new run ID based on validator hotkey and current timestamp.
        
        Format: "vali_{validator_hotkey}_{timestamp}"
        Example: "vali_5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY_20250106_120000"
        
        Returns:
            str: Unique run ID for this validation cycle
        """
        with self._lock:
            vali_hotkey = self.wallet.hotkey.ss58_address
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            run_id = f"vali_{vali_hotkey}_{timestamp}"
            
            # Store as current run ID
            self.current_run_id = run_id
            
            bt.logging.info(f"Generated new run ID: {run_id}")
            return run_id
    
    def get_current_run_id(self) -> Optional[str]:
        """
        Get the current run ID for this validation cycle.
        
        Returns:
            str: Current run ID, or None if no run ID has been generated
        """
        with self._lock:
            return self.current_run_id
    
    def reset_run_id(self) -> None:
        """Reset the current run ID (for testing purposes)."""
        with self._lock:
            self.current_run_id = None
            bt.logging.debug("Run ID reset")


# Global instance for easy access across the validator
_run_manager: Optional[RunManager] = None
_manager_lock = threading.Lock()


def get_run_manager(wallet: bt.wallet = None) -> RunManager:
    """
    Get or create the global RunManager instance.
    
    Args:
        wallet: Bittensor wallet (required for first initialization)
        
    Returns:
        RunManager: Global RunManager instance
        
    Raises:
        ValueError: If wallet is None and no manager exists
    """
    global _run_manager
    
    with _manager_lock:
        if _run_manager is None:
            if wallet is None:
                raise ValueError("Wallet required for RunManager initialization")
            _run_manager = RunManager(wallet)
        
        return _run_manager


def generate_current_run_id(wallet: bt.wallet) -> str:
    """
    Convenience function to generate a run ID using the global manager.
    
    Args:
        wallet: Bittensor wallet
        
    Returns:
        str: Generated run ID
    """
    manager = get_run_manager(wallet)
    return manager.generate_run_id()


def get_current_run_id() -> Optional[str]:
    """
    Convenience function to get current run ID from global manager.
    
    Returns:
        str: Current run ID, or None if no manager exists or no run ID generated
    """
    global _run_manager
    
    if _run_manager is None:
        return None
    
    return _run_manager.get_current_run_id()