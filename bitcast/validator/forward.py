# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# TODO(developer): Set your name
# Copyright © 2023 <your name>

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

import time
import bittensor as bt

from bitcast.validator.reward import get_rewards
from bitcast.utils.uids import get_all_uids
from bitcast.validator.utils.publish_stats import publish_stats
from bitcast.validator.utils.config import VALIDATOR_WAIT, VALIDATOR_STEPS_INTERVAL

async def forward(self):
    """
    The forward function is called by the validator every time step.

    It is responsible for querying the network and scoring the responses.

    Args:
        self (:obj:`bittensor.neuron.Neuron`): The neuron object which contains all the necessary state for the validator.

    """

    if self.step % VALIDATOR_STEPS_INTERVAL == 0:

        miner_uids = get_all_uids(self)

        bt.logging.info(f"Number of miners to query: {len(miner_uids)}")

        # Get rewards for the responses - now queries miners individually
        rewards, yt_stats_list = await get_rewards(self, miner_uids)

        # Log the rewards for monitoring purposes
        bt.logging.info("UID Rewards:")
        for i, (uid, reward) in enumerate(zip(miner_uids, rewards)):
            bt.logging.info(f"UID {uid}: {reward}")
            yt_stats_list[i]["reward"] = float(reward)
        
        # Extract blacklisted UIDs from the stats
        blacklisted_uids = []
        for i, (uid, yt_stats) in enumerate(zip(miner_uids, yt_stats_list)):
            if yt_stats.get("yt_account", {}).get("blacklisted", False):
                blacklisted_uids.append(uid)
                bt.logging.info(f"UID {uid} is blacklisted")
        
        # Update the scores based on the rewards
        self.update_scores(rewards, miner_uids, blacklisted_uids)

        publish_stats(self.wallet, yt_stats_list, miner_uids)

    time.sleep(VALIDATOR_WAIT)
