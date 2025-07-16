# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# TODO(developer): Set your name
# Copyright © 2023 <your name>

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
import numpy as np
from typing import List
import bittensor as bt
import json
from google.oauth2.credentials import Credentials
from bitcast.validator.utils.briefs import get_briefs
from bitcast.validator.socials.youtube.main import eval_youtube
from bitcast.validator.socials.youtube.utils import state
from bitcast.validator.rewards_scaling import allocate_community_reserve
from bitcast.validator.utils.config import MAX_ACCOUNTS_PER_SYNAPSE, YT_MIN_ALPHA_STAKE_THRESHOLD, YT_SCALING_FACTOR_DEDICATED, YT_SCALING_FACTOR_PRE_ROLL, YT_SMOOTHING_FACTOR, YT_MIN_EMISSIONS
from bitcast.validator.utils.token_pricing import get_bitcast_alpha_price, get_total_miner_emissions
from bitcast.protocol import AccessTokenSynapse

def reward(uid, briefs, response, metagraph=None) -> dict:
    """
    Returns:
    - dict: The YouTube statistics dictionary for the miner with nested account structure.
    """
    bt.logging.info(f"===== Reward function called for UID: {uid} =====")

    # Give the burn UID 0 score for now.
    if uid == 0:
        bt.logging.info(f"Special case: Setting all scores to 0 for UID: {uid}")
        return {"scores": {brief["id"]: 0 for brief in briefs}, "uid": uid}

    if not response:
        bt.logging.info("No response provided, returning default scores.")
        return {"scores": {brief["id"]: 0.0 for brief in briefs}, "uid": uid}
    
    # Initialize the new nested structure
    yt_stats = {
        "scores": {brief["id"]: 0.0 for brief in briefs},  # Aggregated scores across all accounts
        "uid": uid
    }

    # Add metagraph information during initialization if metagraph is provided
    if metagraph is not None:
        add_metagraph_info_to_stats(metagraph, uid, yt_stats)

    try:
        # YouTube Scoring - handle multiple tokens
        yt_access_tokens = response.YT_access_tokens

        if yt_access_tokens and isinstance(yt_access_tokens, list):
            bt.logging.info(f"Received {len(yt_access_tokens)} YouTube access tokens for UID {uid}")
            
            # Limit to maximum configured number of accounts per synapse
            tokens_to_process = yt_access_tokens[:MAX_ACCOUNTS_PER_SYNAPSE]
            
            if len(yt_access_tokens) > MAX_ACCOUNTS_PER_SYNAPSE:
                bt.logging.info(f"Limiting to {MAX_ACCOUNTS_PER_SYNAPSE} accounts per synapse (received {len(yt_access_tokens)})")
            
            bt.logging.info(f"Processing {len(tokens_to_process)} YouTube access tokens for UID {uid}")
            
            for i, yt_access_token in enumerate(tokens_to_process):
                if yt_access_token:
                    account_id = f"account_{i+1}"
                    bt.logging.info(f"Processing {account_id} for UID {uid}")
                    
                    try:
                        creds = Credentials(token=yt_access_token)
                        # Check if minimum stake threshold is met
                        min_stake = False
                        if yt_stats.get("metagraph"):
                            alpha_stake = yt_stats["metagraph"].get("alpha_stake", 0)
                            min_stake = float(alpha_stake) >= YT_MIN_ALPHA_STAKE_THRESHOLD
                        account_stats = eval_youtube(creds, briefs, min_stake)
                        
                        # Store the account-specific data in the nested structure
                        yt_stats[account_id] = {
                            "yt_account": account_stats.get("yt_account", {}),
                            "videos": account_stats.get("videos", {}),
                            "scores": account_stats.get("scores", {brief["id"]: 0.0 for brief in briefs}),
                            "performance_stats": account_stats.get("performance_stats", {})
                        }
                        
                        # Aggregate scores across accounts
                        for brief_id, score in account_stats.get("scores", {}).items():
                            yt_stats["scores"][brief_id] += score
                            
                    except Exception as e:
                        bt.logging.error(f"Error processing {account_id} for UID {uid}: {e}")
                        # Add empty account structure for failed accounts
                        yt_stats[account_id] = {
                            "yt_account": {},
                            "videos": {},
                            "scores": {brief["id"]: 0.0 for brief in briefs},
                            "performance_stats": {}
                        }
                else:
                    bt.logging.warning(f"Empty token found at index {i} for UID {uid}")
        else:
            bt.logging.warning(f"YT_access_tokens not found or not a list in response: {response}")

    except Exception as e:
        bt.logging.error(f"Error in reward calculation: {e}")
        # Keep the initialized structure with default scores

    return yt_stats

