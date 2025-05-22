import numpy as np
from unittest.mock import patch, MagicMock
from bitcast.validator.reward import get_rewards
from bitcast.validator.reward import normalize_across_miners, normalize_across_briefs, normalise_scores

# Mock briefs with max_burn=0 to maintain original test behavior
MOCK_TEST_BRIEFS = [
    {"id": "brief1", "max_burn": 0.0, "burn_decay": 0.01},
    {"id": "brief2", "max_burn": 0.0, "burn_decay": 0.01},
    {"id": "brief3", "max_burn": 0.0, "burn_decay": 0.01}
]

def test_get_rewards():
    # Create mock responses
    responses = [
        MagicMock(YT_access_token=None),
        MagicMock(YT_access_token="token1"),
        MagicMock(YT_access_token="token2")
    ]

    # Create mock UIDs
    uids = [0, 1, 2]

    # Mock yt_stats to be returned by reward function, including videos with minutes watched
    mock_yt_stats = [
        {"scores": {"brief1": 0, "brief2": 0, "brief3": 0}, "videos": {}},
        {"yt_account": {"channel_vet_result": True}, "scores": {"brief1": 10, "brief2": 10, "brief3": 10}, "videos": {
            "video1": {"analytics": {"minutes_watched_w_lag": 10, "scorable_proportion": 1.0}, "matching_brief_ids": ["brief1", "brief2", "brief3"], "decision_details": {"video_vet_result": True}}
        }},
        {"yt_account": {"channel_vet_result": True}, "scores": {"brief1": 15, "brief2": 15, "brief3": 15}, "videos": {
            "video1": {"analytics": {"minutes_watched_w_lag": 20, "scorable_proportion": 1.0}, "matching_brief_ids": ["brief1", "brief2", "brief3"], "decision_details": {"video_vet_result": True}}
        }}
    ]

    # Create a mock class instance for self parameter
    mock_self = MagicMock()

    # Patch get_briefs and reward functions
    with patch('bitcast.validator.reward.get_briefs', return_value=MOCK_TEST_BRIEFS) as mock_get_briefs, \
         patch('bitcast.validator.reward.reward', side_effect=lambda uid, briefs, response: mock_yt_stats.pop(0)) as mock_reward:
        
        # Call get_rewards
        result, yt_stats_list = get_rewards(mock_self, uids, responses)
        
        # Verify the result is a numpy array
        assert isinstance(result, np.ndarray)
        
        expected_result = np.array([0, 0.4, 0.6])
        
        # Check that the result matches the expected values (with some tolerance for floating point)
        np.testing.assert_allclose(result, expected_result, rtol=1e-5)
        
        # Verify that get_briefs was called
        mock_get_briefs.assert_called_once()
        
        # Verify that reward was called for each response
        assert mock_reward.call_count == 3
        
        # Verify that yt_stats_list is returned
        assert isinstance(yt_stats_list, list)
        assert len(yt_stats_list) == 3


