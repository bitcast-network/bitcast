import requests
import bittensor as bt
from datetime import datetime, timezone
from bitcast.validator.config import BITCAST_BRIEFS_ENDPOINT

def get_briefs(all: bool = False):
    """
    Fetches the briefs from the server.

    :param all: If True, returns all briefs without filtering;
                if False, only returns briefs where the current UTC date is between start and end dates (inclusive).
    :return: List of brief objects
    """
    try:
        response = requests.get(BITCAST_BRIEFS_ENDPOINT)
        response.raise_for_status()
        briefs_data = response.json()
        
        # Handle both "items" and "briefs" keys in the response
        briefs_list = briefs_data.get("items") or briefs_data.get("briefs") or []
        bt.logging.info(f"Fetched {len(briefs_list)} briefs.")

        filtered_briefs = []
        if not all:
            current_date = datetime.now(timezone.utc).date()
            for brief in briefs_list:
                try:
                    start_date = datetime.strptime(brief["start_date"], "%Y-%m-%d").date()
                    end_date = datetime.strptime(brief["end_date"], "%Y-%m-%d").date()
                    if start_date <= current_date <= end_date:
                        filtered_briefs.append(brief)
                except Exception as e:
                    bt.logging.error(f"Error parsing dates for brief {brief.get('id', 'unknown')}: {e}")
            
            if not filtered_briefs:
                bt.logging.info("No briefs have an active date range.")
        else:
            filtered_briefs = briefs_list

        return filtered_briefs
    except requests.exceptions.RequestException as e:
        bt.logging.error(f"Error fetching briefs: {e}")
        return []