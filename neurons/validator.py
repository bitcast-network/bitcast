import time
import os
import wandb
import threading
import bittensor as bt
import random

from bitcast.base.validator import BaseValidatorNeuron
from bitcast.validator import forward
from bitcast.validator.utils.config import __version__, WANDB_PROJECT
from core.auto_update import run_auto_update

class Validator(BaseValidatorNeuron):
    """
    Your validator neuron class. You should use this class to define your validator's behavior. In particular, you should replace the forward function with your own logic.

    This class inherits from the BaseValidatorNeuron class, which in turn inherits from BaseNeuron. The BaseNeuron class takes care of routine tasks such as setting up wallet, subtensor, metagraph, logging directory, parsing config, etc. You can override any of the methods in BaseNeuron if you need to customize the behavior.

    This class provides reasonable default behavior for a validator such as keeping a moving average of the scores of the miners and using them to set weights at the end of each epoch. Additionally, the scores are reset for new hotkeys at the end of each epoch.
    """

    def __init__(self, config=None):
        super(Validator, self).__init__(config=config)

        # Initialize wandb only if disable_set_weights is False
        if not self.config.neuron.disable_set_weights:
            try:
                wandb.init(
                    entity="bitcast_network",
                    project=WANDB_PROJECT,
                    name=f"validator-{self.uid}-{__version__}",
                    config=self.config,
                    reinit="finish_previous"
                )
            except Exception as e:
                bt.logging.error(f"Failed to initialize wandb run: {e}")

        bt.logging.info("load_state()")
        self.load_state()

    async def forward(self):
        """
        Validator forward pass. Consists of:
        - Generating the query
        - Querying the miners
        - Getting the responses
        - Rewarding the miners
        - Updating the scores
        """
        return await forward(self)

def auto_update_loop(config):
    while True:
        if not config.neuron.disable_auto_update:
            run_auto_update('validator')
        sleep_time = random.randint(600, 900)  # Random time between 10 and 15 minutes
        time.sleep(sleep_time)

if __name__ == "__main__":

    # Start the auto-update loop in a separate thread
    with Validator() as validator:
        update_thread = threading.Thread(target=auto_update_loop, args=(validator.config,), daemon=True)
        update_thread.start()

        while True:
            bt.logging.info(f"Validator running | uid {validator.uid} | {time.time()}")
            time.sleep(30)