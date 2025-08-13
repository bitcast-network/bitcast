"""
Simplified tests for RunManager class focusing on core functionality.
"""

import pytest
import time
from unittest.mock import Mock, patch
from datetime import datetime

import bittensor as bt

from bitcast.validator.utils.run_manager import RunManager, generate_current_run_id


class TestRunManagerCore:
    """Test cases for core RunManager functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create mock wallet
        self.mock_wallet = Mock()
        self.mock_hotkey = Mock()
        self.mock_hotkey.ss58_address = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
        self.mock_wallet.hotkey = self.mock_hotkey
        
        self.run_manager = RunManager(self.mock_wallet)
    
    def test_run_manager_initialization(self):
        """Test RunManager initializes correctly."""
        assert self.run_manager.wallet == self.mock_wallet
        assert self.run_manager.current_run_id is None
        assert hasattr(self.run_manager, '_lock')
    
    @patch('bitcast.validator.utils.run_manager.datetime')
    def test_generate_run_id_format(self, mock_datetime):
        """Test run ID generation follows correct format."""
        # Mock datetime
        mock_datetime.utcnow.return_value.strftime.return_value = "20250106_120000"
        
        run_id = self.run_manager.generate_run_id()
        
        expected = "vali_5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY_20250106_120000"
        assert run_id == expected
        assert self.run_manager.current_run_id == expected
    
    @patch('bitcast.validator.utils.run_manager.datetime')
    def test_generate_run_id_uniqueness(self, mock_datetime):
        """Test that each run ID generation creates unique timestamps."""
        # Mock different timestamps
        mock_datetime.utcnow.return_value.strftime.side_effect = [
            "20250106_120000", 
            "20250106_120001"
        ]
        
        run_id1 = self.run_manager.generate_run_id()
        run_id2 = self.run_manager.generate_run_id()
        
        assert run_id1 != run_id2
        assert "20250106_120000" in run_id1
        assert "20250106_120001" in run_id2
    
    def test_get_current_run_id_none(self):
        """Test get_current_run_id returns None when no run ID generated."""
        assert self.run_manager.get_current_run_id() is None
    
    @patch('bitcast.validator.utils.run_manager.datetime')
    def test_get_current_run_id_after_generation(self, mock_datetime):
        """Test get_current_run_id returns correct ID after generation."""
        mock_datetime.utcnow.return_value.strftime.return_value = "20250106_120000"
        
        run_id = self.run_manager.generate_run_id()
        assert self.run_manager.get_current_run_id() == run_id
    
    def test_reset_run_id(self):
        """Test reset_run_id clears current run ID."""
        # Generate a run ID first
        with patch('bitcast.validator.utils.run_manager.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value.strftime.return_value = "20250106_120000"
            self.run_manager.generate_run_id()
        
        assert self.run_manager.get_current_run_id() is not None
        
        self.run_manager.reset_run_id()
        assert self.run_manager.get_current_run_id() is None
    
    @patch('bitcast.validator.utils.run_manager.datetime')
    @patch('bitcast.validator.utils.run_manager.get_run_manager')
    def test_generate_current_run_id_function(self, mock_get_manager, mock_datetime):
        """Test generate_current_run_id convenience function."""
        mock_datetime.utcnow.return_value.strftime.return_value = "20250106_120000"
        
        # Create a manager with the properly mocked wallet
        test_manager = RunManager(self.mock_wallet)
        mock_get_manager.return_value = test_manager
        
        run_id = generate_current_run_id(self.mock_wallet)
        
        expected = "vali_5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY_20250106_120000"
        assert run_id == expected


class TestRunManagerIntegration:
    """Integration tests for RunManager with real datetime."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create mock wallet
        self.mock_wallet = Mock()
        self.mock_hotkey = Mock()
        self.mock_hotkey.ss58_address = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
        self.mock_wallet.hotkey = self.mock_hotkey
    
    def test_real_run_id_generation(self):
        """Test run ID generation with real datetime."""
        manager = RunManager(self.mock_wallet)
        
        run_id = manager.generate_run_id()
        
        # Verify format
        assert run_id.startswith("vali_5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY_")
        parts = run_id.split("_")
        assert len(parts) == 4  # vali, hotkey, date, time
        assert parts[0] == "vali"
        
        # Verify timestamp format (YYYYMMDD_HHMMSS split into parts)
        date_part = parts[2]  # YYYYMMDD
        time_part = parts[3]  # HHMMSS
        assert len(date_part) == 8  # YYYYMMDD
        assert len(time_part) == 6  # HHMMSS
        
        # Verify it's a valid datetime format
        datetime.strptime(f"{date_part}_{time_part}", "%Y%m%d_%H%M%S")
    
    def test_multiple_generations_different_timestamps(self):
        """Test multiple run ID generations with mocked different timestamps."""
        manager = RunManager(self.mock_wallet)
        
        # Use mocking to guarantee different timestamps
        with patch('bitcast.validator.utils.run_manager.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value.strftime.side_effect = [
                "20250106_120000", 
                "20250106_120001"
            ]
            
            run_id1 = manager.generate_run_id()
            run_id2 = manager.generate_run_id()
            
            assert run_id1 != run_id2
            assert "20250106_120000" in run_id1
            assert "20250106_120001" in run_id2