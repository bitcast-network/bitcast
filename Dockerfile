FROM python:3.12-slim

WORKDIR /app

# System deps for bittensor (substrate-interface needs these)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libssl-dev pkg-config curl git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for runtime security + bittensor HOME workaround
RUN useradd -m -s /bin/bash bitcast
RUN chown -R bitcast:bitcast /app

# Install Python deps
COPY pyproject.toml README.md ./
COPY bitcast/ bitcast/
COPY neurons/ neurons/
RUN pip install --no-cache-dir .

# Entrypoint script (bootstraps wallet from secrets)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Bittensor wallet path + HOME for non-root user
ENV BT_WALLET_PATH=/home/bitcast/.bittensor/wallets
ENV HOME=/home/bitcast

USER bitcast

# Entrypoint and command are set via Terraform task definition.
# Default command runs the validator on SN93 mainnet.
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "neurons.validator", "--netuid", "93", "--subtensor.network", "finney"]
