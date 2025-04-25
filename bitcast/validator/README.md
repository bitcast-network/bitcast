# Validator

## System Requirements

For validation, a validator machine will need:

- **CPU**: 2 cores
- **RAM**: 4 GB

Ensure that your machine meets these requirements before proceeding with the setup.

---

Create a bittensor wallet and register it to the subnet (~/.bittensor/wallets)

For installation of btcli, check [this guide](https://github.com/opentensor/bittensor/blob/master/README.md#install-bittensor-sdk)
```
btcli subnet register --netuid <desired netuid> --wallet.name  <wallet name> --hotkey <your hotkey>
```

## Installation

#### Step 1: Clone Git repo

```
git clone X
```

#### Step 2: Install Required Tools

```
cd bitcast && chmod +x *validator.sh && ./setup_env_validator.sh
```

#### Step 3: Setup ENV
```
cp validator/.env.example validator/.env
```

Replace with your information for `WALLET_NAME`, `HOTKEY_NAME`, `RAPID_API_KEY`, `OPENAI_API_KEY`.
If you want you can use different port for `VALIDATOR_PORT`.

#### Step 4: Run Validator on pm2

```
./run_validator.sh
```

Note: Auto Update will be enabled by default.