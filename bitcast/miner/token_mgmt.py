import os
import pickle
from google.auth.transport.requests import Request
import bittensor as bt
import sys

import httpx

current_dir = os.path.dirname(__file__)

# --- Configuration ---
# Set TOKEN_SOURCE=api to use the Bitcast API endpoint.
# Set TOKEN_SOURCE=local (or leave unset) to use local .pkl files.
TOKEN_SOURCE = os.getenv("TOKEN_SOURCE", "local")

# Bitcast API config (only used when TOKEN_SOURCE=api)
BITCAST_API_URL = os.getenv("BITCAST_API_URL", "")
BITCAST_API_KEY = os.getenv("BITCAST_API_KEY", "")


def _get_token_source():
    """Determine token source: 'api' or 'local'."""
    source = TOKEN_SOURCE.lower().strip()
    if source not in ("api", "local"):
        bt.logging.warning(f"Unknown TOKEN_SOURCE '{TOKEN_SOURCE}', falling back to 'local'")
        return "local"
    return source


def init():
    source = _get_token_source()
    bt.logging.info(f"Token source: {source}")

    if source == "api":
        if not BITCAST_API_URL:
            bt.logging.error("❌ TOKEN_SOURCE=api but BITCAST_API_URL is not set.")
            bt.logging.error("Set BITCAST_API_URL env var (e.g. https://bitcast-api.bitcast.network)")
            sys.exit(1)
        if not BITCAST_API_KEY:
            bt.logging.error("❌ TOKEN_SOURCE=api but BITCAST_API_KEY is not set.")
            bt.logging.error("Set BITCAST_API_KEY env var or switch to TOKEN_SOURCE=local")
            sys.exit(1)
        return

    # Local mode: check for .pkl files
    secrets_dir = os.path.join(current_dir, 'secrets')
    if not os.path.exists(secrets_dir):
        pkl_files = []
    else:
        pkl_files = [f for f in os.listdir(secrets_dir) if f.endswith('.pkl')]
    
    if not pkl_files:
        bt.logging.error("❌ Authentication required.")
        bt.logging.error("")
        bt.logging.error("🔧 PLEASE RUN:")
        bt.logging.error("    python manual_auth.py")
        bt.logging.error("")
        bt.logging.error("Or set TOKEN_SOURCE=api and BITCAST_API_KEY to use the API.")
        bt.logging.error("Works in all environments (headless, SSH, Docker, etc.)")
        bt.logging.error("")
        sys.exit(1)


def _load_token_from_api():
    """
    Fetch fresh access tokens from the Bitcast API endpoint.
    The API handles refresh token decryption and exchange server-side.
    """
    try:
        resp = httpx.get(
            f"{BITCAST_API_URL}/api/v2/youtube/credentials/access-tokens",
            headers={"X-API-Key": BITCAST_API_KEY},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        tokens = [item["access_token"] for item in data.get("tokens", [])]
        bt.logging.info(f"Loaded {len(tokens)} access tokens from API")
        return tokens

    except httpx.HTTPStatusError as e:
        bt.logging.error(f"API returned {e.response.status_code}: {e.response.text}")
    except Exception as e:
        bt.logging.error(f"Failed to fetch tokens from API: {e}")

    return []


def _load_token_from_local():
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


def load_token():
    """
    Load access tokens using the configured source (api or local).
    """
    if _get_token_source() == "api":
        return _load_token_from_api()
    return _load_token_from_local()