"""Unit tests for PlatformRegistry service."""

import pytest
from unittest.mock import Mock

from bitcast.validator.reward_engine.services.platform_registry import PlatformRegistry
from bitcast.validator.reward_engine.interfaces.platform_evaluator import PlatformEvaluator
from bitcast.validator.reward_engine.models.miner_response import MinerResponse


class MockPlatformEvaluator(PlatformEvaluator):
    """Mock platform evaluator for testing."""
    
    def __init__(self, platform_name: str, can_evaluate_response: bool = True):
        self._platform_name = platform_name
        self._can_evaluate_response = can_evaluate_response
    
    def platform_name(self) -> str:
        return self._platform_name
    
    def can_evaluate(self, miner_response) -> bool:
        return self._can_evaluate_response
    
    async def evaluate_accounts(self, miner_response, briefs, metagraph_info):
        return Mock()
    
    def get_supported_token_types(self):
        return [f"{self._platform_name}_tokens"]


class TestPlatformRegistry:
    
    def setup_method(self):
        """Set up test registry."""
        self.registry = PlatformRegistry()
    
    def test_register_evaluator(self):
        """Test registering a platform evaluator."""
        evaluator = MockPlatformEvaluator("youtube")
        self.registry.register_evaluator(evaluator)
        
        assert len(self.registry) == 1
        assert "youtube" in self.registry.get_available_platforms()
    
    def test_get_evaluator(self):
        """Test getting a specific evaluator."""
        evaluator = MockPlatformEvaluator("youtube")
        self.registry.register_evaluator(evaluator)
        
        retrieved = self.registry.get_evaluator("youtube")
        assert retrieved == evaluator
        
        # Test non-existent platform
        none_evaluator = self.registry.get_evaluator("nonexistent")
        assert none_evaluator is None
    
    def test_get_evaluator_for_response(self):
        """Test getting evaluator for a specific response."""
        youtube_evaluator = MockPlatformEvaluator("youtube")
        tiktok_evaluator = MockPlatformEvaluator("tiktok", can_evaluate_response=False)
        
        self.registry.register_evaluator(youtube_evaluator)
        self.registry.register_evaluator(tiktok_evaluator)
        
        response = MinerResponse(uid=123, response_data=Mock(), is_valid=True)
        
        evaluator = self.registry.get_evaluator_for_response(response)
        assert evaluator == youtube_evaluator
    
    def test_get_evaluator_for_invalid_response(self):
        """Test getting evaluator for invalid response."""
        evaluator = MockPlatformEvaluator("youtube")
        self.registry.register_evaluator(evaluator)
        
        # Invalid response
        invalid_response = MinerResponse(uid=123, response_data=None, is_valid=False)
        
        result = self.registry.get_evaluator_for_response(invalid_response)
        assert result is None
    
    def test_get_evaluator_for_response_no_match(self):
        """Test getting evaluator when no evaluator can handle the response."""
        evaluator = MockPlatformEvaluator("youtube", can_evaluate_response=False)
        self.registry.register_evaluator(evaluator)
        
        response = MinerResponse(uid=123, response_data=Mock(), is_valid=True)
        
        result = self.registry.get_evaluator_for_response(response)
        assert result is None
    
    def test_get_available_platforms(self):
        """Test getting list of available platforms."""
        youtube_evaluator = MockPlatformEvaluator("youtube")
        tiktok_evaluator = MockPlatformEvaluator("tiktok")
        
        self.registry.register_evaluator(youtube_evaluator)
        self.registry.register_evaluator(tiktok_evaluator)
        
        platforms = self.registry.get_available_platforms()
        assert len(platforms) == 2
        assert "youtube" in platforms
        assert "tiktok" in platforms
    
    def test_multiple_evaluators(self):
        """Test registry with multiple evaluators."""
        evaluators = [
            MockPlatformEvaluator("youtube"),
            MockPlatformEvaluator("tiktok"),
            MockPlatformEvaluator("instagram")
        ]
        
        for evaluator in evaluators:
            self.registry.register_evaluator(evaluator)
        
        assert len(self.registry) == 3
        assert len(self.registry.get_available_platforms()) == 3
        
        # Test each can be retrieved
        for evaluator in evaluators:
            platform = evaluator.platform_name()
            retrieved = self.registry.get_evaluator(platform)
            assert retrieved == evaluator
    
    def test_registry_repr(self):
        """Test string representation of registry."""
        youtube_evaluator = MockPlatformEvaluator("youtube")
        self.registry.register_evaluator(youtube_evaluator)
        
        repr_str = repr(self.registry)
        assert "PlatformRegistry" in repr_str
        assert "youtube" in repr_str
    
    def test_priority_evaluator_selection(self):
        """Test that YouTube evaluator gets priority in selection."""
        # Register YouTube last to ensure priority order works
        tiktok_evaluator = MockPlatformEvaluator("tiktok")
        youtube_evaluator = MockPlatformEvaluator("youtube")
        
        self.registry.register_evaluator(tiktok_evaluator)
        self.registry.register_evaluator(youtube_evaluator)
        
        response = MinerResponse(uid=123, response_data=Mock(), is_valid=True)
        
        # Should return YouTube evaluator first due to priority
        evaluator = self.registry.get_evaluator_for_response(response)
        assert evaluator.platform_name() == "youtube" 