# Miner

## Content Requirements

In order to mine on the subnet you must have a youtube account and videos which meet the requirements. Do not register until you have met the requirements.

Youtube account:
- 50+ subscribers
- 10%+ average retention

videos:
- Public
- 10%+ retention
- Auto-generated captions (must not have manually entered ones)
- Must match at least one of the briefs from the [content briefs list](http://dashboard.bitcast.network/briefs)
- Must not be released more than 3 days before the content window opens ([content windows per brief](http://dashboard.bitcast.network/briefs))

Test your video script against any briefs using our [dashboard tool](http://dashboard.bitcast.network/).

Your goal is to maximise minutes watched across all videos that hit a brief.
Videos may be long form or shorts.

## System Requirements

- **CPU**: 2 cores
- **RAM**: 4 GB

Ensure that your machine meets these requirements before proceeding with the setup.

# Setup and google console project and app

Obtain client secrets by following [these instructions](https://chatgpt.com/share/67fd9a3c-861c-800a-98ff-05b0eda4fcce) 

When you have downloaded your client secrets json rename it to 'client_secret.json' and paste it into bitcast/miner/secrets/ .

---

Create a bittensor wallet and register it to the subnet (~/.bittensor/wallets)

For installation of btcli, check [this guide](https://github.com/opentensor/bittensor/blob/master/README.md#install-bittensor-sdk)

Create coldkey
```
btcli wallet new_coldkey --wallet.name <wallet name>
```

Create hotkey
```
btcli wallet new_hotkey --wallet.name <wallet name> --wallet.hotkey <hotkey name>
```

Register on the subnet
```
btcli subnet register --netuid 93 --wallet.name  <wallet name> --hotkey <hotkey name>
```

## Installation

#### Step 1: Clone Git repo

```
git clone X
```

#### Step 3: Setup Environment

```
cd bitcast
chmod +x scripts/setup_env.sh && ./scripts/setup_env.sh
```

#### Step 4: Update Wallet Details

Update WALLET_NAME and HOTKEY_NAME within /scrips/run_miner.sh.

(optionally change the port or turn off auto-updates).

#### Step 5: Run Miner on pm2
```
chmod +x scripts/run_miner.sh && ./scripts/run_miner.sh
```

#### Step 6: Authenticate

You should recieve a prompt to open an OAuth screen in your browser. Open the screen and connect your youtube account.

#### Step 7: Continue to Create

If your miner is healthy the validators will be able to find any new content that you publish automatically. Briefs will change over time so ensure you check for new ones regularly.