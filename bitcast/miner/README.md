# Bitcast Miner

A YouTube token server which enables mining on the Bitcast subnet. Responds to validator requests with a temporary read access token for the YouTube APIs.

---

## 🎥 Content Requirements

> **Don’t register until you hit these!**
> **Note: Content requirements are likely to increase over time**

1. **YouTube account**  
   - ≥ 50 subscribers  
   - ≥ 10% average retention (over the last 365 days)  
   - ≥ 1000 minutes watched (over the last 365 days)

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

## 🔑 Google Console Setup

1. **Create a project**  
   - Go to [Google Cloud Console](https://console.cloud.google.com/)  
   - Click **Select a project → New Project**  
   - Name it **bitcast_miner**, then **Create**.  
   - After creation, open the **project selector** dropdown in the top bar and select **bitcast_miner**.

2. **Enable APIs**  
   - Open **APIs & Services → Library**  
   - Search for **YouTube Data API v3** and **YouTube Analytics API**  
   - Click **Enable** on each.

3. **Configure OAuth consent screen**  
   - Click **Get Started**.  
   - Go to **APIs & Services → OAuth consent screen**  
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

---

## 🚀 Installation & Miner Registration

1. **Clone repo**  
   ```bash
   git clone <REPO_URL>
   cd bitcast
   ```

2. **Setup environment & venv**  
   ```bash
   chmod +x scripts/setup_env.sh
   ./scripts/setup_env.sh
   ```  
   This creates a Python virtual environment at `bitcast/venv_bitcast/` and installs dependencies.

3. **Activate the virtual environment**  
   ```bash
   source venv_bitcast/bin/activate
   ```

4. **Register Bittensor Wallet & Subnet**  
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

## 🚀 Run Miner

1. **Configure miner script**  
   - Edit `scripts/run_miner.sh`  
     - Set `WALLET_NAME=<your wallet name>`  
     - Set `HOTKEY_NAME=<your hotkey name>`  
     - (Optional) change port or disable auto-updates  

2. **Open port 8091**  
   Make sure your server’s firewall or cloud security group allows inbound on **8091**.

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

## ℹ️ General Notes

- **2‑day emissions delay:** You’ll begin receiving miner emissions **2 days** after the miner starts.  
- **Validator polling:** Each validator sends a request roughly every **4 hours**.  
- **Process visibility:** Validator logs are pushed to Weights & Biases—check your W&B dashboard for full process logs: `<YOUR_WANDB_RUN_URL>`  
- **Single YouTube account:** Each miner instance supports only **one** YouTube account. To connect multiple accounts, run multiple miners.
- **Auto‑updates:** The codebase has auto-update enabled by default.

---

## 🔄 Staying Healthy

- Once healthy, your miner auto-detects and scores new uploads.  
- **Briefs change**—check [content briefs](http://dashboard.bitcast.network/briefs) regularly.  

Happy mining! 🚀  
