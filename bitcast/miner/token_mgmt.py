import os
import pickle
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import bittensor as bt
import sys
import glob

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
    bt.logging.info("Loading tokens from secrets directory.")
    tokens = []
    
    # Find all .pkl files in the secrets directory
    cred_files = glob.glob(os.path.join(current_dir, 'secrets/*.pkl'))
    
    for cred_file in cred_files:
        try:
            with open(cred_file, 'rb') as f:
                creds = pickle.load(f)
            
            if creds.expired and creds.refresh_token:
                bt.logging.info(f"Token expired in {cred_file}, refreshing token.")
                creds.refresh(Request())
            
            tokens.append(creds.token)
            bt.logging.info(f"Token loaded successfully from {cred_file}")
        except Exception as e:
            bt.logging.error(f"Error loading token from {cred_file}: {e}")
    
    if not tokens:
        bt.logging.error("No valid tokens found in secrets directory.")
        return None
        
    return tokens