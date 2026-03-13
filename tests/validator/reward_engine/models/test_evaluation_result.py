"""Unit tests for evaluation result models."""

import pytest
from bitcast.validator.reward_engine.models.evaluation_result import (
    AccountResult, EvaluationResult, EvaluationResultCollection
)


class TestAccountResult:
    """Test AccountResult class."""
    
    def test_create_success_result(self):
        """Test creating a successful account result."""
        result = AccountResult(
            account_id="test_account",
            platform_data={"channel_id": "123"},
            videos={"video1": {"views": 1000}},
            scores={"brief1": 0.5, "brief2": 0.8},
            performance_stats={"total_views": 1000},
            success=True
        )
        
        assert result.account_id == "test_account"
        assert result.success is True
        assert result.scores["brief1"] == 0.5
        assert result.error_message == ""
    
    def test_create_error_result(self):
        """Test creating an error result."""
        briefs = [{"id": "brief1"}, {"id": "brief2"}]
        result = AccountResult.create_error_result(
            "test_account", "API error", briefs
        )
        
        assert result.account_id == "test_account"
        assert result.success is False
        assert result.error_message == "API error"
        assert result.scores == {"brief1": 0.0, "brief2": 0.0}
        assert result.platform_data == {}


class TestEvaluationResult:
    """Test EvaluationResult class."""
    
    def test_create_evaluation_result(self):
        """Test creating an evaluation result."""
        result = EvaluationResult(
            uid=123,
            platform="youtube"
        )
        
        assert result.uid == 123
        assert result.platform == "youtube"
        assert len(result.account_results) == 0
    
    def test_add_account_result(self):
        """Test adding account results."""
        result = EvaluationResult(uid=123, platform="youtube")
        
        account_result = AccountResult(
            account_id="account1",
            platform_data={},
            videos={},
            scores={"brief1": 0.5},
            performance_stats={},
            success=True
        )
        
        result.add_account_result("account1", account_result)
        
        assert len(result.account_results) == 1
        assert result.account_results["account1"] == account_result
    
    def test_get_total_score_for_brief(self):
        """Test getting total score for a brief."""
        result = EvaluationResult(
            uid=123,
            platform="youtube",
            aggregated_scores={"brief1": 1.5, "brief2": 2.0}
        )
        
        assert result.get_total_score_for_brief("brief1") == 1.5
        assert result.get_total_score_for_brief("brief3") == 0.0


class TestEvaluationResultMerge:
    """Test EvaluationResult.merge method."""
    
    def test_merge_combines_accounts(self):
        """Test that merge adds accounts from other result."""
        result_a = EvaluationResult(
            uid=1, platform="youtube",
            aggregated_scores={"brief1": 1.0}
        )
        result_a.add_account_result("account_1", AccountResult(
            account_id="account_1", platform_data={}, videos={},
            scores={"brief1": 1.0}, performance_stats={}, success=True
        ))
        
        result_b = EvaluationResult(
            uid=1, platform="youtube",
            aggregated_scores={"brief1": 2.0}
        )
        result_b.add_account_result("account_2", AccountResult(
            account_id="account_2", platform_data={}, videos={},
            scores={"brief1": 2.0}, performance_stats={}, success=True
        ))
        
        result_a.merge(result_b)
        
        assert len(result_a.account_results) == 2
        assert "account_1" in result_a.account_results
        assert "account_2" in result_a.account_results
    
    def test_merge_sums_scores(self):
        """Test that merge sums aggregated scores across briefs."""
        result_a = EvaluationResult(
            uid=1, platform="youtube",
            aggregated_scores={"brief1": 1.0, "brief2": 0.5}
        )
        result_b = EvaluationResult(
            uid=1, platform="youtube",
            aggregated_scores={"brief1": 2.0, "brief2": 1.5}
        )
        
        result_a.merge(result_b)
        
        assert result_a.aggregated_scores["brief1"] == 3.0
        assert result_a.aggregated_scores["brief2"] == 2.0
    
    def test_merge_handles_new_brief_ids(self):
        """Test merge when other has brief IDs not in self."""
        result_a = EvaluationResult(
            uid=1, platform="youtube",
            aggregated_scores={"brief1": 1.0}
        )
        result_b = EvaluationResult(
            uid=1, platform="youtube",
            aggregated_scores={"brief2": 3.0}
        )
        
        result_a.merge(result_b)
        
        assert result_a.aggregated_scores["brief1"] == 1.0
        assert result_a.aggregated_scores["brief2"] == 3.0
    
    def test_merge_empty_other(self):
        """Test merging an empty result changes nothing."""
        result_a = EvaluationResult(
            uid=1, platform="youtube",
            aggregated_scores={"brief1": 5.0}
        )
        result_a.add_account_result("account_1", AccountResult(
            account_id="account_1", platform_data={}, videos={},
            scores={"brief1": 5.0}, performance_stats={}, success=True
        ))
        
        result_b = EvaluationResult(uid=1, platform="youtube", aggregated_scores={})
        
        result_a.merge(result_b)
        
        assert len(result_a.account_results) == 1
        assert result_a.aggregated_scores["brief1"] == 5.0


class TestEvaluationResultCollection:
    """Test EvaluationResultCollection class."""
    
    def test_create_collection(self):
        """Test creating an empty collection."""
        collection = EvaluationResultCollection()
        assert len(collection.results) == 0
    
    def test_add_result(self):
        """Test adding results to collection."""
        collection = EvaluationResultCollection()
        result = EvaluationResult(uid=123, platform="youtube")
        
        collection.add_result(123, result)
        
        assert len(collection.results) == 1
        assert collection.results[123] == result
    
    def test_add_empty_result(self):
        """Test adding empty results."""
        collection = EvaluationResultCollection()
        collection.add_empty_result(456, "No response")
        
        result = collection.get_result(456)
        assert result is not None
        assert result.uid == 456
        assert result.platform == "unknown"
    
    def test_get_result(self):
        """Test getting results from collection."""
        collection = EvaluationResultCollection()
        result = EvaluationResult(uid=123, platform="youtube")
        collection.add_result(123, result)
        
        retrieved = collection.get_result(123)
        assert retrieved == result
        
        missing = collection.get_result(999)
        assert missing is None


class TestAccountResultBasicPosting:
    """Basic test for AccountResult posting functionality."""
    
    def test_to_posting_payload_basic_functionality(self):
        """Test that to_posting_payload returns properly structured data."""
        account_result = AccountResult(
            account_id="test_account",
            platform_data={"channel_id": "UC123"},
            videos={"video1": {"title": "Test Video"}},
            scores={"brief1": 0.8},
            performance_stats={"api_calls": 5},
            success=True
        )
        
        payload = account_result.to_posting_payload(
            run_id="test_run_123",
            miner_uid=456,
            platform="youtube"
        )
        
        # Verify structure
        assert "account_data" in payload
        account_data = payload["account_data"]
        assert "yt_account" in account_data
        assert "videos" in account_data  
        assert "scores" in account_data
        assert "performance_stats" in account_data
        assert account_data["success"] is True 