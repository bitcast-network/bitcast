import os
import sys
from dotenv import load_dotenv
from pathlib import Path
import bittensor as bt

env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# required
BITCAST_BRIEFS_ENDPOINT = os.getenv('BITCAST_BRIEFS_ENDPOINT')
BITCAST_STATS_ENDPOINT = os.getenv('BITCAST_STATS_ENDPOINT')
RAPID_API_KEY = os.getenv('RAPID_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
WANDB_API_KEY = os.getenv('WANDB_API_KEY')

# Check if any required variables are missing
required_vars = {
    'RAPID_API_KEY': RAPID_API_KEY,
    'OPENAI_API_KEY': OPENAI_API_KEY,
    'BITCAST_BRIEFS_ENDPOINT': BITCAST_BRIEFS_ENDPOINT,
    'WANDB_API_KEY': WANDB_API_KEY
}

missing_vars = [var for var, value in required_vars.items() if value is None or value == '']
if missing_vars:
    sys.stderr.write(f"Error: Missing required environment variables: {', '.join(missing_vars)}\n")
    sys.exit(1)

# optional
DISABLE_LLM_CACHING = os.getenv('DISABLE_LLM_CACHING', 'False').lower() == 'true'
LANGCHAIN_API_KEY = os.getenv('LANGCHAIN_API_KEY')
LANGCHAIN_TRACING_V2 = os.getenv('LANGCHAIN_TRACING_V2')

# youtube channel
YT_MIN_SUBS = 50
YT_MIN_CHANNEL_AGE = 0
YT_MIN_CHANNEL_WATCH_HOURS = 0
YT_MIN_CHANNEL_RETENTION = 10

# youtube video
YT_MIN_VIDEO_RETENTION = 10

# youtube scoring
YT_ROLLING_WINDOW = 7
YT_REWARD_DELAY = 2

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
bt.logging.info(f"YT_MIN_CHANNEL_WATCH_HOURS: {YT_MIN_CHANNEL_WATCH_HOURS}")
bt.logging.info(f"YT_MIN_CHANNEL_RETENTION: {YT_MIN_CHANNEL_RETENTION}")
bt.logging.info(f"YT_MIN_VIDEO_RETENTION: {YT_MIN_VIDEO_RETENTION}")
bt.logging.info(f"YT_ROLLING_WINDOW: {YT_ROLLING_WINDOW}")
bt.logging.info(f"YT_REWARD_DELAY: {YT_REWARD_DELAY}")
bt.logging.info(f"TRANSCRIPT_MAX_RETRY: {TRANSCRIPT_MAX_RETRY}")
bt.logging.info(f"UPDATE_BLOCKS: {VALIDATOR_CYCLE}")
bt.logging.info(f"DISCRETE_MODE: {DISCRETE_MODE}")