# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# TODO(developer): Set your name
# Copyright © 2023 <your name>

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

import time
import typing
import bittensor as bt
import threading

import bitcast
from bitcast.base.miner import BaseMinerNeuron
from bitcast.miner import token_mgmt
from bitcast.protocol import AccessTokenSynapse
from core.auto_update import run_auto_update

class Miner(BaseMinerNeuron):
    """
    Your miner neuron class. This miner now processes a single type of request:
    an AccessTokenSynapse, which it responds to with the same synapse containing the access token.
    The token is managed using the token_mgmt module.
    """

    def __init__(self, config=None):
        super(Miner, self).__init__(config=config)
        # Initialize token management; adjust force_auth as needed.
        token_mgmt.init(force_auth=False)

        if self.config.dev_mode:
            bt.logging.info("DEV MODE ENABLED")

    async def forward(
        self, synapse: AccessTokenSynapse
    ) -> AccessTokenSynapse:
        """
        Processes the incoming AccessTokenSynapse by loading an access token using token management logic.
        
        Args:
            synapse (template.protocol.AccessTokenSynapse): The synapse object representing the token request.
        
        Returns:
            template.protocol.AccessTokenSynapse: The same synapse object with the access token set.
        """
        # Use token_mgmt logic to load (and refresh if needed) the access token.
        synapse.YT_access_token = token_mgmt.load_token()
        return synapse

    async def blacklist(
        self, synapse: AccessTokenSynapse
    ) -> typing.Tuple[bool, str]:
        """
        Determines whether an incoming request should be blacklisted.
        This function remains unchanged.
        """

        if self.config.dev_mode:
            return False, "Blacklist disabled in dev mode"

        if synapse.dendrite.hotkey == "5DAoDtMxVqtMu2Nd5E7QhPEGXDMgrySvE1b3rRT5ARDhfNNK":
            return False, "Owner hotkey accepted"

        bt.logging.info(f"Received synapse: {synapse}")
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            bt.logging.warning("Received a request without a dendrite or hotkey.")
            return True, "Missing dendrite or hotkey"

        # TODO(developer): Define how miners should blacklist requests.
        uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
        if (
            not self.config.blacklist.allow_non_registered
            and synapse.dendrite.hotkey not in self.metagraph.hotkeys
        ):
            # Ignore requests from un-registered entities.
            bt.logging.trace(
                f"Blacklisting un-registered hotkey {synapse.dendrite.hotkey}"
            )
            return True, "Unrecognized hotkey"

        if self.config.blacklist.force_validator_permit:
            # If the config is set to force validator permit, then we should only allow requests from validators.
            bt.logging.info(f"Validator permit: {self.metagraph.validator_permit[uid]}, Stake: {self.metagraph.S[uid]}")
            if not self.metagraph.validator_permit[uid] or self.metagraph.S[uid] < self.config.blacklist.min_stake:
                bt.logging.warning(
                    f"Blacklisting a request from non-validator hotkey {synapse.dendrite.hotkey}"
                )
                return True, "Non-validator hotkey"

        bt.logging.trace(
            f"Not Blacklisting recognized hotkey {synapse.dendrite.hotkey}"
        )
        return False, "Hotkey recognized!"

    async def priority(self, synapse: AccessTokenSynapse) -> float:
        """
        Determines the processing priority for incoming token requests.
        This function remains unchanged.
        """
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            bt.logging.warning(
                "Received a request without a dendrite or hotkey."
            )
            return 0.0

        # TODO(developer): Define how miners should prioritize requests.
        caller_uid = self.metagraph.hotkeys.index(
            synapse.dendrite.hotkey
        )  # Get the caller index.
        priority = float(
            self.metagraph.S[caller_uid]
        )  # Return the stake as the priority.
        bt.logging.trace(
            f"Prioritizing {synapse.dendrite.hotkey} with value: {priority}"
        )
        return priority

def auto_update_loop(config):
    while True:
        if not config.neuron.disable_auto_update:
            run_auto_update('miner')
        time.sleep(300)  # Check for updates every 5 minutes

if __name__ == "__main__":

    # Start the auto-update loop in a separate thread
    with Miner() as miner:
        update_thread = threading.Thread(target=auto_update_loop, args=(miner.config,), daemon=True)
        update_thread.start()

        while True:
            bt.logging.info(f"Miner running... {time.time()}")
            time.sleep(5)
