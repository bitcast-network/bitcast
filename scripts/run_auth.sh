#!/bin/bash

# Exit on error
set -e

# Get the absolute path of the project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_PARENT="$(cd "$PROJECT_ROOT/.." && pwd)"

VENV_PATH="$PROJECT_PARENT/venv_bitcast"

echo "BitCast Miner - Authentication Setup"
echo "===================================="

# Check if virtual environment exists, if not run setup
if [ ! -d "$VENV_PATH" ]; then
    echo "Virtual environment not found. Running setup..."
    if [ -f "$PROJECT_ROOT/scripts/setup_env.sh" ]; then
        echo "Running setup_env.sh..."
        bash "$PROJECT_ROOT/scripts/setup_env.sh"
    else
        echo "Error: setup_env.sh not found at $PROJECT_ROOT/scripts/setup_env.sh"
        exit 1
    fi
else
    echo "Virtual environment found at $VENV_PATH"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source "$VENV_PATH/bin/activate"

# Change to miner directory
cd "$PROJECT_ROOT/bitcast/miner"

# Check if client_secret.json exists
if [ ! -f "secrets/client_secret.json" ]; then
    echo ""
    echo "⚠️  WARNING: Client secrets file not found!"
    echo "Please ensure you have 'client_secret.json' in the 'secrets/' directory"
    echo "Location: $PROJECT_ROOT/bitcast/miner/secrets/client_secret.json"
    echo ""
    echo "You can download this file from Google Cloud Console:"
    echo "1. Go to https://console.cloud.google.com"
    echo "2. Navigate to APIs & Services → Credentials"
    echo "3. Download your OAuth 2.0 Client ID as JSON"
    echo "4. Save it as 'client_secret.json' in the secrets directory"
    echo ""
    read -p "Press Enter to continue anyway, or Ctrl+C to exit..."
fi

# Run manual authentication
echo ""
echo "🚀 Starting manual authentication..."
echo ""
python manual_auth.py

echo ""
echo "✅ Authentication setup complete!"
echo "You can now run your miner with: bash scripts/run_miner.sh" 