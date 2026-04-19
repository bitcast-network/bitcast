FROM python:3.11-slim

WORKDIR /app

# System deps for bittensor (substrate-interface needs these)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libssl-dev pkg-config curl git \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the package
COPY setup.py .
COPY bitcast/ bitcast/
RUN pip install --no-cache-dir -e .

COPY neurons/ neurons/
COPY core/ core/

# Bittensor wallet data (hotkey/coldkey)
ENV BT_WALLET_PATH=/root/.bittensor/wallets

# Entrypoint
ENTRYPOINT ["python", "neurons/miner.py"]
