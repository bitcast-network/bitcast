#!/bin/bash

# Exit on error
set -e

# Get the absolute path of the project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_PARENT="$(cd "$PROJECT_ROOT/.." && pwd)"

MINER_PROCESS_NAME="bitcast_miner"
VENV_PATH="$PROJECT_PARENT/venv_bitcast"

# Activate virtual environment
if [ ! -d "$VENV_PATH" ]; then
    echo "Error: Virtual environment not found at $VENV_PATH"
    echo "Please run setup_env.sh first"
    exit 1
fi

echo "Activating virtual environment..."
source "$VENV_PATH/bin/activate"

# Source environment variables from .env file
if [ -f "$PROJECT_ROOT/bitcast/miner/.env" ]; then
    echo "Loading environment variables from .env file..."
    source "$PROJECT_ROOT/bitcast/miner/.env"
else
    echo "Error: .env file not found at $PROJECT_ROOT/bitcast/miner/.env"
    exit 1
fi

cd "$PROJECT_ROOT"

# Default values for optional parameters
SUBTENSOR_CHAIN_ENDPOINT=${SUBTENSOR_CHAIN_ENDPOINT:-"wss://entrypoint-finney.opentensor.ai:443"}
SUBTENSOR_NETWORK=${SUBTENSOR_NETWORK:-"finney"}
PORT=${PORT:-8091}
LOGGING=${LOGGING:-"--logging.debug"}

# Handle boolean flags
DEV_MODE_FLAG=""
if [ "${DEV_MODE,,}" = "true" ]; then
    DEV_MODE_FLAG="--dev_mode"
fi

DISABLE_AUTO_UPDATE_FLAG=""
if [ "${DISABLE_AUTO_UPDATE,,}" = "true" ]; then
    DISABLE_AUTO_UPDATE_FLAG="--disable_auto_update"
fi

# Check if required environment variables are set
if [ -z "$NETUID" ] || [ -z "$WALLET_NAME" ] || [ -z "$HOTKEY_NAME" ]; then
    echo "Error: Required environment variables NETUID, WALLET_NAME, and HOTKEY_NAME must be set in .env file"
    exit 1
fi

# STOP MINER PROCESS
if pm2 list | grep -q "$MINER_PROCESS_NAME"; then
    echo "Process '$MINER_PROCESS_NAME' is already running. Restarting it..."
    pm2 restart "$MINER_PROCESS_NAME"
else
    echo "Process '$MINER_PROCESS_NAME' is not running. Starting it for the first time..."
    pm2 start python --name "$MINER_PROCESS_NAME" -- neurons/miner.py \
        --netuid "$NETUID" \
        --subtensor.chain_endpoint "$SUBTENSOR_CHAIN_ENDPOINT" \
        --subtensor.network "$SUBTENSOR_NETWORK" \
        --wallet.name "$WALLET_NAME" \
        --wallet.hotkey "$HOTKEY_NAME" \
        --axon.port "$PORT" \
        $LOGGING $DEV_MODE_FLAG $DISABLE_AUTO_UPDATE_FLAG
fi