def test_get_rewards_identical_responses():
    # Create 4 mock responses (including for uid 0)
    responses = [
        MagicMock(YT_access_token=None),  # for uid 0
        MagicMock(YT_access_token="token1"),
        MagicMock(YT_access_token="token2"),
        MagicMock(YT_access_token="token3")
    ]

    # Create mock UIDs (include uid 0)
    uids = [0, 1, 2, 3]

    # Mock yt_stats to be returned by reward function - all identical except for uid 0
    mock_yt_stats = [
        {"scores": {"brief1": 0, "brief2": 0, "brief3": 0}, "videos": {}},  # Scores for uid 0
        {"yt_account": {"channel_vet_result": True}, "scores": {"brief1": 5, "brief2": 10, "brief3": 15}, "videos": {
            "video1": {"analytics": {"minutes_watched_w_lag": 10, "scorable_proportion": 1.0}, "matching_brief_ids": ["brief1", "brief2", "brief3"], "decision_details": {"video_vet_result": True}}
        }},  # Scores for response 1
        {"yt_account": {"channel_vet_result": True}, "scores": {"brief1": 5, "brief2": 10, "brief3": 15}, "videos": {
            "video1": {"analytics": {"minutes_watched_w_lag": 10, "scorable_proportion": 1.0}, "matching_brief_ids": ["brief1", "brief2", "brief3"], "decision_details": {"video_vet_result": True}}
        }},  # Scores for response 2
        {"yt_account": {"channel_vet_result": True}, "scores": {"brief1": 5, "brief2": 10, "brief3": 15}, "videos": {
            "video1": {"analytics": {"minutes_watched_w_lag": 10, "scorable_proportion": 1.0}, "matching_brief_ids": ["brief1", "brief2", "brief3"], "decision_details": {"video_vet_result": True}}
        }}   # Scores for response 3
    ]

    # Create a mock class instance for self parameter
    mock_self = MagicMock()

    # Patch get_briefs and reward functions
    with patch('bitcast.validator.reward.get_briefs', return_value=MOCK_TEST_BRIEFS) as mock_get_briefs, \
         patch('bitcast.validator.reward.reward', side_effect=lambda uid, briefs, response: mock_yt_stats.pop(0)) as mock_reward:
        
        # Call get_rewards
        result, yt_stats_list = get_rewards(mock_self, uids, responses)
        
        expected_result = np.array([0.0, 1/3, 1/3, 1/3])
        
        # Check that the result matches the expected values (with some tolerance for floating point)
        np.testing.assert_allclose(result, expected_result, rtol=1e-5)
        
        # Verify that get_briefs was called
        mock_get_briefs.assert_called_once()
        
        # Verify that reward was called for each response
        assert mock_reward.call_count == 4
        
        # Verify that yt_stats_list is returned
        assert isinstance(yt_stats_list, list)
        assert len(yt_stats_list) == 4

def test_get_rewards_with_zeros():
    # Create 4 mock responses (including for uid 0)
    responses = [
        MagicMock(YT_access_token=None),  # for uid 0
        MagicMock(YT_access_token="token1"),
        MagicMock(YT_access_token="token2"),
        MagicMock(YT_access_token="token3")
    ]

    # Create mock UIDs (include uid 0)
    uids = [0, 1, 2, 3]

    # Mock yt_stats to be returned by reward function - each has a zero in one position, uid 0 all zeros
    mock_yt_stats = [
        {"scores": {"brief1": 0, "brief2": 0, "brief3": 0}, "videos": {}},  # Scores for uid 0
        {"yt_account": {"channel_vet_result": True}, "scores": {"brief1": 0, "brief2": 10, "brief3": 10}, "videos": {
            "video1": {"analytics": {"minutes_watched_w_lag": 10, "scorable_proportion": 1.0}, "matching_brief_ids": ["brief2", "brief3"], "decision_details": {"video_vet_result": True}}
        }},  # Scores for response 1
        {"yt_account": {"channel_vet_result": True}, "scores": {"brief1": 10, "brief2": 0, "brief3": 10}, "videos": {
            "video1": {"analytics": {"minutes_watched_w_lag": 10, "scorable_proportion": 1.0}, "matching_brief_ids": ["brief1", "brief3"], "decision_details": {"video_vet_result": True}}
        }},  # Scores for response 2
        {"yt_account": {"channel_vet_result": True}, "scores": {"brief1": 10, "brief2": 10, "brief3": 0}, "videos": {
            "video1": {"analytics": {"minutes_watched_w_lag": 10, "scorable_proportion": 1.0}, "matching_brief_ids": ["brief1", "brief2"], "decision_details": {"video_vet_result": True}}
        }}   # Scores for response 3
    ]

    # Create a mock class instance for self parameter
    mock_self = MagicMock()

    # Patch get_briefs and reward functions
    with patch('bitcast.validator.reward.get_briefs', return_value=MOCK_TEST_BRIEFS) as mock_get_briefs, \
         patch('bitcast.validator.reward.reward', side_effect=lambda uid, briefs, response: mock_yt_stats.pop(0)) as mock_reward:
        
        # Call get_rewards
        result, yt_stats_list = get_rewards(mock_self, uids, responses)
        
        expected_result = np.array([0.0, 1/3, 1/3, 1/3])
        
        # Check that the result matches the expected values (with some tolerance for floating point)
        np.testing.assert_allclose(result, expected_result, rtol=1e-5)
        
        # Verify that get_briefs was called
        mock_get_briefs.assert_called_once()
        
        # Verify that reward was called for each response
        assert mock_reward.call_count == 4
        
        # Verify that yt_stats_list is returned
        assert isinstance(yt_stats_list, list)
        assert len(yt_stats_list) == 4

