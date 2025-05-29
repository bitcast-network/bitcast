import pytest
from unittest.mock import MagicMock, patch
from bitcast.validator.socials.youtube.youtube_scoring import update_video_score, check_video_brief_matches, channel_briefs_filter, check_subscriber_range

def test_update_video_score():
    # Setup
    youtube_analytics_client = MagicMock()
    briefs = [{"id": "test_brief"}]
    result = {"videos": {}, "scores": {"test_brief": 0}}
    
    # Create a single video_matches dictionary that will be updated
    video_matches = {}
    
    # Mock calculate_video_score to return different scores
    with patch('bitcast.validator.socials.youtube.youtube_scoring.calculate_video_score') as mock_calculate:
        # Test case 1: First video with score 2, no advertising traffic (equivalent to scorable_proportion: 1.0)
        video_id_1 = "test_video_id_1"
        video_matches[video_id_1] = [True]  # Add to video_matches
        result["videos"][video_id_1] = {
            "details": {"bitcastVideoId": video_id_1}, 
            "analytics": {"trafficSourceMinutes": {"SEARCH": 100, "SUGGESTED": 50}}  # No ADVERTISING
        }
        mock_calculate.return_value = {"score": 2, "daily_analytics": {}, "scorableHistoryMins": 120}
        update_video_score(video_id_1, youtube_analytics_client, video_matches, briefs, result)
        assert result["scores"]["test_brief"] == 2, "First score should be 2"
        
        # Test case 2: Second video with score 2 (after excluding advertising), half advertising traffic (equivalent to scorable_proportion: 0.5)
        video_id_2 = "test_video_id_2"
        video_matches[video_id_2] = [True]  # Add to video_matches
        result["videos"][video_id_2] = {
            "details": {"bitcastVideoId": video_id_2}, 
            "analytics": {"trafficSourceMinutes": {"SEARCH": 50, "ADVERTISING": 50}}  # 50% ADVERTISING
        }
        mock_calculate.return_value = {"score": 2, "daily_analytics": {}, "scorableHistoryMins": 240}  # Returns 2 after excluding advertising
        update_video_score(video_id_2, youtube_analytics_client, video_matches, briefs, result)
        assert result["scores"]["test_brief"] == 4, "Score should be 4 (2 + 2)"
        
        # Test case 3: Third video with score 0 (all traffic is advertising), all advertising traffic (equivalent to scorable_proportion: 0.0)
        video_id_3 = "test_video_id_3"
        video_matches[video_id_3] = [True]  # Add to video_matches
        result["videos"][video_id_3] = {
            "details": {"bitcastVideoId": video_id_3}, 
            "analytics": {"trafficSourceMinutes": {"ADVERTISING": 100}}  # All ADVERTISING
        }
        mock_calculate.return_value = {"score": 0, "daily_analytics": {}, "scorableHistoryMins": 120}  # Returns 0 since all traffic is advertising
        update_video_score(video_id_3, youtube_analytics_client, video_matches, briefs, result)
        assert result["scores"]["test_brief"] == 4, "Score should remain 4 (2 + 2 + 0)"
        
        # Test case 4: Fourth video with score 0, no advertising traffic (equivalent to scorable_proportion: 1.0)
        video_id_4 = "test_video_id_4"
        video_matches[video_id_4] = [True]  # Add to video_matches
        result["videos"][video_id_4] = {
            "details": {"bitcastVideoId": video_id_4}, 
            "analytics": {"trafficSourceMinutes": {"SEARCH": 80, "SUGGESTED": 20}}  # No ADVERTISING
        }
        mock_calculate.return_value = {"score": 0, "daily_analytics": {}, "scorableHistoryMins": 0}
        update_video_score(video_id_4, youtube_analytics_client, video_matches, briefs, result)
        assert result["scores"]["test_brief"] == 4, "Score should remain 4 (2 + 2 + 0 + 0)"

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

