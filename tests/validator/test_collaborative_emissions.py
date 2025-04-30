import numpy as np
from unittest.mock import patch, MagicMock
from bitcast.validator.rewards_scaling import calculate_brief_emissions_scalar, scale_rewards

def test_calculate_brief_emissions_scalar():
    # Test case 1: Basic curve test with single brief
    yt_stats_list = [{
        "videos": {
            "video1": {
                "estimatedMinutesWatched": 100,
                "matching_brief_ids": ["brief1"]
            }
        }
    }]
    briefs = [{
        "id": "brief1",
        "max_burn": 0.5,  # 50% max burn
        "burn_decay": 0.01  # Slow decay
    }]
    
    result = calculate_brief_emissions_scalar(yt_stats_list, briefs)
    expected = 1 - 0.5 + 0.5 * (1 - np.exp(-0.01 * 100))
    assert np.isclose(result["brief1"], expected)

def test_calculate_brief_emissions_scalar_zero_minutes():
    # Test case 2: Zero minutes watched should return 0
    yt_stats_list = [{
        "videos": {
            "video1": {
                "estimatedMinutesWatched": 0,
                "matching_brief_ids": ["brief1"]
            }
        }
    }]
    briefs = [{
        "id": "brief1",
        "max_burn": 0.8,
        "burn_decay": 0.05
    }]
    
    result = calculate_brief_emissions_scalar(yt_stats_list, briefs)
    # When minutes watched is 0, scalar should be 0
    expected = 0.0
    assert np.isclose(result["brief1"], expected)

def test_calculate_brief_emissions_scalar_high_minutes():
    # Test case 3: Very high minutes (approaching asymptote)
    yt_stats_list = [{
        "videos": {
            "video1": {
                "estimatedMinutesWatched": 1000,
                "matching_brief_ids": ["brief1"]
            }
        }
    }]
    briefs = [{
        "id": "brief1",
        "max_burn": 0.3,
        "burn_decay": 0.1
    }]
    
    result = calculate_brief_emissions_scalar(yt_stats_list, briefs)
    # With very high x, e^(-decay*x) approaches 0, so formula approaches 1
    assert result["brief1"] > 0.999

def test_calculate_brief_emissions_scalar_multiple_briefs():
    # Test case 4: Multiple briefs with different parameters
    yt_stats_list = [{
        "videos": {
            "video1": {
                "estimatedMinutesWatched": 50,
                "matching_brief_ids": ["brief1", "brief2"]
            }
        }
    }]
    briefs = [
        {
            "id": "brief1",
            "max_burn": 0.4,
            "burn_decay": 0.02
        },
        {
            "id": "brief2",
            "max_burn": 0.6,
            "burn_decay": 0.03
        }
    ]
    
    result = calculate_brief_emissions_scalar(yt_stats_list, briefs)
    expected1 = 1 - 0.4 + 0.4 * (1 - np.exp(-0.02 * 50))
    expected2 = 1 - 0.6 + 0.6 * (1 - np.exp(-0.03 * 50))
    assert np.isclose(result["brief1"], expected1)
    assert np.isclose(result["brief2"], expected2)

def test_calculate_brief_emissions_scalar_multiple_videos():
    # Test case 5: Multiple videos contributing to same brief
    yt_stats_list = [{
        "videos": {
            "video1": {
                "estimatedMinutesWatched": 30,
                "matching_brief_ids": ["brief1"]
            },
            "video2": {
                "estimatedMinutesWatched": 20,
                "matching_brief_ids": ["brief1"]
            }
        }
    }]
    briefs = [{
        "id": "brief1",
        "max_burn": 0.7,
        "burn_decay": 0.04
    }]
    
    result = calculate_brief_emissions_scalar(yt_stats_list, briefs)
    # Total minutes should be 50
    expected = 1 - 0.7 + 0.7 * (1 - np.exp(-0.04 * 50))
    assert np.isclose(result["brief1"], expected)

def test_calculate_brief_emissions_scalar_invalid_stats():
    # Test case 6: Handle invalid stats gracefully
    yt_stats_list = [
        {"invalid_key": "value"},  # Missing videos key
        None,  # None value
        {"videos": None},  # None videos
        {"videos": "invalid"}  # Invalid videos type
    ]
    briefs = [{
        "id": "brief1",
        "max_burn": 0.5,
        "burn_decay": 0.01
    }]
    
    result = calculate_brief_emissions_scalar(yt_stats_list, briefs)
    # Should return 0 when no valid stats
    expected = 0.0
    assert np.isclose(result["brief1"], expected)

