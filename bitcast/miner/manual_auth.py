#!/usr/bin/env python3
"""
Manual Authentication Script for BitCast Miner

This script provides authentication for headless environments using an echo service.
Works universally across all environments without complex setup.

Usage:
    python manual_auth.py
"""

import os
import pickle
import sys
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import bittensor as bt

# Get the directory of this script
current_dir = os.path.dirname(__file__)

SCOPES = [
    'https://www.googleapis.com/auth/yt-analytics.readonly',
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/yt-analytics-monetary.readonly'
]

def manual_auth_flow():
    """
    Runs OAuth authentication flow using an echo service for code retrieval.
    Works universally across all environments without complex setup.
    """
    client_secrets_path = os.path.join(current_dir, 'secrets/client_secret.json')
    
    if not os.path.exists(client_secrets_path):
        print(f"❌ ERROR: Client secrets file not found: {client_secrets_path}")
        print("Please ensure you have the client_secret.json file in the secrets directory.")
        sys.exit(1)
    
    # Ensure secrets directory exists
    secrets_dir = os.path.join(current_dir, 'secrets')
    os.makedirs(secrets_dir, exist_ok=True)
    
    print("🚀 Starting OAuth authentication flow...")
    print()
    
    try:
        # Create the flow using the client secrets file
        flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, SCOPES)
        
        # Set redirect URI to the echo service
        flow.redirect_uri = 'https://dashboard.bitcast.network/echo'
        
        # Generate the authorization URL
        auth_url, _ = flow.authorization_url(prompt='consent')
        
        print("🔗 AUTHORIZATION URL:")
        print(auth_url)
        print()
        print("📋 INSTRUCTIONS:")
        print("1. Copy the URL above and open it in ANY browser (on any device)")
        print("2. Sign in to Google and grant the requested permissions")
        print("3. You'll be redirected to the BitCast echo service")
        print("4. Look for the authorization code in the URL or on the page")
        print("   The code will be a long string starting with '4/0' (e.g., '4/0AVMBsJj...')")
        print("5. Copy ONLY the authorization code")
        print("6. Paste it below when prompted")
        print()
        
        # Get the authorization code from user
        auth_code = input("📝 Enter the authorization code: ").strip()
        
        if not auth_code:
            print("❌ No code provided. Authentication cancelled.")
            return
            
        print("🔄 Exchanging code for access token...")
        
        # Exchange code for credentials
        flow.fetch_token(code=auth_code)
        creds = flow.credentials
        
        # Save the credentials
        creds_path = os.path.join(current_dir, 'secrets/creds.pkl')
        with open(creds_path, 'wb') as f:
            pickle.dump(creds, f)
        
        print(f"✅ Authentication successful!")
        print(f"📁 Credentials saved to: {creds_path}")
        print("🎉 You can now run your BitCast miner!")
        
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        sys.exit(1)

def check_existing_credentials():
    """
    Check if valid credentials already exist.
    """
    creds_path = os.path.join(current_dir, 'secrets/creds.pkl')
    
    if not os.path.exists(creds_path):
        return False, "No credentials file found."
    
    try:
        with open(creds_path, 'rb') as f:
            creds = pickle.load(f)
        
        if creds.expired and creds.refresh_token:
            print("Existing credentials are expired but can be refreshed.")
            try:
                creds.refresh(Request())
                # Save refreshed credentials
                with open(creds_path, 'wb') as f:
                    pickle.dump(creds, f)
                return True, "Credentials refreshed successfully."
            except Exception as e:
                return False, f"Failed to refresh credentials: {str(e)}"
        elif not creds.expired:
            return True, "Valid credentials already exist."
        else:
            return False, "Credentials are expired and cannot be refreshed."
            
    except Exception as e:
        return False, f"Error reading credentials: {str(e)}"

def main():
    print("BitCast Miner - Manual Authentication Tool")
    print("=" * 50)
    
    # Check if credentials already exist
    is_valid, message = check_existing_credentials()
    
    if is_valid:
        print(f"✅ {message}")
        print("Your miner can run normally with these credentials.")
        
        # Ask if they want to re-authenticate anyway
        response = input("\nDo you want to re-authenticate and overwrite existing credentials? (y/N): ").lower().strip()
        
        if response not in ['y', 'yes']:
            print("Keeping existing credentials. Authentication cancelled.")
            return
        
        print("\nProceeding with re-authentication to overwrite existing credentials...")
    else:
        print(f"ℹ️  {message}")
        print("Authentication required.")
        
        # Prompt user to continue
        response = input("\nDo you want to proceed with authentication? (y/N): ").lower().strip()
        
        if response not in ['y', 'yes']:
            print("Authentication cancelled.")
            return
    
    # Run the manual authentication flow
    manual_auth_flow()

if __name__ == "__main__":
    main() 