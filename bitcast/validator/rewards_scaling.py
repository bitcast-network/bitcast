import numpy as np
from typing import List
import bittensor as bt
from bitcast.validator.utils.config import COMMUNITY_RESERVE_PERCENTAGE, COMMUNITY_RESERVE_UID


def allocate_community_reserve(rewards: np.ndarray, uids: List[int]) -> np.ndarray:
    """Allocate community reserve percentage from burn UID to community reserve UID."""
    burn_uid = 0
    
    if len(rewards) == 0:
        return rewards
    
    try:
        uids_array = np.array(uids)
        burn_uid_idx = np.where(uids_array == burn_uid)[0][0]  
        reserve_idx = np.where(uids_array == COMMUNITY_RESERVE_UID)[0][0]
        
        allocation = min(COMMUNITY_RESERVE_PERCENTAGE, rewards[burn_uid_idx])
        rewards = rewards.copy()
        rewards[burn_uid_idx] -= allocation
        rewards[reserve_idx] += allocation
        
        bt.logging.info(f"Allocated {allocation:.4f} from burn UID {burn_uid} to reserve UID {COMMUNITY_RESERVE_UID}")
        
    except (ValueError, IndexError):
        bt.logging.warning("burn UID or community reserve UID not found")
    except Exception as e:
        bt.logging.error(f"Error in community reserve allocation: {e}")
    
    return rewards
