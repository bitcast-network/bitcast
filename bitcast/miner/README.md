# Bitcast Miner

A YouTube token server which enables mining on the Bitcast subnet. Responds to validator requests with a temporary read access token for the YouTube APIs.

> **Notice**  
> Your YouTube channel is a valuable asset. Bitcast aims to create meaningful opportunities for creators but early-stage Bittensor subnets can be unpredictable environments. We encourage you to participate thoughtfully, as we will not take any responsibility for unexpected changes to your channel’s performance.

---

## 🎥 Content Requirements

> **Don’t register until you hit these!**  
> **Note: Content requirements are likely to increase over time**

1. **YouTube account**  
   - 21+ days old
   - ≥ 100 subscribers
   - ≥ 10% average retention (over the last 90 days)
   - ≥ 1000 minutes watched (over the last 90 days)

2. **Videos**  
   - Public  
   - ≥ 10% retention  
   - Auto-generated captions only  
   - Matches at least one [content brief](http://dashboard.bitcast.network/briefs)  
   - Published no more than **3 days** before the brief content window starts

**Tip:** Test your script against any brief in our [dashboard tool](http://dashboard.bitcast.network/).

---

## 💻 System Requirements

- **CPU:** 2 cores  
- **RAM:** 4 GB  

Make sure your server meets these before you start.

---

## 🚀 Installation

1. **Clone repo**  
   ```bash
   git clone git@github.com:bitcast-network/bitcast.git
   cd bitcast
   ```

2. **Setup environment & venv**  
   ```bash
   chmod +x scripts/setup_env.sh
   ./scripts/setup_env.sh
   ```  
   This creates a Python virtual environment at `../venv_bitcast/` and installs dependencies.

---

## 🔑 Google Console Setup

1. **Create a project**  
   - Go to [Google Cloud Console](https://console.cloud.google.com/)  
   - Click **Select a project → New Project**  
   - Name it **bitcast-miner**, then **Create**.  
   - After creation, open the **project selector** dropdown in the top bar and select **bitcast_miner**.

2. **Enable APIs**  
   - Open **APIs & Services → Library**  
   - Search for **YouTube Data API v3** and **YouTube Analytics API**  
   - Click **Enable** on each.

3. **Configure OAuth consent screen**  
   - Go to **APIs & Services → OAuth consent screen**  
   - Click **Get Started**.  
   - App name: **bitcast-miner**  
   - Support email: *your email*  
   - Audience: **External**  
   - Contact email: *your email*  
   - Agree to Google’s data policy and terms  
   - Click **Create**.

4. **Create OAuth credentials**  
   - Go to **Overview → Metrics → Create OAuth client**  
   - Application type: **Desktop app**  
   - Name it **bitcast-miner**  
   - Click **Create**.  
   - Download the JSON and save as  
     ```
     bitcast/miner/secrets/client_secret.json
     ```

5. **Publish App**  
   - Go to **Audience**.
   - Click **Publish App**.

---

## 🚀 Run Miner

**Important:** The OAuth consent screen requires a browser environment. Run the miner from a terminal capable of launching your default web browser (e.g., VS Code). Headless or minimal terminals (PuTTY, Terminus, mobaXterm) will not work.

3. **Configure Environment**
   ```bash
   cp bitcast/miner/.env.example bitcast/miner/.env
   ```
   Edit `.env` with your wallet information:
   - `WALLET_NAME`: Your Bittensor wallet name
   - `HOTKEY_NAME`: Your validator hotkey name

2. **Open port 8091**  
   Ensure your firewall or cloud security group allows inbound on **8091**.

3. **Start miner**  
   ```bash
   chmod +x scripts/run_miner.sh
   ./scripts/run_miner.sh
   ```
   - The first run will open an OAuth screen in your browser.  
   - Authorize **all** requested YouTube access scopes for the account you wish to connect.  
   - If it hangs or doesn’t appear, rerun `./scripts/run_miner.sh`.  

4. **pm2 Launch & Health Check**  
   The `run_miner.sh` script uses **pm2** to manage the miner process.  
   - List running processes:  
     ```bash
     pm2 list
     ```  
   - View logs in real-time:  
     ```bash
     pm2 logs bitcast_miner
     ```  
   - Check detailed status:  
     ```bash
     pm2 show bitcast_miner
     ```  
   - If the miner isn’t running, you can restart it:  
     ```bash
     pm2 restart bitcast_miner
     ```

---

## 🚀 Miner Registration

1. **Activate the virtual environment**  
   ```bash
   source ../venv_bitcast/bin/activate
   ```

2. **Register Bittensor Wallet & Subnet**  
   > **Run these from within the activated venv.**  
   1. **Create wallets**  
      ```bash
      btcli wallet new_coldkey --wallet.name <WALLET_NAME>
      btcli wallet new_hotkey  --wallet.name <WALLET_NAME> --wallet.hotkey <HOTKEY_NAME>
      ```  
   2. **Register on subnet**  
      ```bash
      btcli subnet register \
        --netuid 93 \
        --wallet.name <WALLET_NAME> \
        --hotkey <HOTKEY_NAME>
      ```

---

## ℹ️ General Notes

- **2-day emissions delay:** You’ll begin receiving miner emissions **2 days** after the miner starts.  
- **Validator polling:** Each validator sends a request roughly every **4 hours**.  
- **Video processing limit:** A maximum of **50 recent videos** will be processed per YouTube account.  
- **Process visibility:** Validator logs can be viewed in the [bitcast wandb project](https://wandb.ai/bitcast_network/bitcast_vali_logs?nw=nwuserwill_bitcast)  
- **Single YouTube account:** Each miner instance supports only **one** YouTube account. To connect multiple accounts, run multiple miners.  
- **Auto-updates:** The codebase has auto-update enabled by default.

---

## 🔄 Staying Healthy

- Once healthy, your miner auto-detects and scores new uploads.  
- **Briefs change**—check [content briefs](http://dashboard.bitcast.network/briefs) regularly.  

Happy mining! 🚀  
