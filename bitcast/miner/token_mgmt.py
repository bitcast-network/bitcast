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
    bt.logging.info("Loading token from file.")
    with open(os.path.join(current_dir, 'secrets/creds.pkl'), 'rb') as f:
        creds = pickle.load(f)
    
    if creds.expired and creds.refresh_token:
        bt.logging.info("Token expired, refreshing token.")
        creds.refresh(Request())

    bt.logging.info(f"Token loaded successfully.")
    return creds.token