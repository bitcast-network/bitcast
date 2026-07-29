FROM python:3.11-slim

WORKDIR /app

# System deps for bittensor (substrate-interface needs these)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libssl-dev pkg-config curl git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for runtime security
RUN useradd -m -s /bin/bash bitcast
RUN chown -R bitcast:bitcast /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the package
COPY setup.py README.md .
COPY bitcast/ bitcast/
RUN pip install --no-cache-dir -e .

# Source code (neurons, core)
COPY neurons/ neurons/
COPY core/ core/

# Entrypoint script (bootstraps wallet from secrets)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Fix ownership: COPY runs as root, so re-chown so the non-root user can
# write cache directories (e.g. /app/bitcast/cache/) at runtime.
RUN chown -R bitcast:bitcast /app

# Bittensor wallet path (non-root)
ENV BT_WALLET_PATH=/home/bitcast/.bittensor/wallets
ENV HOME=/home/bitcast

USER bitcast

# Entrypoint and command are set via Terraform task definition.
ARG ROLE=miner
ENTRYPOINT ["/entrypoint.sh"]
