import os
import pickle
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import bittensor as bt
import sys

current_dir = os.path.dirname(__file__)

SCOPES = [
    'https://www.googleapis.com/auth/yt-analytics.readonly',
    'https://www.googleapis.com/auth/youtube.readonly'
]

def init(force_auth):
    if force_auth or not os.path.exists(os.path.join(current_dir, 'secrets/creds.pkl')):
        bt.logging.info("Running authentication flow.")
        run_auth_flow()

def run_auth_flow():
    client_secrets_path = os.path.join(current_dir, 'secrets/client_secret.json')
    if not os.path.exists(client_secrets_path):
        bt.logging.error(f"Client secrets file not found: {client_secrets_path}.")
        sys.exit(1)
    
    bt.logging.info("Starting authentication flow.")
    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, SCOPES)
    creds = flow.run_local_server(port=0)
    
    # Save refresh token and access token
    with open(os.path.join(current_dir, 'secrets/creds.pkl'), 'wb') as f:
        pickle.dump(creds, f)
    
    bt.logging.info("Refresh token saved.")

def load_token():
    """
    Load all .pkl token files from the secrets directory.
    Returns a list of access tokens for the new multi-token synapse structure.
    """
    bt.logging.info("Loading tokens from files.")
    secrets_dir = os.path.join(current_dir, 'secrets')
    tokens = []
    
    if not os.path.exists(secrets_dir):
        bt.logging.warning(f"Secrets directory not found: {secrets_dir}")
        return tokens
    
    # Find all .pkl files in the secrets directory
    pkl_files = [f for f in os.listdir(secrets_dir) if f.endswith('.pkl')]
    
    if not pkl_files:
        bt.logging.warning("No .pkl token files found in secrets directory.")
        return tokens
    
    bt.logging.info(f"Found {len(pkl_files)} token files: {pkl_files}")
    
    for pkl_file in pkl_files:
        try:
            file_path = os.path.join(secrets_dir, pkl_file)
            with open(file_path, 'rb') as f:
                creds = pickle.load(f)
            
            # Refresh token if expired
            if creds.expired and creds.refresh_token:
                bt.logging.info(f"Token in {pkl_file} expired, refreshing token.")
                creds.refresh(Request())
            
            tokens.append(creds.token)
            bt.logging.info(f"Token loaded successfully from {pkl_file}")
            
        except Exception as e:
            bt.logging.error(f"Error loading token from {pkl_file}: {e}")
            continue
    
    bt.logging.info(f"Successfully loaded {len(tokens)} tokens.")
    return tokens