import os
import pickle
from google.auth.transport.requests import Request
import bittensor as bt
import sys

current_dir = os.path.dirname(__file__)

def init():
    creds_path = os.path.join(current_dir, 'secrets/creds.pkl')
    
    if not os.path.exists(creds_path):
        bt.logging.error("❌ Authentication required.")
        bt.logging.error("")
        bt.logging.error("🔧 PLEASE RUN:")
        bt.logging.error("    python manual_auth.py")
        bt.logging.error("")
        bt.logging.error("This will guide you through the authentication process.")
        bt.logging.error("Works in all environments (headless, SSH, Docker, etc.)")
        bt.logging.error("")
        sys.exit(1)

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