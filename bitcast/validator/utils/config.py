import os
import sys
from dotenv import load_dotenv
from pathlib import Path
import bittensor as bt

env_path = Path(__file__).parents[1] / '.env'
load_dotenv(dotenv_path=env_path)

# Cache Configuration
CACHE_ROOT = Path(__file__).resolve().parents[2] / "cache"
CACHE_DIRS = {
    "openai": os.path.join(CACHE_ROOT, "openai"),
    "briefs": os.path.join(CACHE_ROOT, "briefs"),
    "blacklist": os.path.join(CACHE_ROOT, "blacklist")
}

__version__ = "1.5.2"

# required
BITCAST_SERVER_URL = os.getenv('BITCAST_SERVER_URL', 'http://44.227.253.127')
BITCAST_BRIEFS_ENDPOINT = f"{BITCAST_SERVER_URL}:8013/briefs"
BITCAST_STATS_ENDPOINT = f"{BITCAST_SERVER_URL}:8003/submit"
BITCAST_BLACKLIST_ENDPOINT = f"{BITCAST_SERVER_URL}:8004/blacklist"
BITCAST_BLACKLIST_SOURCES_ENDPOINT = f"{BITCAST_SERVER_URL}:8004/blacklist-sources"
RAPID_API_KEY = os.getenv('RAPID_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
WANDB_API_KEY = os.getenv('WANDB_API_KEY')
WANDB_PROJECT = os.getenv('WANDB_PROJECT', 'bitcast_vali_logs')

# optional
DISABLE_LLM_CACHING = os.getenv('DISABLE_LLM_CACHING', 'False').lower() == 'true'
LANGCHAIN_API_KEY = os.getenv('LANGCHAIN_API_KEY')
LANGCHAIN_TRACING_V2 = os.getenv('LANGCHAIN_TRACING_V2')

# Only run LLM checks on videos that pass all other checks
ECO_MODE = os.getenv('ECO_MODE', 'True').lower() == 'true'

# youtube scoring
YT_LOOKBACK = 90
YT_ROLLING_WINDOW = 7
YT_REWARD_DELAY = 3
YT_VIDEO_RELEASE_BUFFER = 3

# youtube channel
YT_MIN_CHANNEL_AGE = 21
YT_MIN_SUBS = 100
YT_MIN_MINS_WATCHED = 1000
YT_MIN_CHANNEL_RETENTION = 10

# youtube video
YT_MIN_VIDEO_RETENTION = 10

# transcript api
TRANSCRIPT_MAX_RETRY = 10

# validation cycle
VALIDATOR_WAIT = 60 # 60 seconds
VALIDATOR_STEPS_INTERVAL = 240 # 4 hours

DISCRETE_MODE = True

# Log out all non-sensitive config variables
bt.logging.info(f"BITCAST_BRIEFS_ENDPOINT: {BITCAST_BRIEFS_ENDPOINT}")
bt.logging.info(f"BITCAST_STATS_ENDPOINT: {BITCAST_STATS_ENDPOINT}")
bt.logging.info(f"DISABLE_LLM_CACHING: {DISABLE_LLM_CACHING}")
bt.logging.info(f"LANGCHAIN_TRACING_V2: {LANGCHAIN_TRACING_V2}")
bt.logging.info(f"ECO_MODE: {ECO_MODE}")
bt.logging.info(f"YT_MIN_SUBS: {YT_MIN_SUBS}")
bt.logging.info(f"YT_MIN_CHANNEL_AGE: {YT_MIN_CHANNEL_AGE}")
bt.logging.info(f"YT_MIN_MINS_WATCHED: {YT_MIN_MINS_WATCHED}")
bt.logging.info(f"YT_MIN_CHANNEL_RETENTION: {YT_MIN_CHANNEL_RETENTION}")
bt.logging.info(f"YT_MIN_VIDEO_RETENTION: {YT_MIN_VIDEO_RETENTION}")
bt.logging.info(f"YT_VIDEO_RELEASE_BUFFER: {YT_VIDEO_RELEASE_BUFFER}")
bt.logging.info(f"YT_ROLLING_WINDOW: {YT_ROLLING_WINDOW}")
bt.logging.info(f"YT_REWARD_DELAY: {YT_REWARD_DELAY}")
bt.logging.info(f"YT_LOOKBACK: {YT_LOOKBACK}")
bt.logging.info(f"TRANSCRIPT_MAX_RETRY: {TRANSCRIPT_MAX_RETRY}")
bt.logging.info(f"VALIDATOR_WAIT: {VALIDATOR_WAIT}")
bt.logging.info(f"VALIDATOR_STEPS_INTERVAL: {VALIDATOR_STEPS_INTERVAL}")
bt.logging.info(f"DISCRETE_MODE: {DISCRETE_MODE}")