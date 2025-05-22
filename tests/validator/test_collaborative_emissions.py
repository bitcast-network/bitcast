import numpy as np
from unittest.mock import patch, MagicMock
from bitcast.validator.rewards_scaling import calculate_brief_emissions_scalar, scale_rewards

def test_calculate_brief_emissions_scalar():
    # Test case 1: Basic curve test with single brief
    yt_stats_list = [{
        "yt_account": {
            "channel_vet_result": True
        },
        "videos": {
            "video1": {
                "analytics": {
                    "minutes_watched_w_lag": 100,
                    "scorable_proportion": 1.0
                },
                "matching_brief_ids": ["brief1"],
                "decision_details": {"video_vet_result": True}
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
    print(f"result: {result}")
    print(f"expected: {expected}")
    assert np.isclose(result["brief1"], expected)

def test_calculate_brief_emissions_scalar_zero_minutes():
    # Test case 2: Zero minutes watched should return 0
    yt_stats_list = [{
        "yt_account": {
            "channel_vet_result": True
        },
        "videos": {
            "video1": {
                "analytics": {
                    "minutes_watched_w_lag": 0,
                    "scorable_proportion": 1.0
                },
                "matching_brief_ids": ["brief1"],
                "decision_details": {"video_vet_result": True}
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
        "yt_account": {
            "channel_vet_result": True
        },
        "videos": {
            "video1": {
                "analytics": {
                    "minutes_watched_w_lag": 1000,
                    "scorable_proportion": 1.0
                },
                "matching_brief_ids": ["brief1"],
                "decision_details": {"video_vet_result": True}
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
        "yt_account": {
            "channel_vet_result": True
        },
        "videos": {
            "video1": {
                "analytics": {
                    "minutes_watched_w_lag": 50,
                    "scorable_proportion": 1.0
                },
                "matching_brief_ids": ["brief1", "brief2"],
                "decision_details": {"video_vet_result": True}
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
        "yt_account": {
            "channel_vet_result": True
        },
        "videos": {
            "video1": {
                "analytics": {
                    "minutes_watched_w_lag": 30,
                    "scorable_proportion": 1.0
                },
                "matching_brief_ids": ["brief1"],
                "decision_details": {"video_vet_result": True}
            },
            "video2": {
                "analytics": {
                    "minutes_watched_w_lag": 20,
                    "scorable_proportion": 1.0
                },
                "matching_brief_ids": ["brief1"],
                "decision_details": {"video_vet_result": True}
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
        {"videos": "invalid"},  # Invalid videos type
        {"yt_account": {"channel_vet_result": False}},  # Non-vetted channel
        {"yt_account": {"channel_vet_result": True}, "videos": {}}  # Vetted but no videos
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
        "yt_account": {
            "channel_vet_result": True
        },
        "videos": {
            "video1": {
                "analytics": {
                    "minutes_watched_w_lag": 100,
                    "scorable_proportion": 1.0
                },
                "matching_brief_ids": ["brief1"],
                "decision_details": {"video_vet_result": True}
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
        "yt_account": {
            "channel_vet_result": True
        },
        "videos": {
            "video1": {
                "analytics": {
                    "minutes_watched_w_lag": 100,
                    "scorable_proportion": 1.0
                },
                "matching_brief_ids": ["brief1"],
                "decision_details": {"video_vet_result": True}
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
    matrix = [
        [np.float64(0.0), np.float64(0.0)],
        [np.float64(0.3), np.float64(0.35)],
        [np.float64(0.2), np.float64(0.15)]
    ]
    
    yt_stats_list = [{
        "yt_account": {
            "channel_vet_result": True
        },
        "videos": {
            "video1": {
                "analytics": {
                    "minutes_watched_w_lag": 100,
                    "scorable_proportion": 1.0
                },
                "matching_brief_ids": ["brief1"],
                "decision_details": {"video_vet_result": True}
            },
            "video2": {
                "minutes_watched_w_lag": 50,
                "analytics": {
                    "scorable_proportion": 1.0
                },
                "matching_brief_ids": ["brief2"],
                "decision_details": {"video_vet_result": True}
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
    result_np = np.array(result)
    
    # Check properties
    assert np.isclose(np.sum(result_np), 1.0)  # Entire matrix should sum to 1
    assert np.all(result_np >= 0)  # All values should be non-negative

def test_scale_rewards_invalid_sum():
    # Test with matrix that doesn't sum to 1
    matrix = [
        [np.float64(0.0), np.float64(0.0)],
        [np.float64(0.8), np.float64(0.9)],
        [np.float64(0.4), np.float64(0.3)]
    ]
    
    yt_stats_list = [{
        "yt_account": {
            "channel_vet_result": True
        },
        "videos": {
            "video1": {
                "analytics": {
                    "minutes_watched_w_lag": 100,
                    "scorable_proportion": 1.0
                },
                "matching_brief_ids": ["brief1", "brief2"],
                "decision_details": {"video_vet_result": True}
            }
        }
    }]
    
    briefs = [
        {"id": "brief1", "max_burn": 0.5, "burn_decay": 0.01},
        {"id": "brief2", "max_burn": 0.3, "burn_decay": 0.02}
    ]
    
    with patch('bittensor.logging.warning') as mock_warning:
        result = scale_rewards(matrix, yt_stats_list, briefs)
        mock_warning.assert_called_with(f"Input matrix sum {sum(sum(row) for row in matrix)} is not close to 1")
    
    # Result should still have valid properties
    result_np = np.array(result)
    assert np.isclose(np.sum(result_np), 1.0)  # Entire matrix should sum to 1

def test_scale_rewards_nonzero_first_row():
    # Test with non-zero first row
    matrix = [
        [np.float64(0.1), np.float64(0.1)],
        [np.float64(0.5), np.float64(0.6)],
        [np.float64(0.4), np.float64(0.3)]
    ]
    
    yt_stats_list = [{
        "yt_account": {
            "channel_vet_result": True
        },
        "videos": {
            "video1": {
                "analytics": {
                    "minutes_watched_w_lag": 100,
                    "scorable_proportion": 1.0
                },
                "matching_brief_ids": ["brief1", "brief2"],
                "decision_details": {"video_vet_result": True}
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
    result_np = np.array(result)
    assert np.isclose(np.sum(result_np), 1.0)

def test_scale_rewards_zero_scalars():
    # Test with zero minutes watched (should result in zero scalars)
    matrix = [
        [np.float64(0.0), np.float64(0.0)],
        [np.float64(0.6), np.float64(0.7)],
        [np.float64(0.4), np.float64(0.3)]
    ]
    
    yt_stats_list = [{
        "yt_account": {
            "channel_vet_result": True
        },
        "videos": {
            "video1": {
                "analytics": {
                    "scorable_proportion": 1.0,
                    "minutes_watched_w_lag": 0
                },
                "matching_brief_ids": ["brief1", "brief2"],
                "decision_details": {"video_vet_result": True}
            }
        }
    }]
    
    briefs = [
        {"id": "brief1", "max_burn": 0.5, "burn_decay": 0.01},
        {"id": "brief2", "max_burn": 0.3, "burn_decay": 0.02}
    ]
    
    result = scale_rewards(matrix, yt_stats_list, briefs)
    result_np = np.array(result)
    
    # With zero scalars, first row should sum to 1 and rest 0
    assert np.isclose(np.sum(result_np[0, :]), 1.0)
    assert np.allclose(result_np[1:, :], 0.0)
    assert np.isclose(np.sum(result_np), 1.0)

def test_scale_rewards_max_burn_zero():
    # Test with max_burn=0, which should result in no changes to the matrix
    matrix = [
        [np.float64(0.0), np.float64(0.0)],
        [np.float64(0.3), np.float64(0.35)],
        [np.float64(0.2), np.float64(0.15)]
    ]
    
    yt_stats_list = [{
        "yt_account": {
            "channel_vet_result": True
        },
        "videos": {
            "video1": {
                "analytics": {
                    "minutes_watched_w_lag": 100,
                    "scorable_proportion": 1.0
                },
                "matching_brief_ids": ["brief1", "brief2"],
                "decision_details": {"video_vet_result": True}
            }
        }
    }]
    
    briefs = [
        {"id": "brief1", "max_burn": 0.0, "burn_decay": 0.01},
        {"id": "brief2", "max_burn": 0.0, "burn_decay": 0.02}
    ]
    
    result = scale_rewards(matrix, yt_stats_list, briefs)
    result_np = np.array(result)
    
    # With max_burn=0, the matrix should remain unchanged
    assert np.allclose(result_np, matrix)
    assert np.allclose(np.sum(result_np), 1.0)

def test_scale_rewards_burn_decay_zero():
    # Test with burn_decay=0, which should result in first row being max_burn
    matrix = [
        [np.float64(0.0), np.float64(0.0)],
        [np.float64(0.3), np.float64(0.35)],
        [np.float64(0.2), np.float64(0.15)]
    ]
    
    yt_stats_list = [{
        "yt_account": {
            "channel_vet_result": True
        },
        "videos": {
            "video1": {
                "analytics": {
                    "minutes_watched_w_lag": 100,
                    "scorable_proportion": 1.0
                },
                "matching_brief_ids": ["brief1", "brief2"],
                "decision_details": {"video_vet_result": True}
            }
        }
    }]
    
    briefs = [
        {"id": "brief1", "max_burn": 0.3, "burn_decay": 0.0},
        {"id": "brief2", "max_burn": 0.4, "burn_decay": 0.0}
    ]
    
    result = scale_rewards(matrix, yt_stats_list, briefs)
    result_np = np.array(result)
    
    # First row should be max_burn for each column
    assert np.allclose(result_np[0, 0], 0.15)  # max_burn for brief1
    assert np.allclose(result_np[0, 1], 0.2)  # max_burn for brief2
    
    # Total should still sum to 1
    assert np.allclose(np.sum(result_np), 1.0)

def test_scale_rewards_all_zeros():
    # Test with a matrix containing only zeros
    matrix = [
        [np.float64(0.0), np.float64(0.0)],
        [np.float64(0.0), np.float64(0.0)],
        [np.float64(0.0), np.float64(0.0)]
    ]
    
    yt_stats_list = [{
        "yt_account": {
            "channel_vet_result": True
        },
        "videos": {
            "video1": {
                "analytics": {
                    "minutes_watched_w_lag": 100,
                    "scorable_proportion": 1.0
                },
                "matching_brief_ids": ["brief1", "brief2"],
                "decision_details": {"video_vet_result": True}
            }
        }
    }]
    
    briefs = [
        {"id": "brief1", "max_burn": 0.3, "burn_decay": 0.01},
        {"id": "brief2", "max_burn": 0.4, "burn_decay": 0.02}
    ]
    
    with patch('bittensor.logging.warning') as mock_warning:
        result = scale_rewards(matrix, yt_stats_list, briefs)
        mock_warning.assert_called_with(f"Input matrix sum {sum(sum(row) for row in matrix)} is not close to 1")
    
    result_np = np.array(result)
    
    # In case of all zeros:
    # 1. First row should get equal distribution
    # 2. All other rows should remain zero
    assert np.allclose(result_np[0, :], 0.5)  # Equal split between columns
    assert np.allclose(result_np[1:, :], 0.0)
    assert np.allclose(np.sum(result_np), 1.0)

def test_calculate_brief_emissions_scalar_partial_scorable():
    # Test case: Partial scorable_proportion
    yt_stats_list = [{
        "yt_account": {
            "channel_vet_result": True
        },
        "videos": {
            "video1": {
                "analytics": {
                    "minutes_watched_w_lag": 100,
                    "scorable_proportion": 0.5  # Only 50% is scorable
                },
                "matching_brief_ids": ["brief1"],
                "decision_details": {"video_vet_result": True}
            }
        }
    }]
    briefs = [{
        "id": "brief1",
        "max_burn": 0.4,
        "burn_decay": 0.02
    }]
    
    result = calculate_brief_emissions_scalar(yt_stats_list, briefs)
    
    # With 50% scorable, we should only count 50 minutes
    expected = 1 - 0.4 + 0.4 * (1 - np.exp(-0.02 * 50))
    assert np.isclose(result["brief1"], expected)

def test_calculate_brief_emissions_scalar_mixed_scorable():
    # Test case: Multiple videos with different scorable_proportion values
    yt_stats_list = [{
        "yt_account": {
            "channel_vet_result": True
        },
        "videos": {
            "video1": {
                "analytics": {
                    "minutes_watched_w_lag": 60,
                    "scorable_proportion": 0.75  # 75% scorable
                },
                "matching_brief_ids": ["brief1"],
                "decision_details": {"video_vet_result": True}
            },
            "video2": {
                "analytics": {
                    "minutes_watched_w_lag": 80,
                    "scorable_proportion": 0.25  # 25% scorable
                },
                "matching_brief_ids": ["brief1"],
                "decision_details": {"video_vet_result": True}
            }
        }
    }]
    briefs = [{
        "id": "brief1",
        "max_burn": 0.6,
        "burn_decay": 0.03
    }]
    
    result = calculate_brief_emissions_scalar(yt_stats_list, briefs)
    
    # Expected minutes: (60 * 0.75) + (80 * 0.25) = 45 + 20 = 65
    expected = 1 - 0.6 + 0.6 * (1 - np.exp(-0.03 * 65))
    assert np.isclose(result["brief1"], expected)