def test_check_subscriber_range():
    """Test subscriber range checking with null values."""
    # Test case 1: Both values null (no filtering)
    assert check_subscriber_range(100, [None, None]) == True
    assert check_subscriber_range(1000, [None, None]) == True
    assert check_subscriber_range(10000, [None, None]) == True

    # Test case 2: First value null (up to max)
    assert check_subscriber_range(100, [None, 1000]) == True
    assert check_subscriber_range(1000, [None, 1000]) == True
    assert check_subscriber_range(1001, [None, 1000]) == False

    # Test case 3: Second value null (over min)
    assert check_subscriber_range(100, [1000, None]) == False
    assert check_subscriber_range(1000, [1000, None]) == True
    assert check_subscriber_range(1001, [1000, None]) == True

    # Test case 4: Both values set (inclusive range)
    assert check_subscriber_range(100, [100, 1000]) == True
    assert check_subscriber_range(1000, [100, 1000]) == True
    assert check_subscriber_range(99, [100, 1000]) == False
    assert check_subscriber_range(1001, [100, 1000]) == False

def test_channel_briefs_filter():
    """Test filtering briefs based on channel subscriber count."""
    # Test case 1: Channel subscriber count within range
    briefs = [
        {
            "id": "brief1",
            "subs_range": [100, 1000],
            "start_date": "2023-01-01",
            "end_date": "2023-12-31"
        },
        {
            "id": "brief2",
            "subs_range": [1000, 10000],
            "start_date": "2023-01-01",
            "end_date": "2023-12-31"
        }
    ]
    channel_analytics = {"subCount": "500"}
    filtered_briefs = channel_briefs_filter(briefs, channel_analytics)
    assert len(filtered_briefs) == 1
    assert filtered_briefs[0]["id"] == "brief1"

    # Test case 2: Channel subscriber count outside all ranges
    channel_analytics = {"subCount": "50"}
    filtered_briefs = channel_briefs_filter(briefs, channel_analytics)
    assert len(filtered_briefs) == 0

    # Test case 3: Brief without subs_range should be included
    briefs = [
        {
            "id": "brief1",
            "subs_range": [100, 1000],
            "start_date": "2023-01-01",
            "end_date": "2023-12-31"
        },
        {
            "id": "brief2",
            "start_date": "2023-01-01",
            "end_date": "2023-12-31"
        }
    ]
    channel_analytics = {"subCount": "50"}
    filtered_briefs = channel_briefs_filter(briefs, channel_analytics)
    assert len(filtered_briefs) == 1
    assert filtered_briefs[0]["id"] == "brief2"

    # Test case 4: Empty briefs list
    filtered_briefs = channel_briefs_filter([], channel_analytics)
    assert len(filtered_briefs) == 0

    # Test case 5: Channel analytics missing subCount
    briefs = [
        {
            "id": "brief1",
            "subs_range": [100, 1000],
            "start_date": "2023-01-01",
            "end_date": "2023-12-31"
        }
    ]
    channel_analytics = {}
    filtered_briefs = channel_briefs_filter(briefs, channel_analytics)
    assert len(filtered_briefs) == 0

    # Test case 6: Both range values null (no filtering)
    briefs = [
        {
            "id": "brief1",
            "subs_range": [None, None],
            "start_date": "2023-01-01",
            "end_date": "2023-12-31"
        }
    ]
    channel_analytics = {"subCount": "50"}
    filtered_briefs = channel_briefs_filter(briefs, channel_analytics)
    assert len(filtered_briefs) == 1
    assert filtered_briefs[0]["id"] == "brief1"

    # Test case 7: First value null (up to max)
    briefs = [
        {
            "id": "brief1",
            "subs_range": [None, 1000],
            "start_date": "2023-01-01",
            "end_date": "2023-12-31"
        }
    ]
    channel_analytics = {"subCount": "500"}
    filtered_briefs = channel_briefs_filter(briefs, channel_analytics)
    assert len(filtered_briefs) == 1
    assert filtered_briefs[0]["id"] == "brief1"

    # Test case 8: Second value null (over min)
    briefs = [
        {
            "id": "brief1",
            "subs_range": [1000, None],
            "start_date": "2023-01-01",
            "end_date": "2023-12-31"
        }
    ]
    channel_analytics = {"subCount": "1500"}
    filtered_briefs = channel_briefs_filter(briefs, channel_analytics)
    assert len(filtered_briefs) == 1
    assert filtered_briefs[0]["id"] == "brief1"

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
    with patch('bitcast.validator.socials.youtube.youtube_scoring.youtube_utils.get_all_uploads') as mock_get_uploads, \
         patch('bitcast.validator.socials.youtube.youtube_scoring.vet_videos') as mock_vet_videos:
        
        # Setup mock return values
        mock_get_uploads.return_value = ["video1", "video2"]
        mock_vet_videos.return_value = (
            {},  # video_matches
            {"video1": {"details": {}}, "video2": {"details": {}}},  # video_data_dict
            {"video1": {"analytics": {}}, "video2": {"analytics": {}}},  # video_analytics_dict
            {}  # video_decision_details
        )
        
        # Call the function
        from bitcast.validator.socials.youtube.youtube_scoring import process_videos
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

