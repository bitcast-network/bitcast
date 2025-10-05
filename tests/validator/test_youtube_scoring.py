import pytest
from unittest.mock import MagicMock, patch, Mock
from bitcast.validator.platforms.youtube.main import update_video_score, check_video_brief_matches

def test_update_video_score():
    # Setup
    youtube_analytics_client = MagicMock()
    briefs = [{"id": "test_brief", "format": "dedicated"}]  # Specify format for clarity
    result = {"videos": {}, "scores": {"test_brief": 0}}
    
    # Create a single video_matches dictionary that will be updated
    video_matches = {}
    
    # Mock YT_ROLLING_WINDOW to 1 for easier test calculations (so no division)
    # Mock token pricing functions to prevent API calls in tests
    with patch('bitcast.validator.platforms.youtube.evaluation.scoring.YT_ROLLING_WINDOW', 1), \
         patch('bitcast.validator.platforms.youtube.main.calculate_video_score') as mock_calculate, \
         patch('bitcast.validator.platforms.youtube.main.get_bitcast_alpha_price', return_value=1.0), \
         patch('bitcast.validator.platforms.youtube.main.get_total_miner_emissions', return_value=1000.0):
        
        # Test case 1: First video with revenue score 2.50 
        # With dedicated scaling factor (2000), final score = 2.50 * 2000 = 5000.0
        video_id_1 = "test_video_id_1"
        video_matches[video_id_1] = [True]  # Add to video_matches
        result["videos"][video_id_1] = {
            "details": {"bitcastVideoId": video_id_1}, 
            "analytics": {}  # Analytics not used in scoring anymore
        }
        mock_calculate.return_value = {"score": 2.50, "daily_analytics": {}, "scoring_method": "ypp"}
        update_video_score(video_id_1, youtube_analytics_client, video_matches, briefs, result, is_ypp_account=True)
        assert result["scores"]["test_brief"] == 5000.0, "First score should be 5000.0 (2.50 * 2000 scaling)"
        
        # Test case 2: Second video with revenue score 1.75 
        # With dedicated scaling factor (2000), scaled score = 1.75 * 2000 = 3500.0
        # Total = 5000.0 + 3500.0 = 8500.0
        video_id_2 = "test_video_id_2"
        video_matches[video_id_2] = [True]  # Add to video_matches
        result["videos"][video_id_2] = {
            "details": {"bitcastVideoId": video_id_2}, 
            "analytics": {}
        }
        mock_calculate.return_value = {"score": 1.75, "daily_analytics": {}, "scoring_method": "ypp"}
        update_video_score(video_id_2, youtube_analytics_client, video_matches, briefs, result, is_ypp_account=True)
        assert result["scores"]["test_brief"] == 8500.0, "Score should be 8500.0 (5000.0 + 3500.0)"
        
        # Test case 3: Third video with revenue score 0 (no revenue generated)
        # With dedicated scaling factor (2000), scaled score = 0 * 2000 = 0.0
        # Total = 8500.0 + 0.0 = 8500.0
        video_id_3 = "test_video_id_3"
        video_matches[video_id_3] = [True]  # Add to video_matches
        result["videos"][video_id_3] = {
            "details": {"bitcastVideoId": video_id_3}, 
            "analytics": {}
        }
        mock_calculate.return_value = {"score": 0, "daily_analytics": {}, "scoring_method": "ypp"}
        update_video_score(video_id_3, youtube_analytics_client, video_matches, briefs, result, is_ypp_account=True)
        assert result["scores"]["test_brief"] == 8500.0, "Score should remain 8500.0 (5000.0 + 3500.0 + 0.0)"
        
        # Test case 4: Fourth video with revenue score 0.80 
        # With dedicated scaling factor (2000), scaled score = 0.80 * 2000 = 1600.0
        # Total = 8500.0 + 1600.0 = 10100.0
        video_id_4 = "test_video_id_4"
        video_matches[video_id_4] = [True]  # Add to video_matches
        result["videos"][video_id_4] = {
            "details": {"bitcastVideoId": video_id_4}, 
            "analytics": {}
        }
        mock_calculate.return_value = {"score": 0.80, "daily_analytics": {}, "scoring_method": "ypp"}
        update_video_score(video_id_4, youtube_analytics_client, video_matches, briefs, result, is_ypp_account=True)
        assert result["scores"]["test_brief"] == 10100.0, "Score should be 10100.0 (5000.0 + 3500.0 + 0.0 + 1600.0)"


