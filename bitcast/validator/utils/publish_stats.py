import requests
import bittensor as bt
from bitcast.validator.utils.config import BITCAST_STATS_ENDPOINT
from typing import List, Dict, Any
import numpy as np
import threading
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime
import json

# Create a single session with retry logic
session = requests.Session()
retry_strategy = Retry(
    total=1,  # Only try once
    backoff_factor=0.1,
    status_forcelist=[500, 502, 503, 504],
)
adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
session.mount("http://", adapter)
session.mount("https://", adapter)

# Create a thread pool with a limited number of workers
thread_pool = ThreadPoolExecutor(max_workers=5, thread_name_prefix="log_publisher")

def publish_stats_payload(json_payload):
    def _publish():
        try:
            response = session.post(BITCAST_STATS_ENDPOINT, json=json_payload)
            data = response.json()  # Attempt to decode JSON response
            
            if response.status_code == 200 and data.get("status") == "ok":
                bt.logging.info("Payload successfully stored as: %s", data.get("stored_as"))
            else:
                bt.logging.error("Failed to store payload. Status code: %s Response: %s", response.status_code, data)
        except Exception as e:
            bt.logging.error("An unexpected error occurred: %s", e)
    
    # Submit the task to the thread pool
    thread_pool.submit(_publish)

def convert_numpy_types(obj):
    """
    Recursively convert NumPy types to Python native types for JSON serialization.
    
    Args:
        obj: The object to convert
        
    Returns:
        The object with NumPy types converted to Python native types
    """
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    else:
        return obj

def clean_video_data(payload):
    """
    Clean and restructure video data to reduce payload size and improve organization.
    Removes description and transcript fields, and restructures check outcomes to be
    with their respective data sections.
    
    Args:
        payload: The payload to clean and restructure
        
    Returns:
        The cleaned and restructured payload
    """
    if isinstance(payload, dict):
        # Check if this is a YouTube result with videos
        if "videos" in payload and isinstance(payload["videos"], dict):
            # Process each video
            for video_id, video_data in payload["videos"].items():
                # Clean video details by removing description and transcript
                if "details" in video_data and isinstance(video_data["details"], dict):
                    details = video_data["details"].copy()
                    if "description" in details:
                        del details["description"]
                    if "transcript" in details:
                        del details["transcript"]
                    video_data["details"] = details
                
                # Preserve daily analytics data if it exists
                if "analytics" in video_data and isinstance(video_data["analytics"], list):
                    # Keep the daily analytics data as is
                    pass
                elif "analytics" in video_data and isinstance(video_data["analytics"], dict):
                    # If it's a single analytics entry (not daily), keep it as is
                    pass
        
        # Recursively clean nested dictionaries
        return {key: clean_video_data(value) for key, value in payload.items()}
    elif isinstance(payload, list):
        # Recursively clean lists
        return [clean_video_data(item) for item in payload]
    else:
        return payload

def publish_stats(wallet: bt.wallet, json_payloads: List[Dict[str, Any]], uids: List[str]):
    """
    Publishes a combined log payload to the stats endpoint, associating each payload with a UID and a validator hotkey.
    The entire payload is signed using the validator's hotkey.
    
    Args:
        wallet (bt.wallet): The wallet to be used for signing and identification.
        json_payloads (List[Dict[str, Any]]): A list of dictionaries containing log payloads.
            Each dictionary should have at least a "message" field.
        uids (List[str]): A list of UIDs corresponding to each payload.
    """
    # Get hotkey for signing
    keypair = wallet.hotkey
    vali_hotkey = keypair.ss58_address
    
    combined_payload = []
    for payload, uid in zip(json_payloads, uids):
        payload['uid'] = uid  # Add UID to each payload
        # Convert NumPy types to Python native types
        converted_payload = convert_numpy_types(payload)
        # Clean video data by removing description and transcript
        cleaned_payload = clean_video_data(converted_payload)
        combined_payload.append(cleaned_payload)
    
    # Calculate total minutes per brief across all miners
    
    timestamp = datetime.utcnow().isoformat()
    final_payload = {
        "vali_hotkey": vali_hotkey, 
        "time": timestamp, 
        "stats": combined_payload,
    }
    
    # Create a message to sign (format: hotkey:timestamp:payload)
    message = f"{vali_hotkey}:{timestamp}:{json.dumps(combined_payload, sort_keys=True)}"
    
    # Sign the message
    signature = keypair.sign(data=message)
    
    # Add signature and signer address to the final payload
    final_payload['signature'] = signature.hex()
    final_payload['signer'] = keypair.ss58_address
    
    publish_stats_payload(final_payload)

if __name__ == "__main__":
    # Initialize wallet for testing
    wallet = bt.wallet()
    keypair = wallet.hotkey
    
    example_payload = {
        "message": "This is a test log entry",
        "level": "test"
    }
    publish_stats_payload(example_payload)
    
    # Example of using the new function with multiple payloads
    example_payloads = [
        {
            "message": "First test log entry",
            "level": "test"
        },
        {
            "message": "Second test log entry",
            "level": "test"
        }
    ]
    uids = ["1", "2"]
    publish_stats(wallet, example_payloads, uids)
