"""Data model for emission calculation results."""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class EmissionTarget:
    """
    Represents an emission target for a brief.
    
    Note: scaling_factors is now optional since platform-specific transformations
    (scaling factors, boost multipliers) are applied at the platform level before
    reaching emission calculation.
    """
    brief_id: str
    usd_target: float
    allocation_details: Dict[str, Any]
    scaling_factors: Optional[Dict[str, float]] = field(default_factory=dict)
    
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
            scaling_factors=data.get("scaling_factors", {})
        ) 