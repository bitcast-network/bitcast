import pytest
from unittest.mock import MagicMock, patch, Mock
from bitcast.validator.platforms.youtube.main import update_video_score, check_video_brief_matches

def test_update_video_score():
    # Setup
    youtube_analytics_client = MagicMock()
    briefs = [{"id": "test_brief"}]
    result = {"videos": {}, "scores": {"test_brief": 0}}
    
    # Create a single video_matches dictionary that will be updated
    video_matches = {}
    
    # Mock YT_ROLLING_WINDOW to 1 for easier test calculations (so no division)
    with patch('bitcast.validator.platforms.youtube.evaluation.scoring.YT_ROLLING_WINDOW', 1), \
         patch('bitcast.validator.platforms.youtube.main.calculate_video_score') as mock_calculate:
        
        # Test case 1: First video with revenue score 2.50 (daily average over 1 day = 2.50)
        video_id_1 = "test_video_id_1"
        video_matches[video_id_1] = [True]  # Add to video_matches
        result["videos"][video_id_1] = {
            "details": {"bitcastVideoId": video_id_1}, 
            "analytics": {}  # Analytics not used in scoring anymore
        }
        mock_calculate.return_value = {"score": 2.50, "daily_analytics": {}, "scoring_method": "ypp"}
        update_video_score(video_id_1, youtube_analytics_client, video_matches, briefs, result, is_ypp_account=True, cached_ratio=None)
        assert result["scores"]["test_brief"] == 2.50, "First score should be 2.50"
        
        # Test case 2: Second video with revenue score 1.75 (daily average over 1 day = 1.75)
        video_id_2 = "test_video_id_2"
        video_matches[video_id_2] = [True]  # Add to video_matches
        result["videos"][video_id_2] = {
            "details": {"bitcastVideoId": video_id_2}, 
            "analytics": {}
        }
        mock_calculate.return_value = {"score": 1.75, "daily_analytics": {}, "scoring_method": "ypp"}
        update_video_score(video_id_2, youtube_analytics_client, video_matches, briefs, result, is_ypp_account=True, cached_ratio=None)
        assert result["scores"]["test_brief"] == 4.25, "Score should be 4.25 (2.50 + 1.75)"
        
        # Test case 3: Third video with revenue score 0 (no revenue generated)
        video_id_3 = "test_video_id_3"
        video_matches[video_id_3] = [True]  # Add to video_matches
        result["videos"][video_id_3] = {
            "details": {"bitcastVideoId": video_id_3}, 
            "analytics": {}
        }
        mock_calculate.return_value = {"score": 0, "daily_analytics": {}, "scoring_method": "ypp"}
        update_video_score(video_id_3, youtube_analytics_client, video_matches, briefs, result, is_ypp_account=True, cached_ratio=None)
        assert result["scores"]["test_brief"] == 4.25, "Score should remain 4.25 (2.50 + 1.75 + 0)"
        
        # Test case 4: Fourth video with revenue score 0.80 (daily average over 1 day = 0.80)
        video_id_4 = "test_video_id_4"
        video_matches[video_id_4] = [True]  # Add to video_matches
        result["videos"][video_id_4] = {
            "details": {"bitcastVideoId": video_id_4}, 
            "analytics": {}
        }
        mock_calculate.return_value = {"score": 0.80, "daily_analytics": {}, "scoring_method": "ypp"}
        update_video_score(video_id_4, youtube_analytics_client, video_matches, briefs, result, is_ypp_account=True, cached_ratio=None)
        assert result["scores"]["test_brief"] == 5.05, "Score should be 5.05 (2.50 + 1.75 + 0 + 0.80)"


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
            
            # With today = 2023-01-12:
            # start_date = 2023-01-12 - 9 days = 2023-01-03  
            # end_date = 2023-01-12 - 3 days = 2023-01-09
            # Only 2023-01-03 falls in window, so score should be 0.80 / 7 ≈ 0.114
            expected_score = 0.80 / 7
            assert abs(result["score"] - expected_score) < 0.001  # Allow for floating point precision
            assert len(result["daily_analytics"]) == 3


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
            
            # With today = 2023-01-10:
            # start_date = 2023-01-10 - 9 days = 2023-01-01  
            # end_date = 2023-01-10 - 3 days = 2023-01-07
            # Both 2023-01-01 and 2023-01-02 fall in window: (3.50 + 3.50) / 7 = 1.0
            assert result["score"] == 1.0
            assert len(result["daily_analytics"]) == 2 


