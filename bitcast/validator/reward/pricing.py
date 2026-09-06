"""Alpha token price and emission-budget lookups for USD -> weight conversion."""

import time

import bittensor as bt
import httpx

from bitcast.config import BLOCKS_PER_DAY, MINER_EMISSION_SHARE, NETUID, PRICE_CACHE_TTL
from bitcast.http import request_with_retry

COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bitcast&vs_currencies=usd"
FALLBACK_MECH_EMISSION_RATIO = 0.85


class PricingService:
    """Converts USD scores into chain-weight fractions of the daily emission budget."""

    def __init__(self, subtensor: bt.Subtensor, netuid: int = NETUID, mechid: int = 0) -> None:
        self.subtensor = subtensor
        self.netuid = netuid
        self.mechid = mechid
        self._cache: dict[str, tuple[float, float]] = {}  # key -> (value, fetched_at)

    def _cached(self, key: str) -> float | None:
        entry = self._cache.get(key)
        if entry and time.monotonic() - entry[1] < PRICE_CACHE_TTL:
            return entry[0]
        return None

    def _store(self, key: str, value: float) -> float:
        self._cache[key] = (value, time.monotonic())
        return value

    async def _fetch_alpha_price(self) -> float:
        async with httpx.AsyncClient() as client:
            response = await request_with_retry(client, "GET", COINGECKO_PRICE_URL, timeout=10.0, label="alpha-price")
            response.raise_for_status()
            data = response.json()
            return float(data["bitcast"]["usd"])

    async def get_alpha_price_usd(self) -> float:
        """Current USD price of the bitcast alpha token (CoinGecko, 10-min cache)."""
        cached = self._cached("price")
        if cached is not None:
            return cached
        return self._store("price", await self._fetch_alpha_price())

    def get_total_daily_miner_alpha(self) -> float:
        """Alpha emitted to miners per day: block emission x miner share x mechanism split."""
        cached = self._cached("emissions")
        if cached is not None:
            return cached

        subnet_info = self.subtensor.subnet(netuid=self.netuid)
        if subnet_info is None:
            raise ConnectionError(f"Subnet {self.netuid} info unavailable")
        alpha_out = float(getattr(subnet_info.alpha_out_emission, "tao", subnet_info.alpha_out_emission))
        daily_alpha = BLOCKS_PER_DAY * alpha_out

        split = self.subtensor.get_mechanism_emission_split(self.netuid)
        if split and sum(split) > 0 and self.mechid < len(split):
            emission_ratio = split[self.mechid] / sum(split)
        else:
            emission_ratio = FALLBACK_MECH_EMISSION_RATIO

        return self._store("emissions", daily_alpha * MINER_EMISSION_SHARE * emission_ratio)

    async def get_total_daily_usd(self) -> float:
        """USD value of the daily miner emission budget."""
        return await self.get_alpha_price_usd() * self.get_total_daily_miner_alpha()
