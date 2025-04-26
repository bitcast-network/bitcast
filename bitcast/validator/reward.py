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
from bitcast.validator.briefs import get_briefs
from bitcast.validator.socials.youtube.youtube_scoring import eval_youtube
from bitcast.validator.socials.youtube import youtube_utils

def reward(uid, briefs, response) -> dict:
    """
    Returns:
    - dict: The YouTube statistics dictionary for the miner.
    """
    bt.logging.info(f"===== Reward function called for UID: {uid} =====")

    if not response:
        bt.logging.info("No response provided, returning default scores.")
        return {"scores": [0.0] * len(briefs)}
    
    yt_stats = {"scores": [0.0] * len(briefs)}  # Initialize yt_stats outside the try block

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

def get_rewards(
    self,
    uids,
    responses: List[str],
) -> np.ndarray:
    """
    Returns:
    - np.ndarray: A matrix of rewards for the given query and responses, with each row corresponding to a response and each column to a brief.
    - List[dict]: A list of YouTube statistics dictionaries for each response.
    """
    briefs = get_briefs()

    yt_stats_list = [reward(uid, briefs, response) for uid, response in zip(uids, responses)]
    scores_matrix = np.array([yt_stats["scores"] for yt_stats in yt_stats_list])

    youtube_utils.reset_scored_videos()

    rewards = normalise_scores(scores_matrix)

    return rewards, yt_stats_list

def normalise_scores(scores_matrix):
    res = normalize_across_miners(scores_matrix)
    res = normalize_across_briefs(res)
    return sum_scores(res)

def normalize_across_miners(scores_matrix):
    if scores_matrix.size == 0:
        return []

    # Transpose the matrix to work column by column
    transposed = list(zip(*scores_matrix))
    normalized_transposed = []

    for column in transposed:
        column_sum = sum(column)
        if column_sum > 0:
            normalized_column = [value / column_sum for value in column]
        else:
            normalized_column = [0] * len(column)
        normalized_transposed.append(normalized_column)

    # Transpose back to the original shape
    normalized_scores_matrix = list(map(list, zip(*normalized_transposed)))
    return normalized_scores_matrix

def normalize_across_briefs(normalized_scores_matrix):
    if not normalized_scores_matrix:
        return []
    num_briefs = len(normalized_scores_matrix[0])
    return [[score / num_briefs for score in row] for row in normalized_scores_matrix]

def sum_scores(scores_matrix):
    final_scores = []
    for row in scores_matrix:
        final_scores.append(sum(row))
    return final_scores