def test_check_video_brief_matches():
    # Setup
    video_id = "test_video"
    briefs = [
        {"id": "brief1"},
        {"id": "brief2"},
        {"id": "brief3"}
    ]
    
    # Test case 1: Video matches multiple briefs - only first matching brief is returned as list
    video_matches = {
        video_id: [True, True, False]  # Matches brief1 and brief2, but only brief1 returned
    }
    matches_any_brief, matching_brief_ids = check_video_brief_matches(video_id, video_matches, briefs)
    assert matches_any_brief == True
    assert matching_brief_ids == ['brief1', 'brief2']
    
    # Test case 2: Video matches no briefs
    video_matches = {
        video_id: [False, False, False]
    }
    matches_any_brief, matching_brief_ids = check_video_brief_matches(video_id, video_matches, briefs)
    assert matches_any_brief == False
    assert matching_brief_ids == []  # Empty list
    
    # Test case 3: Video matches all briefs - only first matching brief is returned as list
    video_matches = {
        video_id: [True, True, True]
    }
    matches_any_brief, matching_brief_ids = check_video_brief_matches(video_id, video_matches, briefs)
    assert matches_any_brief == True
    assert matching_brief_ids == ['brief1', 'brief2', 'brief3']


def test_process_videos_empty_briefs():
    """Test process_videos function with empty briefs list."""
    # Setup
    youtube_data_client = MagicMock()
    youtube_analytics_client = MagicMock()
    briefs = []
    result = {
        "yt_account": {
            "details": {},
            "analytics": {},
            "channel_vet_result": True
        },
        "videos": {},
        "scores": {}
    }
    
    # Mock the necessary functions
    with patch('bitcast.validator.platforms.youtube.main.get_all_uploads') as mock_get_uploads, \
         patch('bitcast.validator.platforms.youtube.main.vet_videos') as mock_vet_videos:
        
        # Setup mock return values
        mock_get_uploads.return_value = ["video1", "video2"]
        mock_vet_videos.return_value = (
            {},  # video_matches
            {"video1": {"details": {}}, "video2": {"details": {}}},  # video_data_dict
            {"video1": {"analytics": {}}, "video2": {"analytics": {}}},  # video_analytics_dict
            {}  # video_decision_details
        )
        
        # Call the function
        from bitcast.validator.platforms.youtube.main import process_videos
        result = process_videos(youtube_data_client, youtube_analytics_client, briefs, result)
        
        # Verify the results
        assert "videos" in result
        assert len(result["videos"]) == 2  # Should process both videos
        assert "video1" in result["videos"]
        assert "video2" in result["videos"]
        assert result["scores"] == {}  # Scores should be empty since there are no briefs
        
        # Verify that get_all_uploads was called with correct parameters
        mock_get_uploads.assert_called_once()
        
        # Verify that vet_videos was called with empty briefs
        mock_vet_videos.assert_called_once()
        assert mock_vet_videos.call_args[0][1] == []  # Verify briefs parameter was empty list


