import numpy as np
from unittest.mock import patch, MagicMock
from bitcast.validator.reward import get_rewards
from bitcast.validator.reward import normalize_across_miners, normalize_across_briefs, normalise_scores


def test_get_rewards():
    # Create mock responses
    responses = [
        MagicMock(YT_access_token="token1"),
        MagicMock(YT_access_token="token2")
    ]

    # Create mock UIDs
    uids = [1, 2]

    # Mock scores to be returned by reward function
    mock_scores = [
        {"brief1": 10, "brief2": 10, "brief3": 10},  # Scores for response 1
        {"brief1": 15, "brief2": 15, "brief3": 15}   # Scores for response 2
    ]

    # Mock briefs to be returned by get_briefs
    mock_briefs = [{"id": "brief1"}, {"id": "brief2"}, {"id": "brief3"}]

    # Create a mock class instance for self parameter
    mock_self = MagicMock()

    # Patch get_briefs and reward functions
    with patch('bitcast.validator.reward.get_briefs', return_value=mock_briefs) as mock_get_briefs, \
         patch('bitcast.validator.reward.reward', side_effect=lambda uid, briefs, response: {"scores": mock_scores.pop(0)}) as mock_reward:
        
        # Call get_rewards
        result, yt_stats_list = get_rewards(mock_self, uids, responses)
        
        # Verify the result is a list of numpy float64 values
        assert isinstance(result, list)
        assert all(isinstance(score, np.float64) for score in result)
        
        # The expected result after normalization and summing
        # For the first response: [10, 10, 10] -> normalized across miners -> [0.4, 0.4, 0.4] -> normalized across briefs -> [0.133, 0.133, 0.133] -> sum = 0.4
        # For the second response: [15, 15, 15] -> normalized across miners -> [0.6, 0.6, 0.6] -> normalized across briefs -> [0.2, 0.2, 0.2] -> sum = 0.6
        expected_result = [0.4, 0.6]
        
        # Check that the result matches the expected values (with some tolerance for floating point)
        np.testing.assert_allclose(result, expected_result, rtol=1e-5)
        
        # Verify that get_briefs was called
        mock_get_briefs.assert_called_once()
        
        # Verify that reward was called for each response
        assert mock_reward.call_count == 2
        
        # Verify that yt_stats_list is returned
        assert isinstance(yt_stats_list, list)
        assert len(yt_stats_list) == 2

def test_get_rewards_identical_responses():
    # Create 3 identical mock responses
    responses = [
        MagicMock(YT_access_token="token1"),
        MagicMock(YT_access_token="token2"),
        MagicMock(YT_access_token="token3")
    ]

    # Create mock UIDs
    uids = [1, 2, 3]

    # Mock scores to be returned by reward function - all identical
    mock_scores = [
        {"brief1": 5, "brief2": 10, "brief3": 15},  # Scores for response 1
        {"brief1": 5, "brief2": 10, "brief3": 15},  # Scores for response 2
        {"brief1": 5, "brief2": 10, "brief3": 15}   # Scores for response 3
    ]

    # Mock briefs to be returned by get_briefs
    mock_briefs = [{"id": "brief1"}, {"id": "brief2"}, {"id": "brief3"}]

    # Create a mock class instance for self parameter
    mock_self = MagicMock()

    # Patch get_briefs and reward functions
    with patch('bitcast.validator.reward.get_briefs', return_value=mock_briefs) as mock_get_briefs, \
         patch('bitcast.validator.reward.reward', side_effect=lambda uid, briefs, response: {"scores": mock_scores.pop(0)}) as mock_reward:
        
        # Call get_rewards
        result, yt_stats_list = get_rewards(mock_self, uids, responses)
        
        # Verify the result is a list of numpy float64 values
        assert isinstance(result, list)
        assert all(isinstance(score, np.float64) for score in result)
        
        expected_result = [1/3, 1/3, 1/3]
        
        # Check that the result matches the expected values (with some tolerance for floating point)
        np.testing.assert_allclose(result, expected_result, rtol=1e-5)
        
        # Verify that get_briefs was called
        mock_get_briefs.assert_called_once()
        
        # Verify that reward was called for each response
        assert mock_reward.call_count == 3
        
        # Verify that yt_stats_list is returned
        assert isinstance(yt_stats_list, list)
        assert len(yt_stats_list) == 3