def test_calculate_brief_emissions_scalar_burn_decay_zero():
    # Test case: burn_decay is 0
    yt_stats_list = [{
        "videos": {
            "video1": {
                "estimatedMinutesWatched": 100,
                "matching_brief_ids": ["brief1"]
            }
        }
    }]
    briefs = [{
        "id": "brief1",
        "max_burn": 0.6,
        "burn_decay": 0.0
    }]
    result = calculate_brief_emissions_scalar(yt_stats_list, briefs)
    expected = 1 - 0.6  # Should follow normal formula
    assert np.isclose(result["brief1"], expected)

def test_calculate_brief_emissions_scalar_max_burn_zero():
    # Test case: max_burn is 0, should follow normal formula
    yt_stats_list = [{
        "videos": {
            "video1": {
                "estimatedMinutesWatched": 100,
                "matching_brief_ids": ["brief1"]
            }
        }
    }]
    briefs = [{
        "id": "brief1",
        "max_burn": 0.0,
        "burn_decay": 0.05
    }]
    result = calculate_brief_emissions_scalar(yt_stats_list, briefs)
    expected = 1.0
    assert np.isclose(result["brief1"], expected)

def test_scale_rewards_basic():
    # Test basic functionality with valid inputs
    matrix = np.array([
        [0.0, 0.0],
        [0.6, 0.7],
        [0.4, 0.3]
    ])
    
    yt_stats_list = [{
        "videos": {
            "video1": {
                "estimatedMinutesWatched": 100,
                "matching_brief_ids": ["brief1"]
            },
            "video2": {
                "estimatedMinutesWatched": 50,
                "matching_brief_ids": ["brief2"]
            }
        }
    }]
    
    briefs = [
        {
            "id": "brief1",
            "max_burn": 0.5,
            "burn_decay": 0.01
        },
        {
            "id": "brief2",
            "max_burn": 0.3,
            "burn_decay": 0.02
        }
    ]
    
    result = scale_rewards(matrix, yt_stats_list, briefs)
    
    # Check properties
    assert np.allclose(np.sum(result, axis=0), 1.0)  # Columns should sum to 1
    assert np.all(result >= 0)  # All values should be non-negative

def test_scale_rewards_invalid_sum():
    # Test with matrix that doesn't sum to 1
    matrix = np.array([
        [0.0, 0.0],
        [0.8, 0.9],
        [0.4, 0.3]
    ])
    
    yt_stats_list = [{
        "videos": {
            "video1": {
                "estimatedMinutesWatched": 100,
                "matching_brief_ids": ["brief1", "brief2"]
            }
        }
    }]
    
    briefs = [
        {"id": "brief1", "max_burn": 0.5, "burn_decay": 0.01},
        {"id": "brief2", "max_burn": 0.3, "burn_decay": 0.02}
    ]
    
    with patch('bittensor.logging.warning') as mock_warning:
        result = scale_rewards(matrix, yt_stats_list, briefs)
        mock_warning.assert_called_with(f"Input matrix sum {np.sum(matrix)} is not close to 1")
    
    # Result should still have valid properties
    assert np.allclose(np.sum(result, axis=0), 1.0)

def test_scale_rewards_nonzero_first_row():
    # Test with non-zero first row
    matrix = np.array([
        [0.1, 0.1],
        [0.5, 0.6],
        [0.4, 0.3]
    ])
    
    yt_stats_list = [{
        "videos": {
            "video1": {
                "estimatedMinutesWatched": 100,
                "matching_brief_ids": ["brief1", "brief2"]
            }
        }
    }]
    
    briefs = [
        {"id": "brief1", "max_burn": 0.5, "burn_decay": 0.01},
        {"id": "brief2", "max_burn": 0.3, "burn_decay": 0.02}
    ]
    
    with patch('bittensor.logging.warning') as mock_warning:
        result = scale_rewards(matrix, yt_stats_list, briefs)
        mock_warning.assert_called_with("First row of matrix contains non-zero values")
    
    # Result should still have valid properties
    assert np.allclose(np.sum(result, axis=0), 1.0)

