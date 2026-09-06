"""Shared chain-connection and sync lifecycle for miner and validator neurons."""

import sys
import time

import bittensor as bt

from bitcast import __spec_version__
from bitcast.config import BitcastConfig

_BLOCK_TTL = 12.0  # seconds — one block


class BaseNeuron:
    """Wallet, subtensor and metagraph plumbing common to both neuron types.

    Subclasses override :meth:`resync_metagraph`, and validators additionally
    override the weight-setting and state hooks.
    """

    def __init__(self, config: BitcastConfig) -> None:
        self.config = config
        self._configure_logging()

        self.wallet = bt.Wallet(name=config.wallet.name, hotkey=config.wallet.hotkey, path=config.wallet.path)
        self.subtensor = bt.Subtensor(network=config.subtensor.network)
        self.metagraph = bt.Metagraph(netuid=config.netuid, network=config.subtensor.network, subtensor=self.subtensor)
        bt.logging.info(f"Wallet: {self.wallet} | Subtensor: {self.subtensor}")

        self.check_registered()
        self.uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
        self.spec_version = __spec_version__
        self.step = 0
        self._block_cache: tuple[int, float] = (0, 0.0)
        bt.logging.info(f"Running neuron uid={self.uid} on netuid {config.netuid}")

    def _configure_logging(self) -> None:
        bt.logging.set_console()
        if self.config.logging.trace:
            bt.logging.set_trace()
        elif self.config.logging.debug:
            bt.logging.set_debug()

    @property
    def block(self) -> int:
        """Current chain block, cached for one block interval."""
        cached_block, cached_at = self._block_cache
        now = time.monotonic()
        if now - cached_at > _BLOCK_TTL:
            cached_block = self.subtensor.get_current_block()
            self._block_cache = (cached_block, now)
        return cached_block

    def check_registered(self) -> None:
        """Exit if this wallet's hotkey is not registered on the subnet."""
        if not self.subtensor.is_hotkey_registered(
            netuid=self.config.netuid, hotkey_ss58=self.wallet.hotkey.ss58_address
        ):
            bt.logging.error(
                f"Hotkey {self.wallet.hotkey.ss58_address} is not registered on netuid {self.config.netuid}. "
                f"Run `btcli subnets register` and try again."
            )
            sys.exit(1)

    def should_sync_metagraph(self) -> bool:
        """True once ``epoch_length`` blocks have passed since our last update."""
        return (self.block - self.metagraph.last_update[self.uid]) > self.config.neuron.epoch_length

    def should_set_weights(self) -> bool:
        return False

    def set_weights(self) -> None:
        """Hook — validators override."""

    def save_state(self) -> None:
        """Hook — validators override."""

    def resync_metagraph(self) -> None:
        """Refresh metagraph state from the chain."""
        self.metagraph.sync(subtensor=self.subtensor)

    def sync(self) -> None:
        """Keep the neuron in step with the chain: resync, set weights, persist."""
        self.check_registered()
        if self.should_sync_metagraph():
            self.resync_metagraph()
        if self.should_set_weights():
            self.set_weights()
        self.save_state()