def test_get_rewards_all_zeros_in_first_position():
    # Create 4 mock responses (including for uid 0)
    responses = [
        MagicMock(YT_access_token=None),  # for uid 0
        MagicMock(YT_access_token="token1"),
        MagicMock(YT_access_token="token2"),
        MagicMock(YT_access_token="token3")
    ]

    # Create mock UIDs (include uid 0)
    uids = [0, 1, 2, 3]

    # Mock yt_stats to be returned by reward function - all have zero in first position, uid 0 all zeros
    mock_yt_stats = [
        {"scores": {"brief1": 0, "brief2": 0, "brief3": 0}, "videos": {}},  # Scores for uid 0
        {"yt_account": {"channel_vet_result": True}, "scores": {"brief1": 0, "brief2": 10, "brief3": 10}, "videos": {
            "video1": {"analytics": {"minutes_watched_w_lag": 10, "scorable_proportion": 1.0}, "matching_brief_ids": ["brief2", "brief3"], "decision_details": {"video_vet_result": True}}
        }},  # Scores for response 1
        {"yt_account": {"channel_vet_result": True}, "scores": {"brief1": 0, "brief2": 10, "brief3": 10}, "videos": {
            "video1": {"analytics": {"minutes_watched_w_lag": 10, "scorable_proportion": 1.0}, "matching_brief_ids": ["brief2", "brief3"], "decision_details": {"video_vet_result": True}}
        }},  # Scores for response 2
        {"yt_account": {"channel_vet_result": True}, "scores": {"brief1": 0, "brief2": 10, "brief3": 10}, "videos": {
            "video1": {"analytics": {"minutes_watched_w_lag": 10, "scorable_proportion": 1.0}, "matching_brief_ids": ["brief2", "brief3"], "decision_details": {"video_vet_result": True}}
        }}   # Scores for response 3
    ]

    # Mock briefs to be returned by get_briefs (with max_burn=0)
    mock_briefs = [
        {"id": "brief1", "max_burn": 0.0, "burn_decay": 0.01},
        {"id": "brief2", "max_burn": 0.0, "burn_decay": 0.01},
        {"id": "brief3", "max_burn": 0.0, "burn_decay": 0.01}
    ]

    # Create a mock class instance for self parameter
    mock_self = MagicMock()

    # Patch get_briefs and reward functions
    with patch('bitcast.validator.reward.get_briefs', return_value=mock_briefs) as mock_get_briefs, \
         patch('bitcast.validator.reward.reward', side_effect=lambda uid, briefs, response: mock_yt_stats.pop(0)) as mock_reward:
        
        # Call get_rewards
        result, yt_stats_list = get_rewards(mock_self, uids, responses)
        
        # Verify the result is a numpy array
        assert isinstance(result, np.ndarray)
        
        # The expected result after normalization and summing
        # Each response has a total of 20 (0+10+10)
        # After normalization across miners: [0, 1/3, 1/3, 1/3]
        # After normalization across briefs: [1/3, 1/9, 1/9, 1/9]
        # Final sum for each: [1/3, 2/9, 2/9, 2/9]
        expected_result = np.array([1/3, 2/9, 2/9, 2/9])
        
        # Check that the result matches the expected values (with some tolerance for floating point)
        np.testing.assert_allclose(result, expected_result, rtol=1e-5)
        
        # Verify that get_briefs was called
        mock_get_briefs.assert_called_once()
        
        # Verify that reward was called for each response
        assert mock_reward.call_count == 4
        
        # Verify that yt_stats_list is returned
        assert isinstance(yt_stats_list, list)
        assert len(yt_stats_list) == 4
        

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
    assert normalize_across_miners(np.array([])).size == 0
    
    # Test with single row
    scores_matrix = np.array([[10, 30, 2]])
    normalized_scores = normalize_across_miners(scores_matrix)
    assert np.allclose(normalized_scores, [[1.0, 1.0, 1.0]])
    
    # Test with all zeros
    scores_matrix = np.array([[0, 0], [0, 0]])
    normalized_scores = normalize_across_miners(scores_matrix)
    assert np.allclose(normalized_scores, [[0, 0], [0, 0]])

