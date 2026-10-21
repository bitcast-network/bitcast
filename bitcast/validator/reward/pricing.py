"""Alpha token price and emission-budget lookups for USD -> weight conversion.

Pricing failures must never silently zero a creator day (2026-09-30: a
transient CoinGecko 403 zeroed alpha targets platform-wide and the loss was
only discovered when a creator complained). The rule here is:

- A price from earlier in the process lifetime is better than no price.
- A price from a secondary source is better than nothing.
- If nothing trustworthy exists, raise loudly and let the caller abort the
  cycle — a skipped run pays nothing but says so; a zeroed run lies.
"""

import time

import bittensor as bt
import httpx

from bitcast.config import BLOCKS_PER_DAY, MINER_EMISSION_SHARE, NETUID, PRICE_CACHE_TTL
from bitcast.http import request_with_retry

COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bitcast&vs_currencies=usd"
# Secondary price source: CoinPaprika mirrors the same pair keyless.
COINPAPRIKA_SEARCH_URL = "https://api.coinpaprika.com/v1/search?q=bitcast&c=coins&limit=5"
FALLBACK_MECH_EMISSION_RATIO = 0.85
# Stale-beyond-this a cached price is still usable for weighting, but the
# caller is told so it can decide (publication refuses stale, weighting does
# not — a mildly stale price is far better than aborting the cycle).
STALE_PRICE_WARN_AFTER_S = 3600.0


class PricingUnavailableError(RuntimeError):
    """No trustworthy price source responded and no cache exists."""


class PricingService:
    """Converts USD scores into chain-weight fractions of the daily emission budget."""

    def __init__(self, subtensor: bt.Subtensor, netuid: int = NETUID, mechid: int = 0) -> None:
        self.subtensor = subtensor
        self.netuid = netuid
        self.mechid = mechid
        self._cache: dict[str, tuple[float, float]] = {}  # key -> (value, fetched_at)
        self._coinpaprika_coin_id: str | None = None

    def _cached(self, key: str) -> float | None:
        entry = self._cache.get(key)
        if entry and time.monotonic() - entry[1] < PRICE_CACHE_TTL:
            return entry[0]
        return None

    def _store(self, key: str, value: float) -> float:
        self._cache[key] = (value, time.monotonic())
        return value

    async def _fetch_alpha_price_coingecko(self) -> float:
        async with httpx.AsyncClient() as client:
            response = await request_with_retry(client, "GET", COINGECKO_PRICE_URL, timeout=10.0, label="alpha-price")
            response.raise_for_status()
            data = response.json()
            return float(data["bitcast"]["usd"])

    async def _resolve_coinpaprika_coin_id(self, client: httpx.AsyncClient) -> str | None:
        """CoinPaprika addresses coins by id; discover the bitcast id once."""
        if self._coinpaprika_coin_id:
            return self._coinpaprika_coin_id
        response = await request_with_retry(
            client, "GET", COINPAPRIKA_SEARCH_URL, timeout=10.0, label="alpha-price-paprika-search"
        )
        response.raise_for_status()
        coins = response.json().get("coins") or []
        for coin in coins:
            symbol = (coin.get("symbol") or "").upper()
            name = (coin.get("name") or "").lower()
            if symbol == "BITCAST" or "bitcast" in name:
                self._coinpaprika_coin_id = coin.get("id")
                return self._coinpaprika_coin_id
        return None

    async def _fetch_alpha_price_coinpaprika(self) -> float:
        async with httpx.AsyncClient() as client:
            coin_id = await self._resolve_coinpaprika_coin_id(client)
            if not coin_id:
                raise PricingUnavailableError("CoinPaprika search returned no bitcast coin")
            url = f"https://api.coinpaprika.com/v1/tickers/{coin_id}"
            response = await request_with_retry(client, "GET", url, timeout=10.0, label="alpha-price-paprika")
            response.raise_for_status()
            quotes = response.json().get("quotes") or {}
            usd = (quotes.get("USD") or {}).get("price")
            if usd is None:
                raise PricingUnavailableError("CoinPaprika ticker missing USD quote")
            return float(usd)

    async def get_alpha_price_usd(self, *, allow_stale: bool = False) -> float:
        """Current USD price of the bitcast alpha token.

        Order: fresh cache -> CoinGecko -> CoinPaprika -> stale cache (only
        when ``allow_stale``). Raises :class:`PricingUnavailableError` when
        every path fails; never returns a fabricated value.
        """
        cached = self._cached("price")
        if cached is not None:
            return cached
        for fetch in (self._fetch_alpha_price_coingecko, self._fetch_alpha_price_coinpaprika):
            try:
                return self._store("price", await fetch())
            except Exception as err:
                bt.logging.warning(f"Alpha price source failed ({fetch.__name__}): {err!r}; trying next source.")
        entry = self._cache.get("price")
        if entry and allow_stale:
            age_s = time.monotonic() - entry[1]
            bt.logging.warning(
                f"All alpha price sources failed; using stale cached price "
                f"({age_s / 60:.0f} min old) rather than zeroing the cycle."
            )
            return entry[0]
        raise PricingUnavailableError("No alpha price source responded and no cached price exists")

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

    async def get_total_daily_usd(self, *, allow_stale: bool = False) -> float:
        """USD value of the daily miner emission budget."""
        return await self.get_alpha_price_usd(allow_stale=allow_stale) * self.get_total_daily_miner_alpha()
