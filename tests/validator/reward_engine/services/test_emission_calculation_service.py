"""Unit tests for EmissionCalculationService."""

import pytest
import numpy as np
from unittest.mock import patch, Mock
from bitcast.validator.reward_engine.services.emission_calculation_service import EmissionCalculationService
from bitcast.validator.reward_engine.models.score_matrix import ScoreMatrix


class TestEmissionCalculationService:
    """Test EmissionCalculationService class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = EmissionCalculationService()
        
    @pytest.fixture
    def sample_briefs(self):
        """Sample briefs for testing."""
        return [
            {"id": "brief1", "format": "dedicated", "weight": 100},
            {"id": "brief2", "format": "ad-read", "weight": 100}
        ]
    
    @pytest.fixture
    def sample_briefs_with_boost(self):
        """Sample briefs with Boost field for testing."""
        return [
            {"id": "brief1", "format": "dedicated", "weight": 100, "boost": 2.0},
            {"id": "brief2", "format": "ad-read", "weight": 100, "boost": 1.5}
        ]
    
    @pytest.fixture
    def sample_score_matrix(self):
        """Sample score matrix for testing."""
        return ScoreMatrix(np.array([[10.0, 5.0], [8.0, 12.0]]))
    
    def test_boost_field_not_specified_defaults_to_one(self, sample_briefs, sample_score_matrix):
        """Test that briefs without Boost field default to 1.0 (no change in behavior)."""
        with patch('bitcast.validator.reward_engine.services.emission_calculation_service.get_bitcast_alpha_price', return_value=1.0), \
             patch('bitcast.validator.reward_engine.services.emission_calculation_service.get_total_miner_emissions', return_value=1000.0):
            
            targets = self.service.calculate_targets(sample_score_matrix, sample_briefs)
            
            # Verify boost_factor is 1.0 in metadata
            assert targets[0].scaling_factors["boost_factor"] == 1.0
            assert targets[1].scaling_factors["boost_factor"] == 1.0
    
    def test_boost_field_specified_applied_correctly(self, sample_briefs_with_boost, sample_score_matrix):
        """Test that Boost field multiplies scores correctly."""
        with patch('bitcast.validator.reward_engine.services.emission_calculation_service.get_bitcast_alpha_price', return_value=1.0), \
             patch('bitcast.validator.reward_engine.services.emission_calculation_service.get_total_miner_emissions', return_value=1000.0):
            
            targets = self.service.calculate_targets(sample_score_matrix, sample_briefs_with_boost)
            
            # Verify boost_factor is stored in metadata
            assert targets[0].scaling_factors["boost_factor"] == 2.0
            assert targets[1].scaling_factors["boost_factor"] == 1.5
    
    
    def test_multiple_briefs_different_boost_values(self):
        """Test multiple briefs with different boost values work correctly."""
        score_matrix = ScoreMatrix(np.array([[10.0, 5.0], [8.0, 12.0]]))
        briefs = [
            {"id": "brief1", "format": "dedicated", "weight": 100, "boost": 3.0},
            {"id": "brief2", "format": "ad-read", "weight": 100, "boost": 0.5}
        ]
        
        with patch('bitcast.validator.reward_engine.services.emission_calculation_service.get_bitcast_alpha_price', return_value=1.0), \
             patch('bitcast.validator.reward_engine.services.emission_calculation_service.get_total_miner_emissions', return_value=1000.0):
            
            targets = self.service.calculate_targets(score_matrix, briefs)
            
            # Verify correct boost factors stored
            assert targets[0].scaling_factors["boost_factor"] == 3.0
            assert targets[1].scaling_factors["boost_factor"] == 0.5
            
            # Verify both briefs processed
            assert len(targets) == 2
            assert targets[0].brief_id == "brief1"
            assert targets[1].brief_id == "brief2"
    
    def test_basic_emission_calculation(self):
        """Test basic emission target calculation with single brief."""
        score_matrix = ScoreMatrix(np.array([[100.0]]))
        briefs = [{"id": "brief1", "format": "dedicated", "weight": 100, "boost": 2.0}]
        
        with patch('bitcast.validator.reward_engine.services.emission_calculation_service.get_bitcast_alpha_price', return_value=1.0), \
             patch('bitcast.validator.reward_engine.services.emission_calculation_service.get_total_miner_emissions', return_value=1000.0):
            
            targets = self.service.calculate_targets(score_matrix, briefs)
            assert len(targets) == 1
            assert targets[0].usd_target == 100.0  # Should equal input USD value
    
    def test_boost_execution_with_large_values(self):
        """Test that boost functionality executes correctly with various boost values."""
        score_matrix = ScoreMatrix(np.array([[10.0]]))
        
        # Test different boost values to ensure they execute without error
        boost_values = [0.5, 1.0, 2.5, 10.0]
        
        for boost_val in boost_values:
            briefs = [{"id": "test_brief", "format": "dedicated", "weight": 100, "boost": boost_val}]
            
            with patch('bitcast.validator.reward_engine.services.emission_calculation_service.get_bitcast_alpha_price', return_value=1.0), \
                 patch('bitcast.validator.reward_engine.services.emission_calculation_service.get_total_miner_emissions', return_value=1000.0):
                
                targets = self.service.calculate_targets(score_matrix, briefs)
                
                # Verify execution completed successfully
                assert len(targets) == 1
                assert targets[0].scaling_factors["boost_factor"] == boost_val
                assert targets[0].usd_target >= 0
    
    def test_existing_functionality_unchanged(self, sample_briefs, sample_score_matrix):
        """Test that existing functionality works unchanged when no Boost field is present."""
        with patch('bitcast.validator.reward_engine.services.emission_calculation_service.get_bitcast_alpha_price', return_value=1.0), \
             patch('bitcast.validator.reward_engine.services.emission_calculation_service.get_total_miner_emissions', return_value=1000.0):
            
            targets = self.service.calculate_targets(sample_score_matrix, sample_briefs)
            
            # Should have targets for both briefs
            assert len(targets) == 2
            
            # Should have positive USD targets
            assert targets[0].usd_target >= 0
            assert targets[1].usd_target >= 0
            
            # Should have proper structure with boost metadata
            assert isinstance(targets[0].scaling_factors, dict)
            assert isinstance(targets[1].scaling_factors, dict)
    
    def test_zero_score_matrix_handling(self):
        """Test handling of zero score matrix."""
        zero_matrix = ScoreMatrix(np.zeros((2, 1)))  # 2 miners, 1 brief, all zeros
        briefs = [{"id": "brief1", "format": "dedicated", "weight": 100, "boost": 2.0}]
        
        with patch('bitcast.validator.reward_engine.services.emission_calculation_service.get_bitcast_alpha_price', return_value=1.0), \
             patch('bitcast.validator.reward_engine.services.emission_calculation_service.get_total_miner_emissions', return_value=1000.0):
            
            targets = self.service.calculate_targets(zero_matrix, briefs)
            
            # Should handle zero matrix gracefully
            assert len(targets) == 1
            assert targets[0].usd_target == 0.0
            assert targets[0].scaling_factors["boost_factor"] == 2.0 