async def query_miner(self, uid):

    bt.logging.info(f"Querying UID {uid}")
    
    try:
        # Query individual miner
        response = await self.dendrite(
            # Send the query to the specific miner axon
            axons=[self.metagraph.axons[uid]],
            # Request an access token from the miner
            synapse=AccessTokenSynapse(),
            # Don't deserialize the responses to get the AccessTokenSynapse objects directly
            deserialize=False,
        )
        
        # Extract the single response from the list
        miner_response = response[0] if response else None
        
        bt.logging.info(f"Received response from UID {uid}")
        return miner_response
        
    except Exception as e:
        bt.logging.error(f"Error querying miner UID {uid}: {e}")
        return None

async def get_rewards(
    self,
    uids,
) -> np.ndarray:
    """
    Returns:
    - np.ndarray: A matrix of rewards for the given query and responses, with each row corresponding to a response and each column to a brief.
    - List[dict]: A list of YouTube statistics dictionaries for each response.
    """
    briefs = get_briefs()
    
    # Special case: If briefs is empty, return a list of scores where UID 0 gets 1.0 and others get 0.0
    if not briefs:
        bt.logging.info("No briefs available, returning special case scores.")
        return np.array([1.0 if uid == 0 else 0.0 for uid in uids]), [{"scores": {}} for uid in uids]

    bt.logging.info(f"List of UIDs: {uids}")

    yt_stats_list = []
    
    # Query miners one at a time and process their responses immediately
    for uid in uids:
        # Query the individual miner
        miner_response = await query_miner(self, uid)
        
        # Process the response immediately
        yt_stats = reward(uid, briefs, miner_response, self.metagraph)
    
        yt_stats_list.append(yt_stats)

    # Convert dictionary scores to matrix format for normalization
    scores_matrix = []
    for yt_stats in yt_stats_list:
        # Extract aggregated scores from the new nested structure
        scores = [yt_stats["scores"].get(brief["id"], 0.0) for brief in briefs]
        scores_matrix.append(scores)
    
    scores_matrix = np.array(scores_matrix)
    
    state.reset_scored_videos()

    # Convert raw scores to emission targets (USD)
    emission_targets = calculate_emission_targets(scores_matrix, briefs)
    
    add_matrix_to_stats(yt_stats_list, emission_targets, briefs, "emission_targets")

    # Convert USD emission targets to raw weights based on current token pricing
    raw_weights_matrix = calculate_raw_weights(emission_targets)
    
    add_matrix_to_stats(yt_stats_list, raw_weights_matrix, briefs, "raw_weights")

    # Normalize raw weights into final reward distribution
    rewards, rewards_matrix = normalise_scores(raw_weights_matrix, briefs, uids)
    
    add_matrix_to_stats(yt_stats_list, rewards_matrix, briefs, "rewards")
    
    # Allocate community reserve as the final step
    rewards = allocate_community_reserve(rewards, uids)

    return rewards, yt_stats_list

