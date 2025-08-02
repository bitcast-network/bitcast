"""Data model for miner response handling."""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class MinerResponse:
    """Wrapper for miner response data."""
    uid: int
    response_data: Any
    is_valid: bool = True
    error_message: str = ""
    
    @property
    def YT_access_tokens(self) -> List[str]:
        """Get YouTube access tokens from response."""
        if hasattr(self.response_data, 'YT_access_tokens'):
            return self.response_data.YT_access_tokens or []
        return []
    
    @property
    def has_yt_tokens(self) -> bool:
        """Check if response has YouTube tokens."""
        return len(self.YT_access_tokens) > 0
    
    @classmethod
    def from_response(cls, uid: int, response: Any) -> 'MinerResponse':
        """Create from raw miner response."""
        if response is None:
            return cls(
                uid=uid,
                response_data=None,
                is_valid=False,
                error_message="No response received"
            )
        
        return cls(
            uid=uid,
            response_data=response,
            is_valid=True
        )
    
    @classmethod
    def create_error(cls, uid: int, error_message: str) -> 'MinerResponse':
        """Create an error response."""
        return cls(
            uid=uid,
            response_data=None,
            is_valid=False,
            error_message=error_message
        ) 