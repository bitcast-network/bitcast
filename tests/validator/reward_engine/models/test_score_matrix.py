"""Unit tests for ScoreMatrix model."""

import pytest
import numpy as np
from bitcast.validator.reward_engine.models.score_matrix import ScoreMatrix


class TestScoreMatrix:
    """Test ScoreMatrix class."""
    
    def test_create_empty(self):
        """Test creating an empty score matrix."""
        matrix = ScoreMatrix.create_empty(3, 2)
        assert matrix.num_miners == 3
        assert matrix.num_briefs == 2
        assert matrix.get_score(0, 0) == 0.0
        assert matrix.get_score(2, 1) == 0.0
    
    def test_set_and_get_score(self):
        """Test setting and getting individual scores."""
        matrix = ScoreMatrix.create_empty(2, 2)
        matrix.set_score(0, 1, 0.8)
        matrix.set_score(1, 0, 0.5)
        
        assert matrix.get_score(0, 1) == 0.8
        assert matrix.get_score(1, 0) == 0.5
        assert matrix.get_score(0, 0) == 0.0  # Default value
    
    def test_boundary_conditions(self):
        """Test boundary conditions for score access."""
        matrix = ScoreMatrix.create_empty(2, 2)
        
        # Test out of bounds access
        assert matrix.get_score(-1, 0) == 0.0
        assert matrix.get_score(0, -1) == 0.0
        assert matrix.get_score(2, 0) == 0.0  # Beyond num_miners
        assert matrix.get_score(0, 2) == 0.0  # Beyond num_briefs
        
        # Test setting out of bounds (should not raise error)
        matrix.set_score(-1, 0, 0.5)  # Should be ignored
        matrix.set_score(2, 0, 0.5)   # Should be ignored
        
        # Verify matrix is unchanged
        assert np.all(matrix.matrix == 0)
    
    def test_get_miner_scores(self):
        """Test getting all scores for a specific miner."""
        matrix = ScoreMatrix.create_empty(2, 3)
        matrix.set_score(0, 0, 0.1)
        matrix.set_score(0, 1, 0.2)
        matrix.set_score(0, 2, 0.3)
        
        miner_scores = matrix.get_miner_scores(0)
        expected = np.array([0.1, 0.2, 0.3])
        np.testing.assert_array_equal(miner_scores, expected)
        
        # Test out of bounds
        out_of_bounds = matrix.get_miner_scores(5)
        np.testing.assert_array_equal(out_of_bounds, np.zeros(3))
    
    def test_get_brief_scores(self):
        """Test getting all scores for a specific brief."""
        matrix = ScoreMatrix.create_empty(3, 2)
        matrix.set_score(0, 1, 0.4)
        matrix.set_score(1, 1, 0.5)
        matrix.set_score(2, 1, 0.6)
        
        brief_scores = matrix.get_brief_scores(1)
        expected = np.array([0.4, 0.5, 0.6])
        np.testing.assert_array_equal(brief_scores, expected)
        
        # Test out of bounds
        out_of_bounds = matrix.get_brief_scores(5)
        np.testing.assert_array_equal(out_of_bounds, np.zeros(3))
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        matrix = ScoreMatrix.create_empty(2, 2)
        matrix.set_score(0, 1, 0.5)
        matrix.set_score(1, 0, 0.7)
        
        data = matrix.to_dict()
        assert data["num_miners"] == 2
        assert data["num_briefs"] == 2
        assert data["matrix"][0][1] == 0.5
        assert data["matrix"][1][0] == 0.7
    
    def test_initialization_with_existing_matrix(self):
        """Test initialization with an existing numpy array."""
        initial_data = np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]])
        matrix = ScoreMatrix(initial_data)
        
        assert matrix.num_miners == 3
        assert matrix.num_briefs == 2
        assert matrix.get_score(1, 1) == 0.4
        assert matrix.get_score(2, 0) == 0.5
    
    def test_repr(self):
        """Test string representation."""
        matrix = ScoreMatrix.create_empty(3, 2)
        repr_str = repr(matrix)
        assert "ScoreMatrix(3×2)" in repr_str 