"""Base miner neuron: axon lifecycle and periodic chain sync."""

import time
import typing
from abc import abstractmethod

import bittensor as bt

from bitcast.config import BitcastConfig
from bitcast.neuron import BaseNeuron
from bitcast.protocol import AccessTokenSynapse

_LOOP_SLEEP = 30.0  # seconds between sync checks


class BaseMinerNeuron(BaseNeuron):
    """Serves an axon answering :class:`AccessTokenSynapse` requests."""

    def __init__(self, config: BitcastConfig) -> None:
        super().__init__(config)
        self.axon = bt.Axon(
            wallet=self.wallet,
            port=config.axon.port,
            ip=config.axon.ip,
            external_ip=config.axon.external_ip,
            external_port=config.axon.external_port,
        )
        self.axon.attach(forward_fn=self.forward, blacklist_fn=self.blacklist, priority_fn=self.priority)

    @abstractmethod
    async def forward(self, synapse: AccessTokenSynapse) -> AccessTokenSynapse:
        """Fill the synapse with this miner's access tokens."""

    @abstractmethod
    async def blacklist(self, synapse: AccessTokenSynapse) -> typing.Tuple[bool, str]:  # noqa: UP006
        """Decide whether to reject the caller. The v10 axon requires the
        exact ``typing.Tuple[bool, str]`` return annotation."""

    @abstractmethod
    async def priority(self, synapse: AccessTokenSynapse) -> float:
        """Rank concurrent requests; higher runs first."""

    def run(self) -> None:
        """Serve the axon and keep the metagraph fresh until interrupted."""
        self.sync()
        self.subtensor.serve_axon(netuid=self.config.netuid, axon=self.axon)
        self.axon.start()
        bt.logging.info(f"Miner axon serving on port {self.config.axon.port} | uid={self.uid}")
        try:
            while True:
                time.sleep(_LOOP_SLEEP)
                if self.should_sync_metagraph():
                    self.sync()
                    self.step += 1
        except KeyboardInterrupt:
            self.axon.stop()
            bt.logging.info("Miner stopped.")
