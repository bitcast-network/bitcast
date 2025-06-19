from pathlib import Path
import sys

# token loading and refresh
def test_load_token_when_not_expired():
    from bitcast.miner.token_mgmt import load_token
    from unittest.mock import patch, MagicMock

    mock_creds = MagicMock()
    mock_creds.expired = False
    mock_creds.refresh_token = None
    mock_creds.token = "not_expired_token"

    with patch('builtins.open'), \
         patch('pickle.load', return_value=mock_creds), \
         patch('os.path.exists', return_value=True), \
         patch('os.listdir', return_value=['creds.pkl']):
        tokens = load_token()
        assert tokens == ["not_expired_token"]
        assert len(tokens) == 1

def test_load_token_when_expired_and_has_refresh():
    from bitcast.miner.token_mgmt import load_token
    from unittest.mock import patch, MagicMock

    mock_creds = MagicMock()
    mock_creds.expired = True
    mock_creds.refresh_token = "refresh_token_value"
    mock_creds.token = "refreshed_token"

    with patch('builtins.open'), \
         patch('pickle.load', return_value=mock_creds), \
         patch('bitcast.miner.token_mgmt.Request'), \
         patch.object(mock_creds, 'refresh'), \
         patch('os.path.exists', return_value=True), \
         patch('os.listdir', return_value=['creds.pkl']):
        tokens = load_token()
        assert tokens == ["refreshed_token"]
        assert len(tokens) == 1

# init function
def test_init_when_creds_exist():
    from bitcast.miner.token_mgmt import init
    from unittest.mock import patch

    # Test that init() succeeds when credentials exist
    with patch('os.path.exists', return_value=True):
        # Should not raise SystemExit
        init()

def test_init_when_creds_missing():
    from bitcast.miner.token_mgmt import init
    from unittest.mock import patch
    import pytest

    # Test that init() exits when credentials are missing
    with patch('os.path.exists', return_value=False), \
         patch('bitcast.miner.token_mgmt.bt.logging.error'):
        with pytest.raises(SystemExit):
            init()
