import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from bitcast.validator.reward import get_rewards

@pytest.fixture
def mock_briefs():
    return [
        {"id": "brief1", "max_burn": 0.5, "burn_decay": 0.1},
        {"id": "brief2", "max_burn": 0.3, "burn_decay": 0.2}
    ]

@pytest.fixture
def mock_responses():
    return [
        {"YT_access_token": "token1"},
        {"YT_access_token": "token2"},
        {"YT_access_token": "token3"}
    ]

@pytest.fixture
def mock_yt_stats():
    return {
        "scores": {
            "brief1": 0.8,
            "brief2": 0.6
        }
    }

def test_get_rewards_normal_case(mock_briefs, mock_responses):
    # Arrange
    uids = np.array([0, 1, 2])
    
    with patch('bitcast.validator.reward.get_briefs', return_value=mock_briefs), \
         patch('bitcast.validator.reward.reward') as mock_reward, \
         patch('bitcast.validator.reward.youtube_utils.reset_scored_videos'):
        
        # Set up mock reward function to return different scores for different UIDs
        def mock_reward_func(uid, briefs, response):
            if uid == 0:
                return {"scores": {"brief1": 0.0, "brief2": 0.0}}
            else:
                return {"scores": {"brief1": 0.8, "brief2": 0.6}}
        
        mock_reward.side_effect = mock_reward_func
        
        # Act
        rewards, stats = get_rewards(None, uids, mock_responses)
        
        # Assert
        assert len(rewards) == 3
        assert rewards[0] > 0  # Burn UID should get some rewards
        assert all(r >= 0 for r in rewards)  # All rewards should be non-negative
        assert np.isclose(sum(rewards), 1.0)  # Total rewards should sum to 1
        assert len(stats) == 3  # Should have stats for each UID

def test_get_rewards_empty_briefs():
    # Arrange
    uids = np.array([0, 1, 2])
    responses = ["response1", "response2", "response3"]
    
    with patch('bitcast.validator.reward.get_briefs', return_value=[]), \
         patch('bitcast.validator.reward.youtube_utils.reset_scored_videos'):
        
        # Act
        rewards, stats = get_rewards(None, uids, responses)
        
        # Assert
        assert len(rewards) == 3
        assert rewards[0] == 1.0  # Burn UID should get all rewards
        assert all(rewards[1:] == 0.0)  # Other UIDs should get no rewards
        assert len(stats) == 3
        assert all(stat == {"scores": {}} for stat in stats)

def test_get_rewards_all_zero_scores(mock_briefs, mock_responses):
    # Arrange
    uids = np.array([0, 1, 2])
    
    with patch('bitcast.validator.reward.get_briefs', return_value=mock_briefs), \
         patch('bitcast.validator.reward.reward') as mock_reward, \
         patch('bitcast.validator.reward.youtube_utils.reset_scored_videos'):
        
        # Set up mock reward function to return zero scores
        mock_reward.return_value = {"scores": {"brief1": 0.0, "brief2": 0.0}}
        
        # Act
        rewards, stats = get_rewards(None, uids, mock_responses)
        
        # Assert
        assert len(rewards) == 3
        assert rewards[0] == 1.0  # Burn UID should get all rewards
        assert all(rewards[1:] == 0.0)  # Other UIDs should get no rewards
        assert len(stats) == 3

def test_get_rewards_no_burn_uid(mock_briefs, mock_responses):
    # Arrange
    uids = np.array([1, 2])  # No UID 0
    responses = mock_responses[1:]  # Corresponding responses
    
    with patch('bitcast.validator.reward.get_briefs', return_value=mock_briefs), \
         patch('bitcast.validator.reward.reward') as mock_reward, \
         patch('bitcast.validator.reward.youtube_utils.reset_scored_videos'):
        
        mock_reward.return_value = {"scores": {"brief1": 0.5, "brief2": 0.5}}
        
        # Act
        rewards, stats = get_rewards(None, uids, responses)
        
        # Assert
        assert len(rewards) == 2
        assert all(r >= 0 for r in rewards)  # All rewards should be non-negative
        assert np.isclose(sum(rewards), 1.0)  # Total rewards should sum to 1
        assert len(stats) == 2