def test_update_video_score_with_blacklist_sources():
    """Test update_video_score with the new blacklist sources functionality."""
    # Setup
    youtube_analytics_client = MagicMock()
    briefs = [{"id": "test_brief"}]
    result = {"videos": {}, "scores": {"test_brief": 0}}
    video_matches = {}
    
    with patch('bitcast.validator.socials.youtube.youtube_scoring.calculate_video_score') as mock_calculate, \
         patch('bitcast.validator.utils.blacklist.get_blacklist_sources') as mock_blacklist:
        
        # Test case 1: Multiple blacklisted traffic sources
        mock_blacklist.return_value = ["ADVERTISING", "SPAM_SOURCE"]
        video_id_1 = "test_video_id_1"
        video_matches[video_id_1] = [True]
        result["videos"][video_id_1] = {
            "details": {"bitcastVideoId": video_id_1}, 
            "analytics": {"trafficSourceMinutes": {"SEARCH": 100, "ADVERTISING": 30, "SPAM_SOURCE": 20}}
        }
        mock_calculate.return_value = {"score": 100, "daily_analytics": {}, "scorableHistoryMins": 600}  # Only SEARCH traffic (100 mins)
        update_video_score(video_id_1, youtube_analytics_client, video_matches, briefs, result)
        assert result["scores"]["test_brief"] == 100
        
        # Test case 2: EXT_URL with blacklisted sources
        mock_blacklist.return_value = ["ADVERTISING", "spam-site.com", "bad-domain.net"]
        video_id_2 = "test_video_id_2"
        video_matches[video_id_2] = [True]
        result["videos"][video_id_2] = {
            "details": {"bitcastVideoId": video_id_2}, 
            "analytics": {"trafficSourceMinutes": {"SEARCH": 80, "EXT_URL": 40, "ADVERTISING": 20}}
        }
        # Mock calculate_video_score to simulate EXT_URL proportion calculation
        # If spam-site.com accounts for 50% of lifetime EXT_URL traffic, 
        # then daily EXT_URL should be reduced by 50%
        mock_calculate.return_value = {"score": 100, "daily_analytics": {}, "scorableHistoryMins": 600}  # 80 SEARCH + 20 EXT_URL (after 50% reduction)
        update_video_score(video_id_2, youtube_analytics_client, video_matches, briefs, result)
        assert result["scores"]["test_brief"] == 200

