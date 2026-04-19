#!/bin/bash
# Helper to extract Bittensor wallet data into base64 env var format
# Usage: ./scripts/wallet-env.sh <wallet_name> <hotkey_name>
# Outputs env vars that can be appended to .env

set -euo pipefail

WALLET_NAME="${1:-default}"
HOTKEY_NAME="${2:-default}"
WALLET_BASE="${HOME}/.bittensor/wallets"

WALLET_DIR="${WALLET_BASE}/${WALLET_NAME}"
HOTKEY_DIR="${WALLET_DIR}/hotkeys/${HOTKEY_NAME}"

if [ ! -f "${HOTKEY_DIR}/hotkey" ]; then
    echo "ERROR: Hotkey not found at ${HOTKEY_DIR}/hotkey" >&2
    echo "Check: ls ${WALLET_DIR}/hotkeys/" >&2
    exit 1
fi

echo "# Wallet: ${WALLET_NAME}/${HOTKEY_NAME}"
echo "HOTKEY_DATA=$(base64 -w0 "${HOTKEY_DIR}/hotkey")"

if [ -f "${HOTKEY_DIR}/hotkeypub.txt" ]; then
    echo "HOTKEYPUB_DATA=$(cat "${HOTKEY_DIR}/hotkeypub.txt")"
fi

if [ -f "${WALLET_DIR}/coldkeypub.txt" ]; then
    echo "COLDKEYPUB_DATA=$(cat "${WALLET_DIR}/coldkeypub.txt")"
fi

echo "WALLET_NAME=${WALLET_NAME}"
echo "HOTKEY_NAME=${HOTKEY_NAME}"
