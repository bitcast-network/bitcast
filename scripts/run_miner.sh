#!/bin/bash

# Exit on error
set -e

# Get the absolute path of the project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MINER_PROCESS_NAME="bitcast_miner"
VENV_PATH="$PROJECT_ROOT/venv_bitcast"

# Activate virtual environment
if [ ! -d "$VENV_PATH" ]; then
    echo "Error: Virtual environment not found at $VENV_PATH"
    echo "Please run setup_env.sh first"
    exit 1
fi

echo "Activating virtual environment..."
source "$VENV_PATH/bin/activate"

# Stop miner process if it's already running on pm2
if pm2 list | grep -q "$MINER_PROCESS_NAME"; then
  echo "Process '$MINER_PROCESS_NAME' is already running. Deleting it..."
  pm2 delete "$MINER_PROCESS_NAME"
fi

echo "Starting miner process with pm2"
cd "$PROJECT_ROOT"

# Hardcoded parameters
NETUID=1
SUBTENSOR_CHAIN_ENDPOINT="ws://35.86.5.19:9944"
SUBTENSOR_NETWORK="ws://35.86.5.19:9944"
WALLET_NAME="test_1"
HOTKEY_NAME="hotkey_1"
PORT=8091
LOGGING="--logging.debug"
DEV_MODE="--dev_mode"
DISABLE_AUTO_UPDATE= #"--disable_auto_update"

#TODO remove dev_mode
# Run the miner with hardcoded parameters using pm2
pm2 start python --name "$MINER_PROCESS_NAME" -- neurons/miner.py --netuid $NETUID --subtensor.chain_endpoint $SUBTENSOR_CHAIN_ENDPOINT --subtensor.network $SUBTENSOR_NETWORK --wallet.name $WALLET_NAME --wallet.hotkey $HOTKEY_NAME --axon.port $PORT $LOGGING $DEV_MODE $DISABLE_AUTO_UPDATE