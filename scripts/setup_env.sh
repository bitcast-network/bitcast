#!/bin/bash

# Exit on error
set -e

# Get the absolute path of the project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_PARENT="$(cd "$PROJECT_ROOT/.." && pwd)"

###########################################
# System Updates and Package Installation #
###########################################

# Update system
sudo apt update -y

# Install core dependencies
sudo apt install -y \
    python3-pip \
    python3-venv \
    npm

# Install process manager if not already installed
if ! command -v pm2 &> /dev/null; then
    sudo npm install -g pm2@latest
fi

############################
# Virtual Environment Setup #
############################

# Load environment variables from .env file if it exists
if [ -f "$PROJECT_ROOT/bitcast/validator/.env" ]; then
  export $(grep -v '^#' "$PROJECT_ROOT/bitcast/validator/.env" | sed 's/ *= */=/g' | xargs)
fi

# Set default virtual environment path if not specified in .env
VENV_PATH=${VENV_PATH:-"$PROJECT_PARENT/venv_bitcast"}

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_PATH" ]; then
    echo "Creating virtual environment at $VENV_PATH"
    python3 -m venv "$VENV_PATH"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source "$VENV_PATH/bin/activate"

############################
# Python Package Installation
############################

# Change to project root directory
cd "$PROJECT_ROOT"

# Install project dependencies
pip install --upgrade pip

# Remove packages that were removed in bittensor 10.x and conflict with their replacements.
# pip install -r requirements.txt does NOT uninstall packages that are no longer listed,
# so stale scalecodec/bt-decode/bittensor-cli from 9.x will crash bittensor 10.x at import
# time with: RuntimeError: Conflict detected: 'scalecodec' is installed, conflicts with 'cyscale'.
#
# IMPORTANT: cyscale installs its compiled .so files INTO the scalecodec/ directory.
# If we only uninstall 'scalecodec', pip deletes cyscale's files but keeps cyscale's
# metadata — so the subsequent 'pip install -r requirements.txt' skips reinstalling
# cyscale, leaving scalecodec/ gutted and 'import bittensor' fails with
# ModuleNotFoundError: No module named 'scalecodec'. Uninstall cyscale too so it
# gets cleanly reinstalled.
pip uninstall -y scalecodec cyscale bt-decode bittensor-cli 2>/dev/null || true

pip install -r requirements.txt
pip install -e .

echo "Environment setup completed successfully."