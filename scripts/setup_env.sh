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

VENV_PATH="$PROJECT_PARENT/venv_bitcast"

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
pip install -r requirements.txt
pip install -e .

echo "Environment setup completed successfully."