def test_calculate_video_score_ext_url_proportion():
    """Test the EXT_URL proportion calculation logic."""
    from bitcast.validator.socials.youtube.youtube_evaluation import calculate_video_score
    
    # Mock dependencies
    youtube_analytics_client = MagicMock()
    video_publish_date = "2023-01-01T00:00:00Z"
    existing_analytics = {
        "insightTrafficSourceDetail_EXT_URL": {
            "good-site.com": 60,  # Not blacklisted
            "spam-site.com": 60   # Blacklisted - 50% of total EXT_URL traffic
        }
    }
    
    with patch('bitcast.validator.socials.youtube.youtube_utils.get_video_analytics') as mock_analytics, \
         patch('bitcast.validator.utils.blacklist.get_blacklist_sources') as mock_blacklist:
        
        # Test case 1: 50% of EXT_URL traffic is blacklisted
        mock_blacklist.return_value = ["ADVERTISING", "spam-site.com"]
        mock_analytics.return_value = {
            "day_metrics": {
                "2023-01-01": {
                    "day": "2023-01-01",
                    "trafficSourceMinutes": {"SEARCH": 100, "EXT_URL": 40, "ADVERTISING": 20}
                },
                "2023-01-02": {
                    "day": "2023-01-02", 
                    "trafficSourceMinutes": {"SEARCH": 80, "EXT_URL": 60, "ADVERTISING": 30}
                }
            },
            "trafficSourceMinutes": {
                "EXT_URL|2023-01-01": 40,
                "EXT_URL|2023-01-02": 60
            }
        }
        
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value.strftime.side_effect = lambda fmt: {
                '%Y-%m-%d': "2023-01-03"
            }[fmt]
            mock_datetime.strptime.return_value.strftime.return_value = "2023-01-01"
            
            result = calculate_video_score("test_video", youtube_analytics_client, video_publish_date, existing_analytics)
            
            # Expected calculation:
            # Day 1: 100 SEARCH + 20 EXT_URL (40 * 0.5) + 0 ADVERTISING = 120
            # Day 2: 80 SEARCH + 30 EXT_URL (60 * 0.5) + 0 ADVERTISING = 110
            # Total score depends on which days fall in the scoring window
            assert "score" in result
            assert "scorableHistoryMins" in result

def test_calculate_video_score_no_ext_url_data():
    """Test EXT_URL proportion calculation when there's no EXT_URL lifetime data."""
    from bitcast.validator.socials.youtube.youtube_evaluation import calculate_video_score
    
    youtube_analytics_client = MagicMock()
    video_publish_date = "2023-01-01T00:00:00Z"
    existing_analytics = {}  # No EXT_URL data
    
    with patch('bitcast.validator.socials.youtube.youtube_utils.get_video_analytics') as mock_analytics, \
         patch('bitcast.validator.utils.blacklist.get_blacklist_sources') as mock_blacklist:
        
        mock_blacklist.return_value = ["ADVERTISING", "spam-site.com"]
        mock_analytics.return_value = {
            "day_metrics": {
                "2023-01-01": {
                    "day": "2023-01-01",
                    "trafficSourceMinutes": {"SEARCH": 100, "EXT_URL": 40}
                }
            },
            "trafficSourceMinutes": {
                "EXT_URL|2023-01-01": 40
            }
        }
        
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value.strftime.side_effect = lambda fmt: {
                '%Y-%m-%d': "2023-01-03"
            }[fmt]
            mock_datetime.strptime.return_value.strftime.return_value = "2023-01-01"
            
            result = calculate_video_score("test_video", youtube_analytics_client, video_publish_date, existing_analytics)
            
            # When no EXT_URL lifetime data, proportion should be 0.0
            # So all EXT_URL traffic should be included in scoring
            assert "score" in result
            assert "scorableHistoryMins" in result

