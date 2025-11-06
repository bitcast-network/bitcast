import numpy as np
from typing import List
import bittensor as bt
from bitcast.validator.utils.config import SUBNET_TREASURY_PERCENTAGE, SUBNET_TREASURY_UID


def allocate_subnet_treasury(rewards: np.ndarray, uids: List[int]) -> np.ndarray:
    """Allocate subnet treasury percentage from burn UID to subnet treasury UID."""
    burn_uid = 0
    
    if len(rewards) == 0:
        return rewards
    
    try:
        uids_array = np.array(uids)
        burn_uid_idx = np.where(uids_array == burn_uid)[0][0]  
        treasury_idx = np.where(uids_array == SUBNET_TREASURY_UID)[0][0]
        
        allocation = min(SUBNET_TREASURY_PERCENTAGE, rewards[burn_uid_idx])
        rewards = rewards.copy()
        rewards[burn_uid_idx] -= allocation
        rewards[treasury_idx] += allocation
        
        bt.logging.info(f"Allocated {allocation:.4f} from burn UID {burn_uid} to treasury UID {SUBNET_TREASURY_UID}")
        
    except (ValueError, IndexError):
        bt.logging.warning("burn UID or subnet treasury UID not found")
    except Exception as e:
        bt.logging.error(f"Error in subnet treasury allocation: {e}")
    
    return rewards
