import numpy as np
from unittest.mock import patch, MagicMock
from bitcast.validator.reward import calculate_brief_emissions_scalar

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
    # Test case 2: Zero minutes watched
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
    # When x=0, formula reduces to (1-max_burn)
    expected = 0.2  # 1 - 0.8
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
    # Should return minimum value when no valid stats
    expected = 1 - 0.5  # (1-max_burn) when x=0
    assert np.isclose(result["brief1"], expected)

def test_calculate_brief_emissions_scalar_burn_decay_zero():
    # Test case: burn_decay is 0, should always return (1 - max_burn)
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
    expected = 1 - 0.6  # Should ignore minutes watched
    assert np.isclose(result["brief1"], expected)

def test_calculate_brief_emissions_scalar_max_burn_zero():
    # Test case: max_burn is 0, should always return 1
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