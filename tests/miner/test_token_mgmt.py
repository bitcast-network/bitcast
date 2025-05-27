from pathlib import Path

# auth flow
def test_run_auth_flow():
    from bitcast.miner.token_mgmt import run_auth_flow
    from unittest.mock import patch, MagicMock

    mock_flow = MagicMock()
    with patch('bitcast.miner.token_mgmt.InstalledAppFlow') as mock_installed_app_flow, \
         patch('builtins.open'), \
         patch('pickle.dump'):
        mock_flow.run_local_server.return_value = MagicMock()
        mock_installed_app_flow.from_client_secrets_file.return_value = mock_flow

        run_auth_flow()

        mock_installed_app_flow.from_client_secrets_file.assert_called_once()
        mock_flow.run_local_server.assert_called_once()

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
def test_init():
    from bitcast.miner.token_mgmt import init, run_auth_flow
    from unittest.mock import patch
    import os

    with patch('os.path.exists', return_value=False), \
         patch('bitcast.miner.token_mgmt.run_auth_flow') as mock_run_auth_flow:
        init(force_auth=False)
        mock_run_auth_flow.assert_called_once()

    with patch('os.path.exists', return_value=True), \
         patch('bitcast.miner.token_mgmt.run_auth_flow') as mock_run_auth_flow:
        init(force_auth=True)
        mock_run_auth_flow.assert_called_once()