def test_get_rewards_with_zeros():
    # Create mock responses
    responses = [
        MagicMock(YT_access_token="token1"),
        MagicMock(YT_access_token="token2"),
        MagicMock(YT_access_token="token3")
    ]

    # Create mock UIDs
    uids = [1, 2, 3]

    # Mock scores to be returned by reward function - each has a zero in one position
    mock_scores = [
        {"brief1": 0, "brief2": 10, "brief3": 10},  # Scores for response 1
        {"brief1": 10, "brief2": 0, "brief3": 10},  # Scores for response 2
        {"brief1": 10, "brief2": 10, "brief3": 0}   # Scores for response 3
    ]

    # Mock briefs to be returned by get_briefs
    mock_briefs = [{"id": "brief1"}, {"id": "brief2"}, {"id": "brief3"}]

    # Create a mock class instance for self parameter
    mock_self = MagicMock()

    # Patch get_briefs and reward functions
    with patch('bitcast.validator.reward.get_briefs', return_value=mock_briefs) as mock_get_briefs, \
         patch('bitcast.validator.reward.reward', side_effect=lambda uid, briefs, response: {"scores": mock_scores.pop(0)}) as mock_reward:
        
        # Call get_rewards
        result, yt_stats_list = get_rewards(mock_self, uids, responses)
        
        # Verify the result is a list of numpy float64 values
        assert isinstance(result, list)
        assert all(isinstance(score, np.float64) for score in result)
        
        # The expected result after normalization and summing
        # Each response has a total of 20 (10+10+0)
        # After normalization across miners: [1/3, 1/3, 1/3]
        # After normalization across briefs: [1/9, 1/9, 1/9]
        # Final sum for each: 1/3
        expected_result = [1/3, 1/3, 1/3]
        
        # Check that the result matches the expected values (with some tolerance for floating point)
        np.testing.assert_allclose(result, expected_result, rtol=1e-5)
        
        # Verify that get_briefs was called
        mock_get_briefs.assert_called_once()
        
        # Verify that reward was called for each response
        assert mock_reward.call_count == 3
        
        # Verify that yt_stats_list is returned
        assert isinstance(yt_stats_list, list)
        assert len(yt_stats_list) == 3

def test_get_rewards_all_zeros_in_first_position():
    # Create mock responses
    responses = [
        MagicMock(YT_access_token="token1"),
        MagicMock(YT_access_token="token2"),
        MagicMock(YT_access_token="token3")
    ]

    # Create mock UIDs
    uids = [1, 2, 3]

    # Mock scores to be returned by reward function - all have zero in first position
    mock_scores = [
        {"brief1": 0, "brief2": 10, "brief3": 10},  # Scores for response 1
        {"brief1": 0, "brief2": 10, "brief3": 10},  # Scores for response 2
        {"brief1": 0, "brief2": 10, "brief3": 10}   # Scores for response 3
    ]

    # Mock briefs to be returned by get_briefs
    mock_briefs = [{"id": "brief1"}, {"id": "brief2"}, {"id": "brief3"}]

    # Create a mock class instance for self parameter
    mock_self = MagicMock()

    # Patch get_briefs and reward functions
    with patch('bitcast.validator.reward.get_briefs', return_value=mock_briefs) as mock_get_briefs, \
         patch('bitcast.validator.reward.reward', side_effect=lambda uid, briefs, response: {"scores": mock_scores.pop(0)}) as mock_reward:
        
        # Call get_rewards
        result, yt_stats_list = get_rewards(mock_self, uids, responses)
        
        # Verify the result is a list of numpy float64 values
        assert isinstance(result, list)
        assert all(isinstance(score, np.float64) for score in result)
        
        # The expected result after normalization and summing
        # Each response has a total of 20 (0+10+10)
        # After normalization across miners: [1/3, 1/3, 1/3]
        # After normalization across briefs: [0, 1/9, 1/9]
        # Final sum for each: 2/9
        expected_result = [2/9, 2/9, 2/9]
        
        # Check that the result matches the expected values (with some tolerance for floating point)
        np.testing.assert_allclose(result, expected_result, rtol=1e-5)
        
        # Verify that get_briefs was called
        mock_get_briefs.assert_called_once()
        
        # Verify that reward was called for each response
        assert mock_reward.call_count == 3
        
        # Verify that yt_stats_list is returned
        assert isinstance(yt_stats_list, list)
        assert len(yt_stats_list) == 3

def test_get_rewards_uid_0():
    # Create mock responses
    responses = [
        MagicMock(YT_access_token="token1"),
        MagicMock(YT_access_token="token2"),
        MagicMock(YT_access_token="token3")
    ]

    # Create mock UIDs - include UID 0
    uids = [0, 1, 2]

    # Mock briefs to be returned by get_briefs
    mock_briefs = [{"id": "brief1"}, {"id": "brief2"}, {"id": "brief3"}]

    # Create a mock class instance for self parameter
    mock_self = MagicMock()

    # Patch get_briefs and reward functions
    with patch('bitcast.validator.reward.get_briefs', return_value=mock_briefs) as mock_get_briefs, \
         patch('bitcast.validator.reward.reward', side_effect=lambda uid, briefs, response: {"scores": {brief["id"]: 1.0 if uid == 0 else 0.5 for brief in briefs}}) as mock_reward:
        
        # Call get_rewards
        result, yt_stats_list = get_rewards(mock_self, uids, responses)
        
        # Verify the result is a list of numpy float64 values
        assert isinstance(result, list)
        assert all(isinstance(score, np.float64) for score in result)
        
        # The expected result after normalization and summing
        # For UID 0: [1.0, 1.0, 1.0] -> normalized across miners -> [0.5, 0.5, 0.5] -> normalized across briefs -> [0.167, 0.167, 0.167] -> sum = 0.5
        # For other UIDs: [0.5, 0.5, 0.5] -> normalized across miners -> [0.25, 0.25, 0.25] -> normalized across briefs -> [0.083, 0.083, 0.083] -> sum = 0.25
        expected_result = [0.5, 0.25, 0.25]
        
        # Check that the result matches the expected values (with some tolerance for floating point)
        np.testing.assert_allclose(result, expected_result, rtol=1e-5)
        
        # Verify that get_briefs was called
        mock_get_briefs.assert_called_once()
        
        # Verify that reward was called for each response
        assert mock_reward.call_count == 3
        
        # Verify that yt_stats_list is returned
        assert isinstance(yt_stats_list, list)
        assert len(yt_stats_list) == 3

