import pytest
from unittest.mock import MagicMock, patch
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
        mock_calculate.return_value = {"score": 2.50, "daily_analytics": {}}
        update_video_score(video_id_1, youtube_analytics_client, video_matches, briefs, result)
        assert result["scores"]["test_brief"] == 2.50, "First score should be 2.50"
        
        # Test case 2: Second video with revenue score 1.75 (daily average over 1 day = 1.75)
        video_id_2 = "test_video_id_2"
        video_matches[video_id_2] = [True]  # Add to video_matches
        result["videos"][video_id_2] = {
            "details": {"bitcastVideoId": video_id_2}, 
            "analytics": {}
        }
        mock_calculate.return_value = {"score": 1.75, "daily_analytics": {}}
        update_video_score(video_id_2, youtube_analytics_client, video_matches, briefs, result)
        assert result["scores"]["test_brief"] == 4.25, "Score should be 4.25 (2.50 + 1.75)"
        
        # Test case 3: Third video with revenue score 0 (no revenue generated)
        video_id_3 = "test_video_id_3"
        video_matches[video_id_3] = [True]  # Add to video_matches
        result["videos"][video_id_3] = {
            "details": {"bitcastVideoId": video_id_3}, 
            "analytics": {}
        }
        mock_calculate.return_value = {"score": 0, "daily_analytics": {}}
        update_video_score(video_id_3, youtube_analytics_client, video_matches, briefs, result)
        assert result["scores"]["test_brief"] == 4.25, "Score should remain 4.25 (2.50 + 1.75 + 0)"
        
        # Test case 4: Fourth video with revenue score 0.80 (daily average over 1 day = 0.80)
        video_id_4 = "test_video_id_4"
        video_matches[video_id_4] = [True]  # Add to video_matches
        result["videos"][video_id_4] = {
            "details": {"bitcastVideoId": video_id_4}, 
            "analytics": {}
        }
        mock_calculate.return_value = {"score": 0.80, "daily_analytics": {}}
        update_video_score(video_id_4, youtube_analytics_client, video_matches, briefs, result)
        assert result["scores"]["test_brief"] == 5.05, "Score should be 5.05 (2.50 + 1.75 + 0 + 0.80)"


def test_check_video_brief_matches():
    # Setup
    video_id = "test_video"
    briefs = [
        {"id": "brief1"},
        {"id": "brief2"},
        {"id": "brief3"}
    ]
    
    # Test case 1: Video matches multiple briefs
    video_matches = {
        video_id: [True, True, False]  # Matches brief1 and brief2
    }
    matches_any_brief, matching_brief_ids = check_video_brief_matches(video_id, video_matches, briefs)
    assert matches_any_brief == True
    assert matching_brief_ids == ["brief1", "brief2"]
    
    # Test case 2: Video matches no briefs
    video_matches = {
        video_id: [False, False, False]
    }
    matches_any_brief, matching_brief_ids = check_video_brief_matches(video_id, video_matches, briefs)
    assert matches_any_brief == False
    assert matching_brief_ids == []
    
    # Test case 3: Video matches all briefs
    video_matches = {
        video_id: [True, True, True]
    }
    matches_any_brief, matching_brief_ids = check_video_brief_matches(video_id, video_matches, briefs)
    assert matches_any_brief == True
    assert matching_brief_ids == ["brief1", "brief2", "brief3"]


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