def calculate_emission_targets(scores_matrix, briefs):
    """
    Transform raw scores into USD daily emission targets through scaling, smoothing, and readjustment.
    This is the USD amount we will aim to reward the miners today.
        
    Returns:
        numpy array: emission target matrix (miners x briefs)
    """
    
    if isinstance(scores_matrix, list):
        scores_matrix = np.array(scores_matrix, dtype=np.float64)
    if scores_matrix.size == 0:
        return np.array([])
    
    emission_targets = scores_matrix.copy()
    
    # Process each brief (column) to calculate emission targets
    for brief_idx, brief in enumerate(briefs):
        if brief_idx >= emission_targets.shape[1]:
            continue
            
        # Apply format-specific scaling factor for emission targeting
        brief_format = brief.get("format", "dedicated")
        scaling_factor = (YT_SCALING_FACTOR_DEDICATED if brief_format == "dedicated" 
                         else YT_SCALING_FACTOR_PRE_ROLL if brief_format == "pre-roll"
                         else YT_SCALING_FACTOR_DEDICATED)
        
        if brief_format not in ["dedicated", "pre-roll"]:
            bt.logging.warning(f"Unknown brief format '{brief_format}', defaulting to dedicated")
        
        # Scale scores for emission distribution
        emission_targets[:, brief_idx] *= scaling_factor
        
        # Store scaled scores for readjustment (after scaling but before smoothing)
        scaled_scores = emission_targets[:, brief_idx].copy()
        
        # Apply smoothing
        pre_smooth_scores = np.maximum(emission_targets[:, brief_idx], 0)
        smoothed_scores = np.power(pre_smooth_scores, YT_SMOOTHING_FACTOR)
        
        # Readjust to maintain scaled proportions (use scaled averages)
        # Use non-negative scaled scores for readjustment to avoid negative emissions
        avg_scaled = np.mean(np.maximum(scaled_scores, 0))
        avg_smoothed = np.mean(smoothed_scores)
        
        if avg_smoothed != 0:
            emission_targets[:, brief_idx] = smoothed_scores * (avg_scaled / avg_smoothed)
        else:
            emission_targets[:, brief_idx] = smoothed_scores
    
    return emission_targets

def calculate_raw_weights(emission_targets_matrix):
    """
    Convert USD emission targets to raw weights based on token pricing.
    Formula: target_usd / alpha_price / total_daily_alpha = raw_weight
    
    Returns:
        numpy array: raw weight matrix (miners x briefs) representing proportion of daily alpha emissions
    """
    if isinstance(emission_targets_matrix, list):
        emission_targets_matrix = np.array(emission_targets_matrix, dtype=np.float64)
    if emission_targets_matrix.size == 0:
        return np.array([])
    
    try:
        alpha_price_usd = get_bitcast_alpha_price()
        total_daily_alpha = get_total_miner_emissions()
        
        bt.logging.info(f"Alpha price: ${alpha_price_usd}, Daily emissions: {total_daily_alpha}")
        
        # Convert USD targets directly to raw weights
        raw_weights = emission_targets_matrix / alpha_price_usd / total_daily_alpha
        
        bt.logging.info(f"Max raw weight: {np.max(raw_weights):.6f}")
        return raw_weights
        
    except Exception as e:
        bt.logging.error(f"Error converting to raw weights: {e}")
        return np.zeros_like(emission_targets_matrix)

def normalise_scores(scores_matrix, briefs, uids):
    """
    Normalizes the scores matrix in two steps:
    1. Clip each brief's scores: scale down if sum > 1, scale up if sum < YT_MIN_EMISSIONS.
    2. Normalize each miner's scores by the weighted number of briefs. Matrix should now sum to 1.
    3. Sum each miner's normalized scores to produce a final reward per miner.
    
    Returns:
        tuple: (final_rewards, normalized_matrix_before_summing)
    """
    res = clip_scores(scores_matrix)
    rewards_matrix = normalize_across_briefs(res, briefs)
    rewards_list = sum_scores(rewards_matrix, uids)
    
    return rewards_list, rewards_matrix

def clip_scores(scores_matrix):
    """
    For each brief (column), clip scores based on their sum:
    - If sum > 1: scale down proportionally to equal 1
    - If sum < YT_MIN_EMISSIONS: scale up to YT_MIN_EMISSIONS
    - If sum = 0: leave unchanged
    """
    if isinstance(scores_matrix, list):
        scores_matrix = np.array(scores_matrix, dtype=np.float64)
    if scores_matrix.size == 0:
        return np.array([])
    
    # Ensure we're working with float64 to avoid casting errors
    result = scores_matrix.astype(np.float64)
    for col_idx in range(result.shape[1]):
        col_sum = result[:, col_idx].sum()
        if col_sum == 0:
            continue
        elif col_sum > 1:
            result[:, col_idx] /= col_sum
        elif col_sum < YT_MIN_EMISSIONS:
            result[:, col_idx] *= (YT_MIN_EMISSIONS / col_sum)
    
    return result

