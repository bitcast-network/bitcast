import typing
import bittensor as bt

class AccessTokenSynapse(bt.Synapse):
    """
    A protocol representation for access token requests and responses.
    This synapse is used to request access tokens from a miner and receive the response.

    Attributes:
    - YT_access_tokens: A list of string values representing YouTube access tokens. 
      Initially None for requests, and set to the actual tokens for responses.
      Maximum number of tokens is configurable.
    """
    YT_access_tokens: typing.Optional[typing.List[str]] = None
