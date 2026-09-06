"""Base validator neuron: scoring state, EMA updates, weight setting."""

import asyncio
import contextlib
import copy
from abc import abstractmethod

import bittensor as bt
import numpy as np

from bitcast.config import BitcastConfig
from bitcast.neuron import BaseNeuron
from bitcast.validator import weights
from bitcast.validator.telemetry import MinerScoreTelemetry

_ERROR_BACKOFF = 30.0  # seconds to pause after a failed forward


class BaseValidatorNeuron(BaseNeuron):
    """Maintains per-miner scores and periodically sets weights on chain."""

    def __init__(self, config: BitcastConfig) -> None:
        super().__init__(config)
        self.hotkeys = copy.deepcopy(self.metagraph.hotkeys)
        self.dendrite = bt.Dendrite(wallet=self.wallet)
        self.scores = np.zeros(self.metagraph.n, dtype=np.float32)
        self.telemetry = MinerScoreTelemetry(bt.logging.info)
        self.load_state()

    @abstractmethod
    async def forward(self) -> None:
        """One validation step; implemented by the concrete validator."""

    async def run(self) -> None:
        """Main loop: forward, sync, repeat. Errors back off and continue."""
        self.sync()
        bt.logging.info(f"Validator starting at block {self.block}")
        while True:
            try:
                await self.forward()
                self.sync()
                self.step += 1
            except KeyboardInterrupt:
                bt.logging.info("Validator stopped.")
                return
            except Exception as err:
                bt.logging.error(f"Forward failed: {err!r}")
                self.step += 1
                await asyncio.sleep(_ERROR_BACKOFF)

    def sync(self) -> None:
        """Run the normal chain lifecycle, then best-effort flush score telemetry."""
        try:
            super().sync()
        finally:
            # Observability must not delay or break score persistence/weights.
            with contextlib.suppress(Exception):
                self.telemetry.flush()

    def update_scores(self, rewards: np.ndarray, uids: list[int]) -> None:
        """Fold new rewards into the score vector with an exponential moving average."""
        if len(rewards) == 0 or len(uids) == 0:
            bt.logging.warning("update_scores called with empty rewards or uids")
            return
        if len(rewards) != len(uids):
            raise ValueError(f"rewards ({len(rewards)}) and uids ({len(uids)}) must be the same length")

        rewards = np.nan_to_num(np.asarray(rewards, dtype=np.float32), nan=0.0)
        scores_before = self.scores.copy()
        scattered = np.zeros_like(self.scores)
        scattered[np.asarray(uids, dtype=np.int64)] = rewards

        alpha = self.config.neuron.moving_average_alpha
        self.scores = alpha * scattered + (1 - alpha) * self.scores
        # Telemetry failures cannot affect consensus-critical score math.
        with contextlib.suppress(Exception):
            self.telemetry.record_scores(
                validator_uid=self.uid,
                step=self.step,
                uids=uids,
                rewards=rewards,
                ema_before=scores_before[np.asarray(uids, dtype=np.int64)],
                ema_after=self.scores[np.asarray(uids, dtype=np.int64)],
            )

        bt.logging.debug(f"Updated moving-average scores for {len(uids)} uids")

    def should_set_weights(self) -> bool:
        if self.step == 0 or self.config.neuron.disable_set_weights:
            return False
        return (self.block - self.metagraph.last_update[self.uid]) > self.config.neuron.epoch_length

    def set_weights(self) -> None:
        weights.set_weights(self)

    def resync_metagraph(self) -> None:
        """Sync the metagraph, zeroing scores of replaced hotkeys and resizing."""
        previous_axons = copy.deepcopy(self.metagraph.axons)
        self.metagraph.sync(subtensor=self.subtensor)
        if previous_axons == self.metagraph.axons:
            return

        for uid, hotkey in enumerate(self.hotkeys):
            if uid < len(self.metagraph.hotkeys) and hotkey != self.metagraph.hotkeys[uid]:
                self.scores[uid] = 0.0

        if len(self.hotkeys) < self.metagraph.n:
            grown = np.zeros(self.metagraph.n, dtype=np.float32)
            grown[: len(self.scores)] = self.scores
            self.scores = grown

        self.hotkeys = copy.deepcopy(self.metagraph.hotkeys)
        bt.logging.info(f"Metagraph resynced: n={self.metagraph.n}")

    def save_state(self) -> None:
        np.savez(
            self.config.state_path() / "state.npz",
            step=self.step,
            scores=self.scores,
            hotkeys=np.asarray(self.hotkeys),
        )

    def load_state(self) -> None:
        path = self.config.state_path() / "state.npz"
        if not path.exists():
            bt.logging.info("No saved validator state found; starting fresh.")
            return
        state = np.load(path)
        self.step = int(state["step"])
        saved_scores = state["scores"]
        self.scores[: len(saved_scores)] = saved_scores[: len(self.scores)]
        self.hotkeys = list(state["hotkeys"])
        bt.logging.info(f"Loaded validator state at step {self.step}")