def test_normalize_across_briefs():
    # Test with regular matrix and equal weights
    normalized_scores_matrix = [[0.4, 0.2, 0.4, 0.2], [0.6, 0.8, 0.6, 0.8]]
    briefs = [{"weight": 100}, {"weight": 100}, {"weight": 100}, {"weight": 100}]
    normalized_across_briefs = normalize_across_briefs(normalized_scores_matrix, briefs)
    assert np.allclose(normalized_across_briefs, [[0.1, 0.05, 0.1, 0.05], [0.15, 0.2, 0.15, 0.2]])

    # Test with empty matrix
    assert normalize_across_briefs(np.array([]), []).size == 0
    
    # Test with single brief
    normalized_scores_matrix = [[0.4], [0.6]]
    briefs = [{"weight": 100}]
    normalized_across_briefs = normalize_across_briefs(normalized_scores_matrix, briefs)
    assert np.allclose(normalized_across_briefs, [[0.4], [0.6]])

    # Test with different weights
    normalized_scores_matrix = [[0.4, 0.2], [0.6, 0.8]]
    briefs = [{"weight": 200}, {"weight": 100}]  # First brief has double weight
    normalized_across_briefs = normalize_across_briefs(normalized_scores_matrix, briefs)
    # Expected: First column gets 2/3 weight, second column gets 1/3 weight
    expected = np.array([[0.4 * 2/3, 0.2 * 1/3], [0.6 * 2/3, 0.8 * 1/3]])
    assert np.allclose(normalized_across_briefs, expected)

    # Test with missing weights (should default to 100)
    normalized_scores_matrix = [[0.4, 0.2], [0.6, 0.8]]
    briefs = [{"weight": 200}, {}]  # Second brief has no weight specified
    normalized_across_briefs = normalize_across_briefs(normalized_scores_matrix, briefs)
    # Expected: First column gets 2/3 weight, second column gets 1/3 weight (default 100)
    expected = np.array([[0.4 * 2/3, 0.2 * 1/3], [0.6 * 2/3, 0.8 * 1/3]])
    assert np.allclose(normalized_across_briefs, expected)

def test_normalise_scores():
    # Test with regular matrix
    scores_matrix = np.array([[0, 0, 0], [10, 30, 2], [90, 70, 2]])
    mock_yt_stats = [
        {"scores": {"brief1": 0, "brief2": 0, "brief3": 0}},
        {"yt_account": {"channel_vet_result": True}, "scores": {"brief1": 10, "brief2": 30, "brief3": 2}, "videos": {
            "video1": {"analytics": {"minutes_watched_w_lag": 10, "scorable_proportion": 1.0}, "matching_brief_ids": ["brief1", "brief2", "brief3"], "decision_details": {"video_vet_result": True}}
        }},
        {"yt_account": {"channel_vet_result": True}, "scores": {"brief1": 90, "brief2": 70, "brief3": 2}, "videos": {
            "video1": {"analytics": {"minutes_watched_w_lag": 20, "scorable_proportion": 1.0}, "matching_brief_ids": ["brief1", "brief2", "brief3"], "decision_details": {"video_vet_result": True}}
        }}
    ]
    
    final_scores = normalise_scores(scores_matrix, mock_yt_stats, MOCK_TEST_BRIEFS)
    # After normalize_across_miners: [[0.1, 0.3, 0.5], [0.9, 0.7, 0.5]]
    # After normalize_across_briefs: [[0.033, 0.1, 0.167], [0.3, 0.233, 0.167]]
    # After summing rows: [0.3, 0.7]
    assert np.allclose(final_scores, [0, 0.3, 0.7])
    
    # Test with empty matrix
    assert np.array(normalise_scores(np.array([]), [], MOCK_TEST_BRIEFS)).size == 0
    
    # Test with single row
    scores_matrix = np.array([[10, 30, 2]])
    mock_yt_stats = [{"yt_account": {"channel_vet_result": True}, "scores": {"brief1": 10, "brief2": 30, "brief3": 2}, "videos": {
        "video1": {"analytics": {"minutes_watched_w_lag": 10, "scorable_proportion": 1.0}, "matching_brief_ids": ["brief1", "brief2", "brief3"], "decision_details": {"video_vet_result": True}}
    }}]
    final_scores = normalise_scores(scores_matrix, mock_yt_stats, MOCK_TEST_BRIEFS)
    assert np.allclose(final_scores, [1.0])
    
    # Test with all zeros
    scores_matrix = np.array([[0, 0], [0, 0]])
    mock_yt_stats = [
        {"yt_account": {"channel_vet_result": True}, "scores": {"brief1": 0, "brief2": 0}, "videos": {
            "video1": {"analytics": {"minutes_watched_w_lag": 0, "scorable_proportion": 1.0}, "matching_brief_ids": ["brief1", "brief2"], "decision_details": {"video_vet_result": True}}
        }},
        {"yt_account": {"channel_vet_result": True}, "scores": {"brief1": 0, "brief2": 0}, "videos": {
            "video1": {"analytics": {"minutes_watched_w_lag": 0, "scorable_proportion": 1.0}, "matching_brief_ids": ["brief1", "brief2"], "decision_details": {"video_vet_result": True}}
        }}
    ]
    mock_briefs = [{"id": "brief1", "max_burn": 0.0, "burn_decay": 0.01},
                   {"id": "brief2", "max_burn": 0.0, "burn_decay": 0.01}]
    final_scores = normalise_scores(scores_matrix, mock_yt_stats, mock_briefs)
    print(f"FINAL SCORES {final_scores}")
    assert np.allclose(final_scores, [1.0, 0.0])

