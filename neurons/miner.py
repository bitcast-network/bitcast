import time
import typing
import bittensor as bt
import threading
import random

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
        # Initialize token management
        token_mgmt.init()

        if self.config.dev_mode:
            bt.logging.info("DEV MODE ENABLED")

    async def forward(
        self, synapse: AccessTokenSynapse
    ) -> AccessTokenSynapse:
        """
        Processes the incoming AccessTokenSynapse by loading access tokens using token management logic.
        
        Args:
            synapse (template.protocol.AccessTokenSynapse): The synapse object representing the token request.
        
        Returns:
            template.protocol.AccessTokenSynapse: The same synapse object with the access tokens set.
        """
        # Use token_mgmt logic to load (and refresh if needed) all access tokens.
        synapse.YT_access_tokens = token_mgmt.load_token()
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

        bt.logging.info(f"Checking request from hotkey: {synapse.dendrite.hotkey}")

        if synapse.failed_verification:
            bt.logging.warning(f"Request failed signature verification")
            return True, "Signature verification failed"
        
        # Signature must exist and not be a bypass attempt
        signature = synapse.dendrite.signature if synapse.dendrite else None
        if not signature or not isinstance(signature, str) or signature.lower().strip() in ['null', 'none', 'false', '0', 'undefined', '']:
            bt.logging.warning(f"Missing or invalid signature: {signature}")
            return True, "Missing required signature"
        
        bt.logging.info(f"Received synapse: {synapse}")
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            bt.logging.warning("Received a request without a dendrite or hotkey.")
            return True, "Missing dendrite or hotkey"

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
        sleep_time = random.randint(600, 900)  # Random time between 10 and 15 minutes
        time.sleep(sleep_time)

if __name__ == "__main__":

    # Start the auto-update loop in a separate thread
    with Miner() as miner:
        update_thread = threading.Thread(target=auto_update_loop, args=(miner.config,), daemon=True)
        update_thread.start()

        while True:
            bt.logging.info(f"Miner running... {time.time()}")
            time.sleep(5)