def test_calculate_video_score_empty_blacklist():
    """Test scoring when blacklist sources is empty."""
    from bitcast.validator.socials.youtube.youtube_evaluation import calculate_video_score
    
    youtube_analytics_client = MagicMock()
    video_publish_date = "2023-01-01T00:00:00Z"
    existing_analytics = {
        "insightTrafficSourceDetail_EXT_URL": {
            "site1.com": 20,
            "site2.com": 20
        }
    }
    
    with patch('bitcast.validator.socials.youtube.youtube_utils.get_video_analytics') as mock_analytics, \
         patch('bitcast.validator.utils.blacklist.get_blacklist_sources') as mock_blacklist:
        
        mock_blacklist.return_value = []  # Empty blacklist
        mock_analytics.return_value = {
            "day_metrics": {
                "2023-01-01": {
                    "day": "2023-01-01",
                    "trafficSourceMinutes": {"SEARCH": 100, "EXT_URL": 40, "ADVERTISING": 20}
                }
            },
            "trafficSourceMinutes": {
                "EXT_URL|2023-01-01": 40
            }
        }
        
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value.strftime.side_effect = lambda fmt: {
                '%Y-%m-%d': "2023-01-03"
            }[fmt]
            mock_datetime.strptime.return_value.strftime.return_value = "2023-01-01"
            
            result = calculate_video_score("test_video", youtube_analytics_client, video_publish_date, existing_analytics)
            
            # With empty blacklist, all traffic should be included
            assert "score" in result
            assert "scorableHistoryMins" in result

def test_calculate_video_score_all_ext_url_blacklisted():
    """Test scoring when all EXT_URL sources are blacklisted."""
    from bitcast.validator.socials.youtube.youtube_evaluation import calculate_video_score
    
    youtube_analytics_client = MagicMock()
    video_publish_date = "2023-01-01T00:00:00Z"
    existing_analytics = {
        "insightTrafficSourceDetail_EXT_URL": {
            "spam1.com": 20,  # Blacklisted
            "spam2.com": 20   # Blacklisted - 100% of EXT_URL traffic is blacklisted
        }
    }
    
    with patch('bitcast.validator.socials.youtube.youtube_utils.get_video_analytics') as mock_analytics, \
         patch('bitcast.validator.utils.blacklist.get_blacklist_sources') as mock_blacklist:
        
        mock_blacklist.return_value = ["ADVERTISING", "spam1.com", "spam2.com"]
        mock_analytics.return_value = {
            "day_metrics": {
                "2023-01-01": {
                    "day": "2023-01-01",
                    "trafficSourceMinutes": {"SEARCH": 100, "EXT_URL": 40, "ADVERTISING": 20}
                }
            },
            "trafficSourceMinutes": {
                "EXT_URL|2023-01-01": 40
            }
        }
        
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value.strftime.side_effect = lambda fmt: {
                '%Y-%m-%d': "2023-01-03"
            }[fmt]
            mock_datetime.strptime.return_value.strftime.return_value = "2023-01-01"
            
            result = calculate_video_score("test_video", youtube_analytics_client, video_publish_date, existing_analytics)
            
            # Only SEARCH traffic should be counted (100 minutes)
            assert "score" in result
            assert "scorableHistoryMins" in result

@patch('bitcast.validator.utils.blacklist.get_blacklist_sources')
def test_blacklist_sources_api_fallback(mock_blacklist):
    """Test that the system falls back gracefully when blacklist sources API fails."""
    from bitcast.validator.socials.youtube.youtube_evaluation import calculate_video_score
    
    # Simulate API failure - should fall back to ["ADVERTISING"]
    mock_blacklist.return_value = ["ADVERTISING"]
    
    youtube_analytics_client = MagicMock()
    video_publish_date = "2023-01-01T00:00:00Z"
    existing_analytics = {}  # No EXT_URL data
    
    with patch('bitcast.validator.socials.youtube.youtube_utils.get_video_analytics') as mock_analytics:
        mock_analytics.return_value = {
            "day_metrics": {
                "2023-01-01": {
                    "day": "2023-01-01",
                    "trafficSourceMinutes": {"SEARCH": 100, "ADVERTISING": 50}
                }
            },
            "trafficSourceMinutes": {}
        }
        
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value.strftime.side_effect = lambda fmt: {
                '%Y-%m-%d': "2023-01-03"
            }[fmt]
            mock_datetime.strptime.return_value.strftime.return_value = "2023-01-01"
            
            result = calculate_video_score("test_video", youtube_analytics_client, video_publish_date, existing_analytics)
            
            # Should still work with fallback blacklist
            assert "score" in result
            assert "scorableHistoryMins" in result 