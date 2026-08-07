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

WALLET_BASE="${WALLET_PATH:-/home/bitcast/.bittensor/wallets}"
WALLET_NAME="${WALLET_NAME:-default}"
HOTKEY_NAME="${HOTKEY_NAME:-default}"

WALLET_DIR="${WALLET_BASE}/${WALLET_NAME}"
HOTKEY_DIR="${WALLET_DIR}/hotkeys"
mkdir -p "${HOTKEY_DIR}"

# bittensor-wallet 4.1+ writes a "cryptoType" field into keyfiles that 4.0.1 —
# the version this image pins — refuses to parse:
#   DeserializationError("Failed to parse keyfile data.")
#
# This is not cosmetic. serve_axon reads wallet.coldkeypub to build the
# extrinsic, so an unparseable coldkeypub.txt aborts the serve *after* the axon
# starts locally. The miner then logs as healthy forever while its on-chain axon
# still points at whatever address it last published — validators dial the stale
# address and the miner earns nothing. This has now bitten prod twice: task-def
# rev 10 (2026-07-29) and rev 12 (2026-08-06, the no-code wallet migration).
#
# 4.0.1's format has no cryptoType and assumes SR25519, so dropping a cryptoType
# of 1 (SR25519) is lossless — it yields the identical ss58 address. Any other
# value would silently change the key's curve, so refuse rather than guess. A
# non-JSON (encrypted) keyfile passes through untouched.
strip_crypto_type() {
    python3 - "$1" <<'PY'
import json
import sys

path = sys.argv[1]
try:
    with open(path) as fh:
        keyfile = json.load(fh)
except (OSError, ValueError, UnicodeDecodeError):
    sys.exit(0)  # encrypted, missing or non-JSON keyfile — leave it alone

crypto_type = keyfile.pop("cryptoType", None)
if crypto_type is None:
    sys.exit(0)
if crypto_type != 1:
    sys.exit(
        f"[entrypoint] ERROR: {path} has cryptoType={crypto_type}, expected 1 "
        "(SR25519). Refusing to strip it — that would change the key's curve."
    )

with open(path, "w") as fh:
    json.dump(keyfile, fh)
print(f"[entrypoint] Stripped cryptoType=1 from {path} for bittensor-wallet 4.0.1")
PY
}

# --- Write hotkey (private key) ---
if [ -n "${HOTKEY_DATA:-}" ]; then
    echo "[entrypoint] Writing hotkey: ${WALLET_NAME}/${HOTKEY_NAME}"
    echo "${HOTKEY_DATA}" | base64 -d > "${HOTKEY_DIR}/${HOTKEY_NAME}"
    chmod 600 "${HOTKEY_DIR}/${HOTKEY_NAME}"
    strip_crypto_type "${HOTKEY_DIR}/${HOTKEY_NAME}"
else
    echo "[entrypoint] ERROR: HOTKEY_DATA not set - cannot run without hotkey"
    exit 1
fi

# --- Write hotkeypub (public key) ---
if [ -n "${HOTKEYPUB_DATA:-}" ]; then
    echo "${HOTKEYPUB_DATA}" > "${HOTKEY_DIR}/${HOTKEY_NAME}pub.txt"
    chmod 644 "${HOTKEY_DIR}/${HOTKEY_NAME}pub.txt"
    strip_crypto_type "${HOTKEY_DIR}/${HOTKEY_NAME}pub.txt"
fi

# --- Write coldkeypub (public address only) ---
if [ -n "${COLDKEYPUB_DATA:-}" ]; then
    echo "${COLDKEYPUB_DATA}" > "${WALLET_DIR}/coldkeypub.txt"
    chmod 644 "${WALLET_DIR}/coldkeypub.txt"
    strip_crypto_type "${WALLET_DIR}/coldkeypub.txt"
fi

# --- Clear sensitive env vars ---
unset HOTKEY_DATA

echo "[entrypoint] Wallet bootstrapped at ${HOTKEY_DIR}/${HOTKEY_NAME}"
echo "[entrypoint] Starting: $*"
exec "$@"
