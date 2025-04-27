# Bitcast Validator

A validator service that maintains network integrity by verifying YouTube content performance and disbursing rewards to miners.

---

## 🔍 Validator Responsibilities

Validators are crucial network participants that:
- Obtain temporary YouTube API tokens the miners
- Retrieve channel and video analytics via OAuth
- Verify content submissions and channel eligibility
- Evaluate performance based on engagement metrics
- Distribute on-chain rewards to miners

---

## 💻 System Requirements

- **CPU**: 2 cores
- **RAM**: 4 GB

Ensure your machine meets these requirements before proceeding with setup.

---

## 🔑 API Setup Requirements

1. **RapidAPI Key**
   - Sign up at [RapidAPI](https://rapidapi.com/)
   - Subscribe to required APIs
   - Copy your API key

2. **OpenAI API Key**
   - Get your API key from [OpenAI Platform](https://platform.openai.com/)
   - Ensure you have sufficient credits

3. **Weights & Biases API Key**
   - Sign up at [Weights & Biases](https://wandb.ai/)
   - Get your API key from your account settings

---

## 🚀 Installation & Setup

1. **Clone Repository**
   ```bash
   git clone <REPO_URL>
   cd bitcast
   ```

2. **Setup Environment**
   ```bash
   chmod +x *validator.sh
   ./setup_env_validator.sh
   ```

3. **Configure Environment**
   ```bash
   cp validator/.env.example validator/.env
   ```
   Edit `.env` with your information:
   - `WALLET_NAME`: Your Bittensor wallet name
   - `HOTKEY_NAME`: Your validator hotkey name
   - `RAPID_API_KEY`: Your RapidAPI key
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `WANDB_API_KEY`: Your Weights & Biases API key

4. **Register on Bittensor Network**
   ```bash
   btcli subnet register \
     --netuid 93 \
     --wallet.name <WALLET_NAME> \
     --hotkey <HOTKEY_NAME>
   ```

---

## 🚀 Running the Validator

1. **Start Validator Service**
   ```bash
   ./run_validator.sh
   ```

2. **Process Management with PM2**
   The validator runs under PM2 for process management:
   - View running processes:
     ```bash
     pm2 list
     ```
   - Check logs:
     ```bash
     pm2 logs bitcast_validator
     ```
   - Monitor status:
     ```bash
     pm2 show bitcast_validator
     ```
   - Restart if needed:
     ```bash
     pm2 restart bitcast_validator
     ```

---

## ℹ️ General Notes

- **Auto-updates**: Enabled by default for security and feature updates

---

For support or questions, reach out on our Discord:
[Bitcast Support on Bittensor Discord](https://discord.com/channels/799672011265015819/1362489640841380045)