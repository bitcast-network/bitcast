"""Data model for emission calculation results."""

from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class EmissionTarget:
    """Represents an emission target for a brief."""
    brief_id: str
    usd_target: float
    allocation_details: Dict[str, Any]
    scaling_factors: Dict[str, float]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "brief_id": self.brief_id,
            "usd_target": self.usd_target,
            "allocation_details": self.allocation_details,
            "scaling_factors": self.scaling_factors
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EmissionTarget':
        """Create from dictionary."""
        return cls(
            brief_id=data["brief_id"],
            usd_target=data["usd_target"],
            allocation_details=data["allocation_details"],
            scaling_factors=data["scaling_factors"]
        ) 