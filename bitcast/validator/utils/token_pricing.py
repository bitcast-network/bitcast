import requests
import bittensor as bt
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((requests.exceptions.RequestException, KeyError))
)
def get_bitcast_alpha_price() -> float:
    """
    Get the current BitCast price in USD from CoinGecko API.
    
    Returns:
        float: The current BitCast price in USD
        
    Raises:
        requests.exceptions.RequestException: If the API request fails after all retries
        KeyError: If the expected data structure is not found in the response
        ValueError: If the response data is invalid
    """
    response = requests.get(
        "https://api.coingecko.com/api/v3/simple/price?ids=bitcast&vs_currencies=usd", 
        timeout=10
    )
    response.raise_for_status()
    
    data = response.json()
    
    # Validate response structure
    if 'bitcast' not in data:
        raise KeyError("BitCast data not found in API response")
    if 'usd' not in data['bitcast']:
        raise KeyError("USD price not found in BitCast data")
    
    bitcast_usd_price = data['bitcast']['usd']
    
    if not isinstance(bitcast_usd_price, (int, float)) or bitcast_usd_price <= 0:
        raise ValueError(f"Invalid price value: {bitcast_usd_price}")
    
    return float(bitcast_usd_price)


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((Exception,))
)
def get_total_miner_emissions() -> float:
    """
    Get the total miner emissions per day for subnet 93.
    
    Returns:
        float: The total miner emissions in TAO per day
        
    Raises:
        Exception: If the subtensor connection or calculation fails after all retries
    """
    subtensor = bt.Subtensor(network='finney')
    subnet_info = subtensor.subnet(netuid=93)
    tao_per_block = float(subnet_info.alpha_in_emission)
    
    BLOCKS_PER_DAY = 7200
    total_tao_daily = tao_per_block * BLOCKS_PER_DAY
    miner_daily = total_tao_daily * 0.41
    
    if not isinstance(miner_daily, (int, float)) or miner_daily < 0:
        raise ValueError(f"Invalid miner emissions value: {miner_daily}")
    
    return float(miner_daily)