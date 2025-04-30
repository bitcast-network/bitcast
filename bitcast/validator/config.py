import os
import sys
from dotenv import load_dotenv
from pathlib import Path
import bittensor as bt

env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

__version__ = "0.1.0"

# required
BITCAST_SERVER_URL = os.getenv('BITCAST_SERVER_URL', 'http://44.227.253.127')
BITCAST_BRIEFS_ENDPOINT = f"{BITCAST_SERVER_URL}:8013/briefs"
BITCAST_STATS_ENDPOINT = f"{BITCAST_SERVER_URL}:8003/submit"
RAPID_API_KEY = os.getenv('RAPID_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
WANDB_API_KEY = os.getenv('WANDB_API_KEY')
WANDB_PROJECT = os.getenv('WANDB_PROJECT', 'bitcast_vali_logs')

# optional
DISABLE_LLM_CACHING = os.getenv('DISABLE_LLM_CACHING', 'False').lower() == 'true'
LANGCHAIN_API_KEY = os.getenv('LANGCHAIN_API_KEY')
LANGCHAIN_TRACING_V2 = os.getenv('LANGCHAIN_TRACING_V2')

# youtube scoring
YT_LOOKBACK = 365
YT_ROLLING_WINDOW = 7
YT_REWARD_DELAY = 2
YT_VIDEO_RELEASE_BUFFER = 365

# youtube channel
YT_MIN_CHANNEL_AGE = 0
YT_MIN_SUBS = 0
YT_MIN_MINS_WATCHED = 0
YT_MIN_CHANNEL_WATCH_HOURS = 0
YT_MIN_CHANNEL_RETENTION = 0

# youtube video
YT_MIN_VIDEO_RETENTION = 0

# transcript api
TRANSCRIPT_MAX_RETRY = 10

# validation cycle
VALIDATOR_CYCLE = 14400 #4 hours

DISCRETE_MODE = False

# Log out all non-sensitive config variables
bt.logging.info(f"BITCAST_BRIEFS_ENDPOINT: {BITCAST_BRIEFS_ENDPOINT}")
bt.logging.info(f"BITCAST_STATS_ENDPOINT: {BITCAST_STATS_ENDPOINT}")
bt.logging.info(f"DISABLE_LLM_CACHING: {DISABLE_LLM_CACHING}")
bt.logging.info(f"LANGCHAIN_TRACING_V2: {LANGCHAIN_TRACING_V2}")
bt.logging.info(f"YT_MIN_SUBS: {YT_MIN_SUBS}")
bt.logging.info(f"YT_MIN_CHANNEL_AGE: {YT_MIN_CHANNEL_AGE}")
bt.logging.info(f"YT_MIN_MINS_WATCHED: {YT_MIN_MINS_WATCHED}")
bt.logging.info(f"YT_MIN_CHANNEL_WATCH_HOURS: {YT_MIN_CHANNEL_WATCH_HOURS}")
bt.logging.info(f"YT_MIN_CHANNEL_RETENTION: {YT_MIN_CHANNEL_RETENTION}")
bt.logging.info(f"YT_MIN_VIDEO_RETENTION: {YT_MIN_VIDEO_RETENTION}")
bt.logging.info(f"YT_VIDEO_RELEASE_BUFFER: {YT_VIDEO_RELEASE_BUFFER}")
bt.logging.info(f"YT_ROLLING_WINDOW: {YT_ROLLING_WINDOW}")
bt.logging.info(f"YT_REWARD_DELAY: {YT_REWARD_DELAY}")
bt.logging.info(f"YT_LOOKBACK: {YT_LOOKBACK}")
bt.logging.info(f"TRANSCRIPT_MAX_RETRY: {TRANSCRIPT_MAX_RETRY}")
bt.logging.info(f"UPDATE_BLOCKS: {VALIDATOR_CYCLE}")
bt.logging.info(f"DISCRETE_MODE: {DISCRETE_MODE}")