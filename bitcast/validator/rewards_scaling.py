import numpy as np
from typing import List
import bittensor as bt
from bitcast.validator.utils.config import COMMUNITY_RESERVE_PERCENTAGE, COMMUNITY_RESERVE_UID



def calculate_brief_emissions_scalar(yt_stats_list: List[dict], briefs: List[dict]) -> dict:
    """
    Calculate the emissions scalar for each brief based on total minutes watched and burn parameters.
    Only counts stats from vetted channels (where channel_vet_result is True).
    
    Args:
        yt_stats_list (List[dict]): List of YouTube statistics from all miners
        briefs (List[dict]): List of briefs containing max_burn and burn_decay parameters
        
    Returns:
        dict: Dictionary mapping brief IDs to their emission scalars (0-1)
    """
    # First calculate total minutes per brief
    brief_total_minutes = {}
    for stats in yt_stats_list:
        try:
            if not isinstance(stats, dict):
                continue
            
            # Process nested account structure (account_1, account_2, etc.)
            for key, value in stats.items():
                if key.startswith("account_") and isinstance(value, dict):
                    if "yt_account" in value and "videos" in value:
                        account_stats = value
                        
                        # Only process stats from vetted channels
                        if not account_stats.get("yt_account", {}).get("channel_vet_result", False):
                            continue
                            
                        videos = account_stats["videos"]
                        if isinstance(videos, dict):
                            # Handle case where videos is a dictionary
                            for video_id, video_data in videos.items():
                                if isinstance(video_data, dict):
                                    
                                    # Only include videos that passed individual vetting
                                    decision_details = video_data.get("decision_details", {})
                                    if not decision_details.get("video_vet_result", False):
                                        continue

                                    minutes = float(video_data.get("analytics", {}).get("scorableHistoryMins", 0))
                                    
                                    matching_briefs = video_data.get("matching_brief_ids", [])
                                    for brief_id in matching_briefs:
                                        brief_total_minutes[brief_id] = brief_total_minutes.get(brief_id, 0) + (minutes)
        except Exception as e:
            bt.logging.warning(f"Error processing stats: {e}")
            continue
    
    bt.logging.info(f"Total minutes watched per brief: {brief_total_minutes}")
    
    # Calculate emission scalar for each brief
    brief_scalars = {}
    for brief in briefs:
        brief_id = brief["id"]
        max_burn = brief.get("max_burn")
        burn_decay = brief.get("burn_decay")
        total_minutes = brief_total_minutes.get(brief_id, 0.0)
        
        # Return 0 if no minutes watched
        if total_minutes == 0:
            brief_scalars[brief_id] = 0.0
            continue
            
        # Calculate scalar using the formula: (1-max_burn) + max_burn*(1-exp(-burn_decay * x))
        scalar = (1 - max_burn) + max_burn * (1 - np.exp(-burn_decay * total_minutes))
        brief_scalars[brief_id] = scalar
        
    bt.logging.info(f"Emission scalars per brief: {brief_scalars}")
    return brief_scalars

def scale_rewards(matrix: np.ndarray, yt_stats_list: List[dict], briefs: List[dict]) -> np.ndarray:
    """
    Scale rewards matrix based on brief emission scalars.
    Args:
        matrix (np.ndarray): Input matrix where each column sums to 1. Each element should be np.float64.
        yt_stats_list (List[dict]): List of YouTube statistics from all miners
        briefs (List[dict]): List of briefs containing max_burn and burn_decay parameters
    Returns:
        np.ndarray: Scaled matrix where each column still sums to 1, with np.float64 values
    """
    if matrix is None or (isinstance(matrix, np.ndarray) and matrix.size == 0):
        return np.array([])

    matrix_np = np.array(matrix, dtype=np.float64)
    col_sums = np.sum(matrix_np, axis=0)
    
    if not np.isclose(np.sum(col_sums), 1.0, rtol=1e-1):
        bt.logging.warning(f"Input matrix sum {np.sum(col_sums)} is not close to 1")
    if not np.allclose(matrix_np[0, :], 0.0, rtol=1e-5):
        bt.logging.warning("First row of matrix contains non-zero values")

    brief_scalars = calculate_brief_emissions_scalar(yt_stats_list, briefs)
    scalars = np.array([brief_scalars[brief["id"]] for brief in briefs], dtype=np.float64)

    if np.allclose(scalars, 0.0, rtol=1e-5):
        result = np.zeros_like(matrix_np)
        result[0, :] = 1.0 / matrix_np.shape[1]
        return result

    scaled_matrix = matrix_np.copy()
    scaled_matrix[1:, :] *= scalars[np.newaxis, :]
    num_cols = scaled_matrix.shape[1]
    col_sums = np.sum(scaled_matrix[1:, :], axis=0)
    scaled_matrix[0, :] = (1.0 / num_cols) - col_sums
    return scaled_matrix

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
