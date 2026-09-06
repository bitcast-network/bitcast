"""Structural Protocols over the bittensor chain objects.

This is the mockability seam: everything outside ``chain/`` that needs chain
state depends on these Protocols, so the full test suite runs with plain
fakes — no subtensor, no network. ``bt.Subtensor`` and ``bt.Metagraph``
satisfy them structurally at runtime.
"""

from typing import Any, Protocol

import numpy as np

# Numpy arrays are handed around without dtype guarantees (float32 scores can
# become float64 after a metagraph-growth resize — ported behavior).
NDArray = np.ndarray[Any, np.dtype[Any]]


class MetagraphLike(Protocol):
    """The metagraph surface the validator actually uses."""

    @property
    def n(self) -> Any: ...  # int-like (np scalar with .item())

    @property
    def uids(self) -> NDArray: ...

    @property
    def hotkeys(self) -> list[str]: ...

    @property
    def axons(self) -> list[Any]: ...

    @property
    def last_update(self) -> NDArray: ...

    def sync(self, subtensor: Any = None) -> None: ...


class SubtensorLike(Protocol):
    """The subtensor surface the validator actually uses."""

    @property
    def chain_endpoint(self) -> str: ...

    def get_current_block(self) -> int: ...

    def metagraph(self, netuid: int) -> Any: ...

    def is_hotkey_registered(self, hotkey_ss58: str, netuid: int | None = None, block: int | None = None) -> bool: ...

    def min_allowed_weights(self, netuid: int, block: int | None = None) -> int | None: ...

    def max_weight_limit(self, netuid: int, block: int | None = None) -> float | None: ...

    def set_weights(
        self,
        wallet: Any,
        netuid: int,
        uids: Any,
        weights: Any,
        *,
        wait_for_finalization: bool = False,
        wait_for_inclusion: bool = False,
        version_key: int = 0,
    ) -> Any:
        """bt 10.5.0 returns an ``ExtrinsicResponse`` exposing ``.success`` and
        ``.message`` (and unpacking to ``(success, message)``). ``weights.py``
        reads the attributes, so fakes must provide them — see
        ``tests.conftest.FakeExtrinsicResponse``."""
        ...

    def serve_axon(self, netuid: int, axon: Any) -> Any: ...


class WalletLike(Protocol):
    """The wallet surface used for signing and identity."""

    @property
    def hotkey(self) -> Any: ...  # keypair with .ss58_address and .sign()
