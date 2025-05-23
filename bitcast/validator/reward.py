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
from bitcast.validator.socials.youtube.youtube_scoring import eval_youtube
from bitcast.validator.socials.youtube import youtube_utils
from bitcast.validator.rewards_scaling import scale_rewards
from bitcast.protocol import AccessTokenSynapse

def reward(uid, briefs, response) -> dict:
    """
    Returns:
    - dict: The YouTube statistics dictionary for the miner.
    """
    bt.logging.info(f"===== Reward function called for UID: {uid} =====")

    # Give the burn UID 0 score for now.
    if uid == 0:
        bt.logging.info(f"Special case: Setting all scores to 0 for UID: {uid}")
        return {"scores": {brief["id"]: 0 for brief in briefs}}

    if not response:
        bt.logging.info("No response provided, returning default scores.")
        return {"scores": {brief["id"]: 0.0 for brief in briefs}}
    
    yt_stats = {"scores": {brief["id"]: 0.0 for brief in briefs}}  # Initialize yt_stats outside the try block

    try:
        # YouTube Scoring
        yt_access_token = response.YT_access_token

        if yt_access_token:
            creds = Credentials(token=yt_access_token)
            yt_stats = eval_youtube(creds, briefs)  # Assign yt_stats directly if successfully retrieved
        else:
            bt.logging.warning(f"YT_access_token not found in response: {response}")

    except Exception as e:
        bt.logging.error(f"Error in reward calculation: {e}")
        # Instead of discarding the partial data, we'll keep the yt_stats object
        # that was initialized above, which will have the default scores
        # but will be properly structured for the publish_stats function

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
        yt_stats = reward(uid, briefs, miner_response)
        yt_stats_list.append(yt_stats)
    
    # Convert dictionary scores to matrix format for normalization
    scores_matrix = []
    for yt_stats in yt_stats_list:
        scores = [yt_stats["scores"].get(brief["id"], 0.0) for brief in briefs]
        scores_matrix.append(scores)
    
    scores_matrix = np.array(scores_matrix)
    
    youtube_utils.reset_scored_videos()
    rewards = normalise_scores(scores_matrix, yt_stats_list, briefs)

    return rewards, yt_stats_list

def normalise_scores(scores_matrix, yt_stats_list, briefs):
    """
    Normalizes the scores matrix in three steps:
    1. Normalize each brief's scores across all miners so each column sums to 1.
    2. Normalize each miner's scores by the weighted number of briefs. Matrix should now sum to 1.
    3. Scale rewards to determine burn portions.
    4. Sum each miner's normalized and scaled scores to produce a final reward per miner.
    """
    res = normalize_across_miners(scores_matrix)
    res = normalize_across_briefs(res, briefs)
    res = scale_rewards(res, yt_stats_list, briefs)  # Apply scaling after normalization but before summing
    return sum_scores(res)

def normalize_across_miners(scores_matrix):
    """
    For each brief (column), normalize scores so the sum across all miners is 1.
    """
    if isinstance(scores_matrix, list):
        scores_matrix = np.array(scores_matrix, dtype=np.float64)
    if scores_matrix.size == 0:
        return np.array([])
    col_sums = scores_matrix.sum(axis=0, keepdims=True)
    col_sums[col_sums == 0] = 1  # Avoid division by zero
    return scores_matrix / col_sums

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

def sum_scores(scores_matrix):
    """
    For each miner (row), sum all normalized scores to get a single reward value.
    """
    if isinstance(scores_matrix, list):
        scores_matrix = np.array(scores_matrix, dtype=np.float64)
    if scores_matrix.size == 0:
        return np.array([])
    return scores_matrix.sum(axis=1)