def test_get_rewards_empty_briefs():
    # Create mock responses
    responses = [
        MagicMock(YT_access_token="token1"),
        MagicMock(YT_access_token="token2"),
        MagicMock(YT_access_token="token3")
    ]

    # Create mock UIDs - include UID 0
    uids = [0, 1, 2]

    # Create a mock class instance for self parameter
    mock_self = MagicMock()

    # Patch get_briefs to return an empty list
    with patch('bitcast.validator.reward.get_briefs', return_value=[]) as mock_get_briefs:
        
        # Call get_rewards
        result, yt_stats_list = get_rewards(mock_self, uids, responses)
        
        # Verify the result is a numpy array
        assert isinstance(result, np.ndarray)
        
        # Verify the expected result: UID 0 gets 1.0, others get 0.0
        expected_result = np.array([1.0, 0.0, 0.0])
        np.testing.assert_allclose(result, expected_result, rtol=1e-5)
        
        # Verify that get_briefs was called
        mock_get_briefs.assert_called_once()
        
        # Verify that yt_stats_list is returned with the correct structure
        assert isinstance(yt_stats_list, list)
        assert len(yt_stats_list) == 3
        
        # Verify that UID 0 has a score of 1.0
        assert yt_stats_list[0]["scores"] == {}
        
        # Verify that other UIDs have a score of 0.0
        assert yt_stats_list[1]["scores"] == {}
        assert yt_stats_list[2]["scores"] == {}

def test_normalize_across_miners():
    # Test with regular matrix
    scores_matrix = np.array([[10, 30, 2], [90, 70, 2]])
    normalized_scores = normalize_across_miners(scores_matrix)
    assert np.allclose(normalized_scores, [[0.1, 0.3, 0.5], [0.9, 0.7, 0.5]])
    
    # Test with empty matrix
    assert normalize_across_miners(np.array([])) == []
    
    # Test with single row
    scores_matrix = np.array([[10, 30, 2]])
    normalized_scores = normalize_across_miners(scores_matrix)
    assert np.allclose(normalized_scores, [[1.0, 1.0, 1.0]])
    
    # Test with all zeros
    scores_matrix = np.array([[0, 0], [0, 0]])
    normalized_scores = normalize_across_miners(scores_matrix)
    assert np.allclose(normalized_scores, [[0, 0], [0, 0]])

def test_normalize_across_briefs():
    # Test with regular matrix
    normalized_scores_matrix = [[0.4, 0.2, 0.4, 0.2], [0.6, 0.8, 0.6, 0.8]]
    normalized_across_briefs = normalize_across_briefs(normalized_scores_matrix)
    assert np.allclose(normalized_across_briefs, [[0.1, 0.05, 0.1, 0.05], [0.15, 0.2, 0.15, 0.2]])
    
    # Test with empty matrix
    assert normalize_across_briefs([]) == []
    
    # Test with single brief
    normalized_scores_matrix = [[0.4], [0.6]]
    normalized_across_briefs = normalize_across_briefs(normalized_scores_matrix)
    assert np.allclose(normalized_across_briefs, [[0.4], [0.6]])

def test_normalise_scores():
    # Test with regular matrix
    scores_matrix = np.array([[10, 30, 2], [90, 70, 2]])
    final_scores = normalise_scores(scores_matrix)
    # After normalize_across_miners: [[0.1, 0.3, 0.5], [0.9, 0.7, 0.5]]
    # After normalize_across_briefs: [[0.033, 0.1, 0.167], [0.3, 0.233, 0.167]]
    # After summing rows: [0.3, 0.7]
    assert np.allclose(final_scores, [0.3, 0.7])
    
    # Test with empty matrix
    assert normalise_scores(np.array([])) == []
    
    # Test with single row
    scores_matrix = np.array([[10, 30, 2]])
    final_scores = normalise_scores(scores_matrix)
    assert np.allclose(final_scores, [1.0])
    
    # Test with all zeros
    scores_matrix = np.array([[0, 0], [0, 0]])
    final_scores = normalise_scores(scores_matrix)
    assert np.allclose(final_scores, [0.0, 0.0])