def test_calculate_video_score_non_ypp_with_cached_ratio():
    """Test Non-YPP scoring works with cached ratio and non-revenue metrics."""
    from bitcast.validator.platforms.youtube.evaluation.scoring import calculate_video_score
    from datetime import datetime, timedelta
    
    mock_analytics_client = Mock()
    
    # Test data
    video_id = "test_video_123"
    video_publish_date = "2024-01-01T00:00:00Z"
    existing_analytics = {}
    cached_ratio = 0.001  # $0.001 per view
    
    # Calculate realistic dates that would be within the scoring window
    # The scoring function calculates: 
    # start_date = (now - YT_REWARD_DELAY - YT_ROLLING_WINDOW + 1)
    # end_date = (now - YT_REWARD_DELAY)
    # With YT_REWARD_DELAY=3 and YT_ROLLING_WINDOW=7, this is roughly 9 days ago to 3 days ago
    now = datetime.now()
    test_start = (now - timedelta(days=9)).strftime('%Y-%m-%d')
    test_middle = (now - timedelta(days=6)).strftime('%Y-%m-%d') 
    test_end = (now - timedelta(days=3)).strftime('%Y-%m-%d')
    
    # Mock get_video_analytics to return views data (no revenue metrics for Non-YPP)
    with patch('bitcast.validator.platforms.youtube.evaluation.scoring.get_video_analytics') as mock_get_analytics:
        mock_get_analytics.return_value = {
            "day_metrics": {
                test_start: {"day": test_start, "views": 5000},
                test_middle: {"day": test_middle, "views": 3000},
                test_end: {"day": test_end, "views": 2000}
            }
        }
        
        # Mock get_youtube_metrics to verify it's called with is_ypp_account=False
        with patch('bitcast.validator.platforms.youtube.evaluation.scoring.get_youtube_metrics') as mock_get_metrics:
            mock_get_metrics.return_value = {"views": ("views", "day", None, None, "day")}
            
            # Mock YT_ROLLING_WINDOW to 7 for predictable testing
            with patch('bitcast.validator.platforms.youtube.evaluation.scoring.YT_ROLLING_WINDOW', 7):
                result = calculate_video_score(
                    video_id=video_id,
                    youtube_analytics_client=mock_analytics_client,
                    video_publish_date=video_publish_date,
                    existing_analytics=existing_analytics,
                    is_ypp_account=False,  # Non-YPP account
                    cached_ratio=cached_ratio
                )
    
    # Verify get_youtube_metrics was called with is_ypp_account=False
    mock_get_metrics.assert_called_once_with(eco_mode=True, for_daily=True, is_ypp_account=False)
    
    # Verify the result uses predicted scoring
    assert result["scoring_method"] == "non_ypp_predicted"
    
    # Expected calculation: 10,000 total views * 0.001 ratio = $10 predicted revenue
    # Score = predicted_revenue / YT_ROLLING_WINDOW (7 days) = 10 / 7 ≈ 1.429
    expected_score = (10000 * cached_ratio) / 7  # Total views: 5000+3000+2000=10000
    assert abs(result["score"] - expected_score) < 0.001
    
    # Should have daily analytics with views data
    assert len(result["daily_analytics"]) == 3


def test_calculate_video_score_non_ypp_no_cached_ratio():
    """Test Non-YPP scoring falls back to standard dual scoring when no cached ratio available."""
    from bitcast.validator.platforms.youtube.evaluation.scoring import calculate_video_score
    
    mock_analytics_client = Mock()
    
    video_id = "test_video_123"
    video_publish_date = "2024-01-01T00:00:00Z"
    existing_analytics = {}
    cached_ratio = None  # No cached ratio
    
    # Mock get_video_analytics to return views data
    with patch('bitcast.validator.platforms.youtube.evaluation.scoring.get_video_analytics') as mock_get_analytics:
        mock_get_analytics.return_value = {
            "day_metrics": {
                "2024-01-01": {"day": "2024-01-01", "views": 1000}
            }
        }
        
        with patch('bitcast.validator.platforms.youtube.evaluation.scoring.get_youtube_metrics') as mock_get_metrics:
            mock_get_metrics.return_value = {"views": ("views", "day", None, None, "day")}
            
            with patch('bitcast.validator.platforms.youtube.evaluation.scoring.calculate_dual_score') as mock_dual_score:
                mock_dual_score.return_value = {
                    "score": 0.0,
                    "daily_analytics": [],
                    "scoring_method": "non_ypp_fallback"
                }
                
                result = calculate_video_score(
                    video_id=video_id,
                    youtube_analytics_client=mock_analytics_client,
                    video_publish_date=video_publish_date,
                    existing_analytics=existing_analytics,
                    is_ypp_account=False,
                    cached_ratio=cached_ratio  # None
                )
    
    # Should use standard dual scoring path
    assert result["scoring_method"] == "non_ypp_fallback" 


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