def test_get_rewards_with_brief_weights():
    # Create mock responses
    responses = [
        MagicMock(YT_access_token=None),  # for uid 0
        MagicMock(YT_access_token="token1"),
        MagicMock(YT_access_token="token2")
    ]

    # Create mock UIDs
    uids = [0, 1, 2]

    # Mock briefs with different weights
    mock_briefs = [
        {"id": "brief1", "max_burn": 0.0, "burn_decay": 0.01, "weight": 100},
        {"id": "brief2", "max_burn": 0.0, "burn_decay": 0.01, "weight": 200},
        {"id": "brief3", "max_burn": 0.0, "burn_decay": 0.01, "weight": 300}
    ]

    # Mock yt_stats with identical scores for each brief
    mock_yt_stats = [
        {"scores": {"brief1": 0, "brief2": 0, "brief3": 0}, "videos": {}},  # Scores for uid 0
        {"yt_account": {"channel_vet_result": True}, "scores": {"brief1": 10, "brief2": 10, "brief3": 10}, "videos": {
            "video1": {"analytics": {"minutes_watched_w_lag": 10, "scorable_proportion": 1.0}, "matching_brief_ids": ["brief1", "brief2", "brief3"], "decision_details": {"video_vet_result": True}}
        }},  # Scores for response 1
        {"yt_account": {"channel_vet_result": True}, "scores": {"brief1": 10, "brief2": 10, "brief3": 10}, "videos": {
            "video1": {"analytics": {"minutes_watched_w_lag": 10, "scorable_proportion": 1.0}, "matching_brief_ids": ["brief1", "brief2", "brief3"], "decision_details": {"video_vet_result": True}}
        }}   # Scores for response 2
    ]

    # Create a mock class instance for self parameter
    mock_self = MagicMock()

    # Patch get_briefs and reward functions
    with patch('bitcast.validator.reward.get_briefs', return_value=mock_briefs) as mock_get_briefs, \
         patch('bitcast.validator.reward.reward', side_effect=lambda uid, briefs, response: mock_yt_stats.pop(0)) as mock_reward:
        
        # Call get_rewards
        result, yt_stats_list = get_rewards(mock_self, uids, responses)
        
        # Verify the result is a numpy array
        assert isinstance(result, np.ndarray)
        
        # After applying weights:
        # brief1: 10 * 100 = 1000
        # brief2: 10 * 200 = 2000
        # brief3: 10 * 300 = 3000
        # After normalization across miners: [0, 0.5, 0.5] for each brief
        # After normalization across briefs: [0, 0.5/3, 0.5/3] for each brief
        # Final sum for each: [0, 0.5, 0.5]
        expected_result = np.array([0.0, 0.5, 0.5])
        
        # Check that the result matches the expected values (with some tolerance for floating point)
        np.testing.assert_allclose(result, expected_result, rtol=1e-5, atol=1e-10)
        
        # Verify that get_briefs was called
        mock_get_briefs.assert_called_once()
        
        # Verify that reward was called for each response
        assert mock_reward.call_count == 3
        
        # Verify that yt_stats_list is returned
        assert isinstance(yt_stats_list, list)
        assert len(yt_stats_list) == 3
