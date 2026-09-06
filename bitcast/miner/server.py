"""The Bitcast miner: serves access tokens to permitted validators."""

import typing

import bittensor as bt

from bitcast.config import BitcastConfig
from bitcast.miner.base import BaseMinerNeuron
from bitcast.miner.token_mgmt import TokenManager
from bitcast.protocol import AccessTokenSynapse


class Miner(BaseMinerNeuron):
    """Answers :class:`AccessTokenSynapse` queries with fresh YouTube tokens."""

    def __init__(self, config: BitcastConfig) -> None:
        super().__init__(config)
        self.token_manager = TokenManager()
        self.token_manager.init()  # fail fast on misconfiguration

    async def forward(self, synapse: AccessTokenSynapse) -> AccessTokenSynapse:
        synapse.YT_access_tokens = await self.token_manager.load_tokens()
        bt.logging.info(f"Served {len(synapse.YT_access_tokens)} access tokens")
        return synapse

    async def blacklist(self, synapse: AccessTokenSynapse) -> typing.Tuple[bool, str]:  # noqa: UP006
        """Reject callers that are not registered validators with sufficient stake."""
        if self.config.dev_mode:
            return False, "Blacklist disabled in dev mode"
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            return True, "Missing dendrite or hotkey"

        hotkey = synapse.dendrite.hotkey
        if hotkey not in self.metagraph.hotkeys:
            if self.config.blacklist.allow_non_registered:
                return False, "Non-registered hotkey allowed"
            return True, "Unrecognized hotkey"

        uid = self.metagraph.hotkeys.index(hotkey)
        if self.config.blacklist.force_validator_permit and (
            not self.metagraph.validator_permit[uid] or self.metagraph.S[uid] < self.config.blacklist.min_stake
        ):
            return True, "Non-validator hotkey"
        return False, "Hotkey recognized"

    async def priority(self, synapse: AccessTokenSynapse) -> float:
        """Serve higher-stake callers first."""
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            return 0.0
        if synapse.dendrite.hotkey not in self.metagraph.hotkeys:
            return 0.0
        uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
        return float(self.metagraph.S[uid])