def test_scale_rewards_zero_scalars():
    # Test with zero minutes watched (should result in zero scalars)
    matrix = np.array([
        [0.0, 0.0],
        [0.6, 0.7],
        [0.4, 0.3]
    ])
    
    yt_stats_list = [{
        "videos": {
            "video1": {
                "estimatedMinutesWatched": 0,
                "matching_brief_ids": ["brief1", "brief2"]
            }
        }
    }]
    
    briefs = [
        {"id": "brief1", "max_burn": 0.5, "burn_decay": 0.01},
        {"id": "brief2", "max_burn": 0.3, "burn_decay": 0.02}
    ]
    
    result = scale_rewards(matrix, yt_stats_list, briefs)
    
    # With zero scalars, first row should be 1 and rest 0
    assert np.allclose(result[0, :], 1.0)
    assert np.allclose(result[1:, :], 0.0)
    assert np.allclose(np.sum(result, axis=0), 1.0)

def test_scale_rewards_max_burn_zero():
    # Test with max_burn=0, which should result in no changes to the matrix
    matrix = np.array([
        [0.0, 0.0],
        [0.6, 0.7],
        [0.4, 0.3]
    ])
    
    yt_stats_list = [{
        "videos": {
            "video1": {
                "estimatedMinutesWatched": 100,
                "matching_brief_ids": ["brief1", "brief2"]
            }
        }
    }]
    
    briefs = [
        {"id": "brief1", "max_burn": 0.0, "burn_decay": 0.01},
        {"id": "brief2", "max_burn": 0.0, "burn_decay": 0.02}
    ]
    
    result = scale_rewards(matrix, yt_stats_list, briefs)
    
    # With max_burn=0, the matrix should remain unchanged
    assert np.allclose(result, matrix)
    assert np.allclose(np.sum(result, axis=0), 1.0)

def test_scale_rewards_burn_decay_zero():
    # Test with burn_decay=0, which should result in first row being max_burn
    matrix = np.array([
        [0.0, 0.0],
        [0.6, 0.7],
        [0.4, 0.3]
    ])
    
    yt_stats_list = [{
        "videos": {
            "video1": {
                "estimatedMinutesWatched": 100,
                "matching_brief_ids": ["brief1", "brief2"]
            }
        }
    }]
    
    briefs = [
        {"id": "brief1", "max_burn": 0.3, "burn_decay": 0.0},
        {"id": "brief2", "max_burn": 0.4, "burn_decay": 0.0}
    ]
    
    result = scale_rewards(matrix, yt_stats_list, briefs)
    
    # First row should be max_burn for each column
    assert np.allclose(result[0, 0], 0.3)  # max_burn for brief1
    assert np.allclose(result[0, 1], 0.4)  # max_burn for brief2
    
    # Remaining rows should be scaled proportionally to fill the remaining space
    remaining_scale_col0 = 0.7  # 1 - max_burn for brief1
    remaining_scale_col1 = 0.6  # 1 - max_burn for brief2
    
    original_sum_col0 = matrix[1:, 0].sum()
    original_sum_col1 = matrix[1:, 1].sum()
    
    # Check that remaining rows are scaled correctly
    assert np.allclose(result[1:, 0], matrix[1:, 0] * remaining_scale_col0 / original_sum_col0)
    assert np.allclose(result[1:, 1], matrix[1:, 1] * remaining_scale_col1 / original_sum_col1)
    
    # Total should still sum to 1
    assert np.allclose(np.sum(result, axis=0), 1.0)

def test_scale_rewards_all_zeros():
    # Test with a matrix containing only zeros
    matrix = np.array([
        [0.0, 0.0],
        [0.0, 0.0],
        [0.0, 0.0]
    ])
    
    yt_stats_list = [{
        "videos": {
            "video1": {
                "estimatedMinutesWatched": 100,
                "matching_brief_ids": ["brief1", "brief2"]
            }
        }
    }]
    
    briefs = [
        {"id": "brief1", "max_burn": 0.3, "burn_decay": 0.01},
        {"id": "brief2", "max_burn": 0.4, "burn_decay": 0.02}
    ]
    
    with patch('bittensor.logging.warning') as mock_warning:
        result = scale_rewards(matrix, yt_stats_list, briefs)
        mock_warning.assert_called_with("Input matrix sum 0.0 is not close to 1")
    
    # In case of all zeros:
    # 1. First row should get equal distribution (total matrix sum = 1)
    # 2. All other rows should remain zero
    
    # Check first row has equal distribution
    assert np.allclose(result[0, 0], 0.5)  # Equal split between columns
    assert np.allclose(result[0, 1], 0.5)  # Equal split between columns
    
    # Check all other rows remain zero
    assert np.allclose(result[1:, :], 0.0)
    
    # Total matrix should sum to 1
    assert np.allclose(np.sum(result), 1.0) 