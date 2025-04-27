#!/bin/bash

# Exit on error
set -e

# Get the absolute path of the project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

VALIDATOR_PROCESS_NAME="bitcast_validator"
VENV_PATH="$PROJECT_ROOT/venv_bitcast"

# Activate virtual environment
if [ ! -d "$VENV_PATH" ]; then
    echo "Error: Virtual environment not found at $VENV_PATH"
    echo "Please run setup_env.sh first"
    exit 1
fi

echo "Activating virtual environment..."
source "$VENV_PATH/bin/activate"

# Load environment variables from .env file
if [ -f "$PROJECT_ROOT/bitcast/validator/.env" ]; then
  export $(grep -v '^#' "$PROJECT_ROOT/bitcast/validator/.env" | sed 's/ *= */=/g' | xargs)
fi

# Ensure required environment variables are set
if [ -z "$RAPID_API_KEY" ]; then
  echo "Error: RAPID_API_KEY is not set in the .env file."
  exit 1
fi
if [ -z "$OPENAI_API_KEY" ]; then
  echo "Error: OPENAI_API_KEY is not set in the .env file."
  exit 1
fi
if [ -z "$BITCAST_BRIEFS_ENDPOINT" ]; then
  echo "Error: BITCAST_BRIEFS_ENDPOINT is not set in the .env file."
  exit 1
fi
if [ -z "$WANDB_API_KEY" ]; then
  echo "Error: WANDB_API_KEY is not set in the .env file."
  exit 1
fi
if [ -z "$WALLET_NAME" ]; then
  echo "Error: WALLET_NAME is not set in the .env file."
  exit 1
fi
if [ -z "$HOTKEY_NAME" ]; then
  echo "Error: HOTKEY_NAME is not set in the .env file."
  exit 1
fi

# Set default values for validator parameters if not set in .env
NETUID=${NETUID:-93}
SUBTENSOR_NETWORK=${SUBTENSOR_NETWORK:-"finney"}
SUBTENSOR_CHAIN_ENDPOINT=${SUBTENSOR_CHAIN_ENDPOINT:-"wss://entrypoint-finney.opentensor.ai:443"}
PORT=${PORT:-8092}
LOGGING=${LOGGING:-"--logging.debug"}
WANDB_PROJECT=${WANDB_PROJECT:-"bitcast_vali_logs"}

# Clear cache if specified 
while [[ $# -gt 0 ]]; do
  case $1 in
    --clear-cache)
      rm -rf "$PROJECT_ROOT/cache"
      shift
      ;;
    *)
      shift
      ;;
  esac
done

# Login to Weights & Biases
if ! wandb login $WANDB_API_KEY; then
  echo "Failed to login to Weights & Biases with the provided API key."
  exit 1
fi

# STOP VALIDATOR PROCESS
if pm2 list | grep -q "$VALIDATOR_PROCESS_NAME"; then
  echo "Process '$VALIDATOR_PROCESS_NAME' is already running. Deleting it..."
  pm2 delete "$VALIDATOR_PROCESS_NAME"
fi

echo "Starting validator process with pm2"
cd "$PROJECT_ROOT"

# Start the validator with pm2 using environment variables
pm2 start python --name "$VALIDATOR_PROCESS_NAME" -- neurons/validator.py --netuid $NETUID --subtensor.chain_endpoint $SUBTENSOR_CHAIN_ENDPOINT --subtensor.network $SUBTENSOR_NETWORK --wallet.name $WALLET_NAME --wallet.hotkey $HOTKEY_NAME --axon.port $PORT  --wandb.project $WANDB_PROJECT $LOGGING $DISABLE_AUTO_UPDATE