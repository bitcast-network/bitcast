#!/bin/bash
# Container entrypoint - bootstraps Bittensor wallet files from secrets
# before launching the miner or validator.
#
# Only the hotkey (private) and coldkeypub (public) are needed for runtime.
# Coldkey private key is intentionally excluded for security.
#
# Bittensor layout:
#   wallets/<wallet>/hotkeys/<hotkey>           ← hotkey JSON (file)
#   wallets/<wallet>/hotkeys/<hotkey>pub.txt    ← public key
#   wallets/<wallet>/coldkeypub.txt
#
# Environment variables consumed:
#   WALLET_PATH        - base path (default: /root/.bittensor/wallets)
#   WALLET_NAME        - wallet name (default: default)
#   HOTKEY_NAME        - hotkey name (default: default)
#   HOTKEY_DATA        - base64-encoded hotkey file (private key)
#   HOTKEYPUB_DATA     - content for <hotkey>pub.txt (public key)
#   COLDKEYPUB_DATA    - content for coldkeypub.txt (public address)

set -euo pipefail

WALLET_BASE="${WALLET_PATH:-/root/.bittensor/wallets}"
WALLET_NAME="${WALLET_NAME:-default}"
HOTKEY_NAME="${HOTKEY_NAME:-default}"

WALLET_DIR="${WALLET_BASE}/${WALLET_NAME}"
HOTKEY_DIR="${WALLET_DIR}/hotkeys"
mkdir -p "${HOTKEY_DIR}"

# --- Write hotkey (private key) ---
if [ -n "${HOTKEY_DATA:-}" ]; then
    echo "[entrypoint] Writing hotkey: ${WALLET_NAME}/${HOTKEY_NAME}"
    echo "${HOTKEY_DATA}" | base64 -d > "${HOTKEY_DIR}/${HOTKEY_NAME}"
    chmod 600 "${HOTKEY_DIR}/${HOTKEY_NAME}"
else
    echo "[entrypoint] ERROR: HOTKEY_DATA not set - cannot run without hotkey"
    exit 1
fi

# --- Write hotkeypub (public key) ---
if [ -n "${HOTKEYPUB_DATA:-}" ]; then
    echo "${HOTKEYPUB_DATA}" > "${HOTKEY_DIR}/${HOTKEY_NAME}pub.txt"
    chmod 644 "${HOTKEY_DIR}/${HOTKEY_NAME}pub.txt"
fi

# --- Write coldkeypub (public address only) ---
if [ -n "${COLDKEYPUB_DATA:-}" ]; then
    echo "${COLDKEYPUB_DATA}" > "${WALLET_DIR}/coldkeypub.txt"
    chmod 644 "${WALLET_DIR}/coldkeypub.txt"
fi

# --- Clear sensitive env vars ---
unset HOTKEY_DATA

echo "[entrypoint] Wallet bootstrapped at ${HOTKEY_DIR}/${HOTKEY_NAME}"
echo "[entrypoint] Starting: $*"
exec "$@"
