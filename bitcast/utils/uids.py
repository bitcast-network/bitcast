import random
import bittensor as bt
import numpy as np
from typing import List


def check_uid_availability(
    metagraph: "bt.metagraph.Metagraph", uid: int, vpermit_tao_limit: int
) -> bool:
    """Check if uid is available. The UID should be available if it is serving and has less than vpermit_tao_limit stake
    Args:
        metagraph (:obj: bt.metagraph.Metagraph): Metagraph object
        uid (int): uid to be checked
        vpermit_tao_limit (int): Validator permit tao limit
    Returns:
        bool: True if uid is available, False otherwise
    """
    # Filter non serving axons.
    if not metagraph.axons[uid].is_serving:
        return False
    # Filter validator permit > 1024 stake.
    if metagraph.validator_permit[uid]:
        if metagraph.S[uid] > vpermit_tao_limit:
            return False
    # Available otherwise.
    return True


def get_all_uids(self, exclude: List[int] = None) -> np.ndarray:
    """Returns all uids from the metagraph, excluding specified ones.
    Args:
        exclude (List[int]): List of uids to exclude from the result.
    Returns:
        uids (np.ndarray): All uids excluding specified ones.
    """
    avail_uids = []

    for uid in range(self.metagraph.n.item()):
        uid_is_not_excluded = exclude is None or uid not in exclude

        if uid_is_not_excluded:
            avail_uids.append(uid)

    # Ensure uid 0 is always included at the start of the list
    if 0 not in avail_uids:
        avail_uids.insert(0, 0)

    uids = np.array(avail_uids)
    return uids
