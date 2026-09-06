"""Wire protocol between Bitcast validators and miners."""

import bittensor as bt


class AccessTokenSynapse(bt.Synapse):
    """Request/response carrying YouTube OAuth access tokens.

    A validator sends this synapse with ``YT_access_tokens=None``; the miner
    fills in its current access tokens so the validator can evaluate the
    associated YouTube channels.
    """

    YT_access_tokens: list[str] | None = None