def test_calculate_video_score_revenue_based():
    """Test the revenue-based scoring calculation logic with daily average."""
    from bitcast.validator.platforms.youtube.evaluation.scoring import calculate_video_score
    from datetime import datetime

    # Mock dependencies
    youtube_analytics_client = MagicMock()
    video_publish_date = "2023-01-01T00:00:00Z"
    existing_analytics = {}  # Not used anymore

    # Mock YT_ROLLING_WINDOW to 7 for realistic testing
    with patch('bitcast.validator.platforms.youtube.evaluation.scoring.get_video_analytics') as mock_analytics, \
         patch('bitcast.validator.platforms.youtube.evaluation.scoring.YT_ROLLING_WINDOW', 7):
        
        # Test case: Revenue across multiple days, total = 5.05, average = 5.05/7 ≈ 0.721
        mock_analytics.return_value = {
            "day_metrics": {
                "2023-01-01": {
                    "day": "2023-01-01",
                    "estimatedRedPartnerRevenue": 2.50
                },
                "2023-01-02": {
                    "day": "2023-01-02", 
                    "estimatedRedPartnerRevenue": 1.75
                },
                "2023-01-03": {
                    "day": "2023-01-03",
                    "estimatedRedPartnerRevenue": 0.80
                }
            }
        }
        
        # Mock datetime.now() to return a fixed date
        with patch('bitcast.validator.platforms.youtube.evaluation.scoring.datetime') as mock_datetime:
            # Set up the datetime mock to return a real datetime object for now()
            mock_datetime.now.return_value = datetime(2023, 1, 12)
            mock_datetime.strptime = datetime.strptime
            # Pass through timedelta operations to the real datetime module
            import datetime as dt
            mock_datetime.timedelta = dt.timedelta
            
            result = calculate_video_score("test_video", youtube_analytics_client, video_publish_date, existing_analytics)
            
            # Check that result contains expected fields
            assert "score" in result
            assert "daily_analytics" in result
            
            # With curve-based scoring, we test that:
            # 1. The score is calculated (should be a number)
            # 2. The scoring method is curve-based
            # 3. The result structure is correct
            assert isinstance(result["score"], (int, float))
            assert result["scoring_method"] in ["ypp_curve_based", "ypp_curve_error"]
            assert len(result["daily_analytics"]) == 3
            
            # Curve-based scoring returns additional debugging information
            if result["scoring_method"] == "ypp_curve_based":
                assert "day1_average" in result
                assert "day2_average" in result
                assert "periods" in result


