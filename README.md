<p align="center">
  <a href="https://www.bitcast.network/">
    <img src="assets/lockup_gradient.svg" alt="Bitcast Logo" width="800" />
  </a>
</p>

# Bitcast — The Decentralized Creator Economy

Bitcast is a decentralized platform that incentivizes content creators to connect brands with audiences. Creators publish YouTube videos to satisfy defined briefs and earn rewards based on engagement metrics.

---

## ⚙️ High-Level Architecture

- **Miners**: Produce and publish YouTube content for one or more briefs.  
- **Validators**: Obtain temporary OAuth tokens to securely access YouTube Analytics and validate performance.  
- **Brands**: Define and publish content briefs (initially focused on the Bittensor ecosystem).  
- **Briefs Server**: Hosts the [active briefs](https://www.dashboard.bitcast.network/briefs).  
- **Bittensor Network**: Manages on-chain compensation, rewarding Validators and Miners with the [Bitcast alpha token](https://www.coingecko.com/en/coins/bitcast).

---

## 🚀 Getting Started

### For Miners

1. **Review Requirements**  
   Ensure your YouTube account and videos meet the [minimum requirements](bitcast/miner/README.md).

2. **Publish Content**  
   Create videos targeting one or more active briefs.

3. **Earn Rewards**  
   Videos that satisfy briefs are rewarded based on **YouTube Premium revenue** stats.

4. **Agency Operations**  
   Run a single miner with up to 5 YouTube accounts to operate as a content agency, aggregating multiple creators under one mining operation.

See the [Miner Setup Guide](bitcast/miner/README.md) for:
- Installation and configuration  
- OAuth and account integration  
- Miner registration on the network  
- Reward tracking and monitoring

### For Validators

Validators maintain the integrity of the network by:
- Retrieving analytics data via OAuth  
- Verifying content engagement  
- Disbursing on-chain rewards to Miners

Refer to the [Validator Setup Guide](bitcast/validator/README.md) for detailed instructions.

---

## 📊 Scoring & Rewards System

Bitcast employs a dynamic, multi-layered scoring and rewards mechanism to fairly distribute emissions and incentivize high-quality participation. The system is designed to prioritize genuine engagement and prevent manipulation.

### 1. Briefs & Boost Multipliers

- Every [brief](https://dashboard.bitcast.network/) is assigned a **boost** value.
  - **Boost** acts as a multiplier on the score of videos that fulfill the brief, giving higher priority to briefs from sponsors or clients.

### 2. Video Eligibility & Format Types

- **Eligibility:**  
  - Videos must have both their transcript and description fully satisfy the requirements of an active brief.
- **Format Types:**  
  Each brief specifies a required video format, which determines both eligibility and reward scaling:
  - **Dedicated:**  
    - Sponsor’s topic is the main focus (≥80% of video).
    - Each YouTube account can be rewarded for up to **2 videos per dedicated brief** (oldest 2 by publish date).
    - Receives **100% of the reward**.
  - **Ad-Read:**  
    - Sponsor’s message appears as a short, distinct segment.
    - Each YouTube account can be rewarded for up to **5 videos per ad-read brief** (oldest 5 by publish date).
    - Receives **20% of the dedicated reward**.

### 3. Performance Metrics & Anti-Exploitation Controls

- **Reward Calculation:**  
  - Rewards are based on the 7-day moving average of YouTube Premium Revenue (`estimatedRedPartnerRevenue`).
  - For **non-YPP YouTubers**, Premium Revenue is estimated using the video’s minutes watched (`estimatedMinutesWatched`) multiplied by 0.00005.
  - For each eligible video, the (actual or estimated) Premium Revenue is multiplied by a scaling factor to determine the daily reward (in USD).
  - This daily USD reward is then converted into a weight relative to the subnet’s total daily miner emissions (USD).
  - By anchoring rewards to USD, we align with industry-standard metrics (CPM), making the system more transparent and familiar for miners.
- **Lookback & Revenue Cap:**  
  - To prevent exploitation via fake engagement, Bitcast applies a lookback window:
    - For each video, the **average premium revenue over the 7-day period is capped at the median daily revenue for the channel from the previous month**.
    - YouTube audit and remove engagement that they deem to be fake within 1 month. The lookback factors this audit in a prevents exploitation.
- **Reward Timing:**  
  - Only videos matching active briefs are considered.
  - Videos earn rewards for the first 14 days after they are published.
  - There is a **3-day delay** in rewards (to align with YouTube's engagement verification), so rewards always lag behind video engagement by 3 days.

### 4. Emissions Model

- The **boost multiplier** increases the score of qualifying videos.
- Each brief has a **maximum emissions cap**, preventing any single brief from dominating the total emissions.
- **Unclaimed emissions** are automatically allocated to the subnet treasury.

---

## 🤝 Contact & Support

For assistance or questions, join our Discord support channel:

[Bitcast Support on Bittensor Discord](https://discord.com/channels/799672011265015819/1362489640841380045)
