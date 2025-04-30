import numpy as np
from typing import List
import bittensor as bt



def calculate_brief_emissions_scalar(yt_stats_list: List[dict], briefs: List[dict]) -> dict:
    """
    Calculate the emissions scalar for each brief based on total minutes watched and burn parameters.
    
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
            if isinstance(stats, dict) and "videos" in stats:
                videos = stats["videos"]
                if isinstance(videos, dict):
                    # Handle case where videos is a dictionary
                    for video_id, video_data in videos.items():
                        if isinstance(video_data, dict):
                            minutes = float(video_data.get("estimatedMinutesWatched", 0))
                            matching_briefs = video_data.get("matching_brief_ids", [])
                            for brief_id in matching_briefs:
                                brief_total_minutes[brief_id] = brief_total_minutes.get(brief_id, 0) + minutes
                elif isinstance(videos, list):
                    # Handle case where videos is a list
                    for video_data in videos:
                        if isinstance(video_data, dict):
                            minutes = float(video_data.get("estimatedMinutesWatched", 0))
                            matching_briefs = video_data.get("matching_brief_ids", [])
                            for brief_id in matching_briefs:
                                brief_total_minutes[brief_id] = brief_total_minutes.get(brief_id, 0) + minutes
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
        matrix (np.ndarray): Input matrix where each column sums to 1
        yt_stats_list (List[dict]): List of YouTube statistics from all miners
        briefs (List[dict]): List of briefs containing max_burn and burn_decay parameters
        
    Returns:
        np.ndarray: Scaled matrix where each column still sums to 1
    """
    # Validate matrix sums to approximately 1
    col_sums = np.sum(matrix, axis=0)
    if not np.allclose(col_sums, 1.0, rtol=1e-5):
        bt.logging.warning(f"Input matrix sum {np.sum(matrix)} is not close to 1")
        
    # Validate first row contains only zeros
    if not np.allclose(matrix[0, :], 0.0):
        bt.logging.warning("First row of matrix contains non-zero values")
        
    # Get emission scalars for each brief
    brief_scalars = calculate_brief_emissions_scalar(yt_stats_list, briefs)
    
    # Convert brief scalars to list matching matrix columns
    scalars = []
    for brief in briefs:
        scalars.append(brief_scalars[brief["id"]])
    scalars = np.array(scalars)
    
    # Create output matrix
    scaled_matrix = matrix.copy()
    
    # Special case: if matrix is all zeros, distribute rewards equally in first row
    if np.allclose(matrix, 0.0):
        scaled_matrix[0, :] = 1.0 / matrix.shape[1]  # Equal split between columns
        return scaled_matrix
    
    # Scale non-first rows by scalars
    scaled_matrix[1:, :] *= scalars[None, :]
    
    # Set first row to make columns sum to 1
    col_sums = np.sum(scaled_matrix[1:, :], axis=0)
    scaled_matrix[0, :] = 1.0 - col_sums
    
    return scaled_matrix