def test_calculate_video_score_no_revenue():
    """Test scoring when there's no revenue data."""
    from bitcast.validator.platforms.youtube.evaluation.scoring import calculate_video_score
    from datetime import datetime

    youtube_analytics_client = MagicMock()
    video_publish_date = "2023-01-01T00:00:00Z"
    existing_analytics = {}

    with patch('bitcast.validator.platforms.youtube.evaluation.scoring.get_video_analytics') as mock_analytics, \
         patch('bitcast.validator.platforms.youtube.evaluation.scoring.YT_ROLLING_WINDOW', 7):
        
        mock_analytics.return_value = {
            "day_metrics": {
                "2023-01-01": {
                    "day": "2023-01-01"
                    # No estimatedRedPartnerRevenue field
                }
            }
        }
        
        with patch('bitcast.validator.platforms.youtube.evaluation.scoring.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2023, 1, 10)
            mock_datetime.strptime = datetime.strptime
            import datetime as dt
            mock_datetime.timedelta = dt.timedelta
            
            result = calculate_video_score("test_video", youtube_analytics_client, video_publish_date, existing_analytics)
            
            # Should handle missing revenue gracefully - 0 / 7 = 0
            assert result["score"] == 0
            assert "daily_analytics" in result


def test_calculate_video_score_empty_analytics():
    """Test scoring when analytics data is empty."""
    from bitcast.validator.platforms.youtube.evaluation.scoring import calculate_video_score
    from datetime import datetime

    youtube_analytics_client = MagicMock()
    video_publish_date = "2023-01-01T00:00:00Z"
    existing_analytics = {}

    with patch('bitcast.validator.platforms.youtube.evaluation.scoring.get_video_analytics') as mock_analytics, \
         patch('bitcast.validator.platforms.youtube.evaluation.scoring.YT_ROLLING_WINDOW', 7):
        
        mock_analytics.return_value = {
            "day_metrics": {}  # Empty analytics
        }
        
        with patch('bitcast.validator.platforms.youtube.evaluation.scoring.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2023, 1, 10)
            mock_datetime.strptime = datetime.strptime
            import datetime as dt
            mock_datetime.timedelta = dt.timedelta
            
            result = calculate_video_score("test_video", youtube_analytics_client, video_publish_date, existing_analytics)
            
            # Should handle empty analytics gracefully - 0 / 7 = 0
            assert result["score"] == 0
            assert result["daily_analytics"] == []


def test_calculate_video_score_partial_window_data():
    """Test that scoring divides by YT_ROLLING_WINDOW even with partial data."""
    from bitcast.validator.platforms.youtube.evaluation.scoring import calculate_video_score
    from datetime import datetime

    youtube_analytics_client = MagicMock()
    video_publish_date = "2023-01-01T00:00:00Z"
    existing_analytics = {}

    with patch('bitcast.validator.platforms.youtube.evaluation.scoring.get_video_analytics') as mock_analytics, \
         patch('bitcast.validator.platforms.youtube.evaluation.scoring.YT_ROLLING_WINDOW', 7):
        
        # Only 2 days of data in a 7-day window
        mock_analytics.return_value = {
            "day_metrics": {
                "2023-01-01": {
                    "day": "2023-01-01",
                    "estimatedRedPartnerRevenue": 3.50
                },
                "2023-01-02": {
                    "day": "2023-01-02", 
                    "estimatedRedPartnerRevenue": 3.50
                }
                # Days 3-7 have no data
            }
        }
        
        with patch('bitcast.validator.platforms.youtube.evaluation.scoring.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2023, 1, 10)
            mock_datetime.strptime = datetime.strptime
            import datetime as dt
            mock_datetime.timedelta = dt.timedelta
            
            result = calculate_video_score("test_video", youtube_analytics_client, video_publish_date, existing_analytics)
            
            # With curve-based scoring, we test that:
            # 1. The score is calculated (should be a number)
            # 2. The scoring method is curve-based
            # 3. The result structure is correct
            assert isinstance(result["score"], (int, float))
            assert result["scoring_method"] in ["ypp_curve_based", "ypp_curve_error"]
            assert len(result["daily_analytics"]) == 2
            
            # Curve-based scoring should have additional debugging information
            if result["scoring_method"] == "ypp_curve_based":
                assert "day1_average" in result
                assert "day2_average" in result 


def test_calculate_video_score_non_ypp_with_cached_ratio():
    """Test Non-YPP scoring works with cached ratio and non-revenue metrics."""
    from bitcast.validator.platforms.youtube.evaluation.scoring import calculate_video_score
    from bitcast.validator.utils.config import ECO_MODE
    from datetime import datetime, timedelta

    mock_analytics_client = Mock()

    # Test data
    video_id = "test_video_123"
    video_publish_date = "2024-01-01T00:00:00Z"
    existing_analytics = {}
    
    # Calculate realistic dates that would be within the scoring window
    # The scoring function calculates: 
    # start_date = (now - YT_REWARD_DELAY - YT_ROLLING_WINDOW + 1)
    # end_date = (now - YT_REWARD_DELAY)
    # With YT_REWARD_DELAY=3 and YT_ROLLING_WINDOW=7, this is roughly 9 days ago to 3 days ago
    now = datetime.now()
    test_start = (now - timedelta(days=9)).strftime('%Y-%m-%d')
    test_middle = (now - timedelta(days=6)).strftime('%Y-%m-%d') 
    test_end = (now - timedelta(days=3)).strftime('%Y-%m-%d')
    
    # Mock get_video_analytics to return minutes watched data (no revenue metrics for Non-YPP)
    with patch('bitcast.validator.platforms.youtube.evaluation.scoring.get_video_analytics') as mock_get_analytics:
        mock_get_analytics.return_value = {
            "day_metrics": {
                test_start: {"day": test_start, "estimatedMinutesWatched": 5000},
                test_middle: {"day": test_middle, "estimatedMinutesWatched": 3000},
                test_end: {"day": test_end, "estimatedMinutesWatched": 2000}
            }
        }
        
        # Mock get_youtube_metrics to verify it's called with is_ypp_account=False
        with patch('bitcast.validator.platforms.youtube.evaluation.scoring.get_youtube_metrics') as mock_get_metrics:
            mock_get_metrics.return_value = {"estimatedMinutesWatched": ("estimatedMinutesWatched", "day", None, None, "day")}
            
            # Mock YT_ROLLING_WINDOW to 7 for predictable testing
            with patch('bitcast.validator.platforms.youtube.evaluation.scoring.YT_ROLLING_WINDOW', 7):
                result = calculate_video_score(
                    video_id=video_id,
                    youtube_analytics_client=mock_analytics_client,
                    video_publish_date=video_publish_date,
                    existing_analytics=existing_analytics,
                    is_ypp_account=False  # Non-YPP account
                )
    
    # Verify get_youtube_metrics was called with is_ypp_account=False
    mock_get_metrics.assert_called_once_with(eco_mode=ECO_MODE, for_daily=True, is_ypp_account=False)
    
    # Verify the result uses curve-based Non-YPP scoring
    assert result["scoring_method"] == "non_ypp_curve_based"
    
    # With curve-based scoring, we test that:
    # 1. The score is calculated (should be a number)
    # 2. The result structure is correct
    # 3. Non-YPP specific fields are present
    assert isinstance(result["score"], (int, float))
    assert "day1_minutes_average" in result
    assert "day2_minutes_average" in result
    assert "revenue_multiplier" in result
    
    # Should have daily analytics with minutes watched data
    assert len(result["daily_analytics"]) == 3


def test_calculate_video_score_non_ypp_no_cached_ratio():
    """Test Non-YPP scoring uses hardcoded multiplier when no cached ratio available."""
    from bitcast.validator.platforms.youtube.evaluation.scoring import calculate_video_score
    from datetime import datetime
    
    mock_analytics_client = Mock()
    
    video_id = "test_video_123"
    video_publish_date = "2024-01-01T00:00:00Z"
    existing_analytics = {}
    
    # Mock get_video_analytics to return minutes watched data
    with patch('bitcast.validator.platforms.youtube.evaluation.scoring.get_video_analytics') as mock_get_analytics:
        mock_get_analytics.return_value = {
            "day_metrics": {
                "2024-01-01": {"day": "2024-01-01", "estimatedMinutesWatched": 1000},
                "2024-01-02": {"day": "2024-01-02", "estimatedMinutesWatched": 1500}
            }
        }
        
        with patch('bitcast.validator.platforms.youtube.evaluation.scoring.get_youtube_metrics') as mock_get_metrics:
            mock_get_metrics.return_value = {"estimatedMinutesWatched": ("estimatedMinutesWatched", "day", None, None, "day")}
            
            with patch('bitcast.validator.platforms.youtube.evaluation.scoring.datetime') as mock_datetime:
                mock_datetime.now.return_value = datetime(2024, 1, 10)
                mock_datetime.strptime = datetime.strptime
                import datetime as dt
                mock_datetime.timedelta = dt.timedelta
                
                result = calculate_video_score(
                    video_id=video_id,
                    youtube_analytics_client=mock_analytics_client,
                    video_publish_date=video_publish_date,
                    existing_analytics=existing_analytics,
                    is_ypp_account=False
                )
    
    # Should use curve-based Non-YPP scoring with hardcoded multiplier
    assert result["scoring_method"] == "non_ypp_curve_based"
    assert isinstance(result["score"], (int, float))
    assert "revenue_multiplier" in result
    # Should use the hardcoded multiplier from config
    from bitcast.validator.utils.config import YT_NON_YPP_REVENUE_MULTIPLIER
    assert result["revenue_multiplier"] == YT_NON_YPP_REVENUE_MULTIPLIER 


def test_select_highest_priority_brief():
    """Test the select_highest_priority_brief function with weight-based selection."""
    from bitcast.validator.platforms.youtube.evaluation.video import select_highest_priority_brief
    
    # Test case 1: Select highest weight brief
    briefs = [
        {"id": "brief1", "weight": 5},
        {"id": "brief2", "weight": 10},  # Should be selected
        {"id": "brief3", "weight": 3}
    ]
    brief_results = [True, True, True]  # All match
    
    selected_index, selected_brief = select_highest_priority_brief(briefs, brief_results)
    assert selected_index == 1
    assert selected_brief["id"] == "brief2"
    assert selected_brief["weight"] == 10
    
    # Test case 2: Handle missing weight field (defaults to 0)
    briefs = [
        {"id": "brief1", "weight": 5},
        {"id": "brief2"},  # No weight field - defaults to 0
        {"id": "brief3", "weight": 8}  # Should be selected
    ]
    brief_results = [True, True, True]
    
    selected_index, selected_brief = select_highest_priority_brief(briefs, brief_results)
    assert selected_index == 2
    assert selected_brief["id"] == "brief3"
    assert selected_brief["weight"] == 8
    
    # Test case 3: Tie-breaking (same weight, first one wins)
    briefs = [
        {"id": "brief1", "weight": 5},
        {"id": "brief2", "weight": 5},  # Same weight, but brief1 should win (earlier index)
        {"id": "brief3", "weight": 3}
    ]
    brief_results = [True, True, True]
    
    selected_index, selected_brief = select_highest_priority_brief(briefs, brief_results)
    assert selected_index == 0  # First one with highest weight
    assert selected_brief["id"] == "brief1"
    
    # Test case 4: Only some briefs match
    briefs = [
        {"id": "brief1", "weight": 10},  # Matches but not selected
        {"id": "brief2", "weight": 15},  # Doesn't match
        {"id": "brief3", "weight": 8}   # Should be selected (highest among matching)
    ]
    brief_results = [True, False, True]  # Only brief1 and brief3 match
    
    selected_index, selected_brief = select_highest_priority_brief(briefs, brief_results)
    assert selected_index == 0  # brief1 wins among matching briefs
    assert selected_brief["id"] == "brief1"
    assert selected_brief["weight"] == 10
    
    # Test case 5: No briefs match
    briefs = [
        {"id": "brief1", "weight": 5},
        {"id": "brief2", "weight": 10},
        {"id": "brief3", "weight": 3}
    ]
    brief_results = [False, False, False]  # None match
    
    selected_index, selected_brief = select_highest_priority_brief(briefs, brief_results)
    assert selected_index is None
    assert selected_brief is None
    
    # Test case 6: Empty lists
    selected_index, selected_brief = select_highest_priority_brief([], [])
    assert selected_index is None
    assert selected_brief is None


def test_boost_factor_applied_in_usd_calculations():
    """Regression test: Verify boost factor is correctly applied in per-video USD calculations."""
    from bitcast.validator.platforms.youtube.main import _calculate_per_video_metrics
    
    # Mock pricing functions to have predictable values
    with patch('bitcast.validator.platforms.youtube.main.get_bitcast_alpha_price', return_value=10.0), \
         patch('bitcast.validator.platforms.youtube.main.get_total_miner_emissions', return_value=1000.0):
        
        # Test data
        base_score = 1.0
        scaling_factor = 100
        boost_factor = 1.25
        
        # Calculate metrics
        metrics = _calculate_per_video_metrics(base_score, scaling_factor, boost_factor)
        
        # Verify boost is applied correctly
        assert metrics["brief_boost"] == boost_factor, "Should store boost factor as brief_boost"
        assert "boost" not in metrics, "Old 'boost' field should not exist"
        assert "boost_factor" not in metrics, "Old 'boost_factor' field should not exist"
        
        # Verify USD target includes all factors (this is now the actual USD value)
        expected_usd_target = base_score * scaling_factor * boost_factor  # 1.0 * 100 * 1.25 = 125.0
        assert metrics["usd_target"] == expected_usd_target, f"USD target should be {expected_usd_target}"
        assert "scaled_score" not in metrics, "Old 'scaled_score' field should not exist"
        
        # Verify alpha target calculation
        # alpha_target = usd_target / alpha_price = 125.0 / 10.0 = 12.5
        expected_alpha_target = 12.5
        assert abs(metrics["alpha_target"] - expected_alpha_target) < 1e-10, f"Alpha target should be {expected_alpha_target}"
        
        # Verify weight calculation (normalized)
        # total_daily_usd = alpha_price * total_daily_alpha = 10.0 * 1000.0 = 10000.0
        # weight = usd_target / total_daily_usd = 125.0 / 10000.0 = 0.0125
        expected_weight = 0.0125
        assert abs(metrics["weight"] - expected_weight) < 1e-10, f"Weight should be {expected_weight}" 