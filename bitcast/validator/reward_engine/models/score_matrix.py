"""Data model for score matrix operations."""

import numpy as np
from typing import Dict, Any


class ScoreMatrix:
    """Handles score matrix operations for reward calculations."""
    
    def __init__(self, matrix: np.ndarray):
        """Initialize with a score matrix."""
        self.matrix = matrix.astype(np.float64)  # Ensure consistent data type
        self.num_miners, self.num_briefs = matrix.shape
    
    @classmethod
    def create_empty(cls, num_miners: int, num_briefs: int) -> 'ScoreMatrix':
        """Create an empty score matrix with zeros."""
        matrix = np.zeros((num_miners, num_briefs), dtype=np.float64)
        return cls(matrix)
    
    def set_score(self, miner_idx: int, brief_idx: int, score: float):
        """Set a score for a specific miner and brief."""
        if 0 <= miner_idx < self.num_miners and 0 <= brief_idx < self.num_briefs:
            self.matrix[miner_idx, brief_idx] = score
    
    def get_score(self, miner_idx: int, brief_idx: int) -> float:
        """Get a score for a specific miner and brief."""
        if 0 <= miner_idx < self.num_miners and 0 <= brief_idx < self.num_briefs:
            return self.matrix[miner_idx, brief_idx]
        return 0.0
    
    def get_miner_scores(self, miner_idx: int) -> np.ndarray:
        """Get all scores for a specific miner."""
        if 0 <= miner_idx < self.num_miners:
            return self.matrix[miner_idx, :]
        return np.zeros(self.num_briefs, dtype=np.float64)
    
    def get_brief_scores(self, brief_idx: int) -> np.ndarray:
        """Get all scores for a specific brief."""
        if 0 <= brief_idx < self.num_briefs:
            return self.matrix[:, brief_idx]
        return np.zeros(self.num_miners, dtype=np.float64)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "matrix": self.matrix.tolist(),
            "num_miners": self.num_miners,
            "num_briefs": self.num_briefs
        }
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"ScoreMatrix({self.num_miners}×{self.num_briefs})" 