def normalize_across_briefs(normalized_scores_matrix, briefs):
    """
    For each miner (row), normalize scores by the weighted sum of briefs.
    The weights are taken from the briefs' weight field (defaulting to 100 if not specified).
    """
    if isinstance(normalized_scores_matrix, list):
        normalized_scores_matrix = np.array(normalized_scores_matrix, dtype=np.float64)
    if normalized_scores_matrix.size == 0:
        return np.array([])
    
    # Get weights for each brief, defaulting to 100 if not specified
    brief_weights = np.array([brief.get("weight", 100) for brief in briefs])
    total_weight = np.sum(brief_weights)
    
    # Instead of multiplying and then dividing, just divide by the number of briefs
    # when weights are equal (which is the common case)
    if np.all(brief_weights == brief_weights[0]):
        return normalized_scores_matrix / len(briefs)
    
    # For different weights, use the weighted average
    # Apply weights to columns (briefs) instead of rows (miners)
    return normalized_scores_matrix * (brief_weights / total_weight)[np.newaxis, :]

def sum_scores(scores_matrix, uids):
    """
    For each miner (row), sum all normalized scores to get a single reward value.
    Ensures the total scores sum to 1 by setting UID 0 to 1 - sum(other_scores).
    """
    if isinstance(scores_matrix, list):
        scores_matrix = np.array(scores_matrix, dtype=np.float64)
    if scores_matrix.size == 0:
        return np.array([])
    
    # Sum each miner's scores across briefs
    rewards = scores_matrix.sum(axis=1)
    
    # Find the index of UID 0
    uid_0_index = None
    for i, uid in enumerate(uids):
        if uid == 0:
            uid_0_index = i
            break
    
    # If UID 0 exists, set its reward to ensure total sums to 1
    if uid_0_index is not None:
        # Calculate sum of all other rewards
        other_rewards_sum = sum(rewards[i] for i in range(len(rewards)) if i != uid_0_index)
        # Set UID 0's reward to make total sum to 1
        rewards[uid_0_index] = 1.0 - other_rewards_sum
    
    return rewards

def add_metagraph_info_to_stats(metagraph, uid: int, yt_stats: dict) -> None:
    """
    Add metagraph information to the yt_stats dictionary for a given UID.
    
    Args:
        metagraph: The bittensor metagraph object
        uid: The UID to get metagraph information for
        yt_stats: The stats dictionary to add metagraph information to
    """
    try:
        # Stake information
        stake = float(metagraph.S[uid])
        alpha_stake = float(metagraph.alpha_stake[uid]) if hasattr(metagraph, 'alpha_stake') else 0.0
        coldkey = str(metagraph.coldkeys[uid]) if hasattr(metagraph, 'coldkeys') and uid < len(metagraph.coldkeys) else ""
        emission = float(metagraph.emission[uid]) if hasattr(metagraph, 'emission') else 0.0

        yt_stats["metagraph"] = {
            # Stake information
            "stake": stake,
            "alpha_stake": alpha_stake,
            "coldkey": coldkey,
            "emission": emission
        }

    except Exception as e:
        bt.logging.error(f"Error getting metagraph info for UID {uid}: {e}")

def add_matrix_to_stats(yt_stats_list, matrix, briefs, name):
    """
    Add normalized scores per brief to each miner's stats.
    
    Args:
        yt_stats_list: List of miner statistics dictionaries
        normalized_matrix: Normalized matrix (miners x briefs)
        briefs: List of brief dictionaries with IDs
    """
    for i, yt_stats in enumerate(yt_stats_list):
        if i < len(matrix):  # Ensure we don't go out of bounds
            normalized_scores_for_miner = matrix[i]
            yt_stats[name] = {
                brief["id"]: float(normalized_scores_for_miner[j]) 
                for j, brief in enumerate(briefs) 
                if j < len(normalized_scores_for_miner)
            }