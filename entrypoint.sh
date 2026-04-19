#!/bin/bash
# Container entrypoint - bootstraps Bittensor wallet files from secrets
# before launching the miner or validator.
#
# Only the hotkey (private) and coldkeypub (public) are needed for runtime.
# Coldkey private key is intentionally excluded for security.
#
# Environment variables consumed:
#   WALLET_PATH        - base path for wallet storage (default: /root/.bittensor/wallets)
#   HOTKEY_DATA        - base64-encoded hotkey file (private key)
#   HOTKEYPUB_DATA     - content for hotkeypub.txt (public key)
#   COLDKEYPUB_DATA    - content for coldkeypub.txt (public address)

set -euo pipefail

WALLET_BASE="${WALLET_PATH:-/root/.bittensor/wallets}"
WALLET_NAME="${WALLET_NAME:-default}"

WALLET_DIR="${WALLET_BASE}/${WALLET_NAME}"
mkdir -p "${WALLET_DIR}"

# --- Write hotkey (private key) ---
if [ -n "${HOTKEY_DATA:-}" ]; then
    echo "[entrypoint] Writing hotkey: ${WALLET_NAME}"
    echo "${HOTKEY_DATA}" | base64 -d > "${WALLET_DIR}/hotkey"
    chmod 600 "${WALLET_DIR}/hotkey"
else
    echo "[entrypoint] ERROR: HOTKEY_DATA not set - cannot run without hotkey"
    exit 1
fi

# --- Write hotkeypub (public key) ---
if [ -n "${HOTKEYPUB_DATA:-}" ]; then
    echo "${HOTKEYPUB_DATA}" > "${WALLET_DIR}/hotkeypub.txt"
    chmod 644 "${WALLET_DIR}/hotkeypub.txt"
fi

# --- Write coldkeypub (public address only) ---
if [ -n "${COLDKEYPUB_DATA:-}" ]; then
    echo "${COLDKEYPUB_DATA}" > "${WALLET_DIR}/coldkeypub.txt"
    chmod 644 "${WALLET_DIR}/coldkeypub.txt"
fi

# --- Clear sensitive env vars ---
unset HOTKEY_DATA

echo "[entrypoint] Wallet bootstrapped at ${WALLET_DIR}"
echo "[entrypoint] Starting: $*"
exec "$@"
