"""All Bitcast configuration in one place.

Three layers, matching the bitcast-x-v2 pattern:

* ``ConsensusParams`` — **frozen constants** feeding consensus-critical math.
  Changing any value diverges this validator's weights from the network.
  Module-level aliases (``YT_*``, ``NETUID``, …) re-export these so existing
  import sites keep working; ``CONSENSUS`` is the single source of truth.
* ``*Settings`` groups — environment-driven operational config, read via
  pydantic-settings ``BaseSettings``. Env var names are unchanged from the
  old codebase (the ``.env`` surface is frozen).
* ``Settings`` aggregate — composes the groups plus ``CONSENSUS``. Flat
  backward-compat properties (``settings.chutes_api_key``, …) delegate to the
  groups so consumers keep working during the migration.

No import-time side effects beyond ``load_dotenv()``: call ``get_settings()``
from entrypoints to build the (cached) aggregate.
"""

import argparse
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

# ---------------------------------------------------------------------------
# Consensus constants (frozen — bit-identical math depends on these)
# ---------------------------------------------------------------------------


class ConsensusParams(BaseModel):
    """Constants feeding consensus-critical math.

    Changing any value diverges this validator's weights from the network.
    """

    model_config = ConfigDict(frozen=True)

    # --- Subnet ---
    netuid: int = 93
    burn_uid: int = 0
    subnet_treasury_uid: int = 106
    subnet_treasury_percentage: float = 0.0
    miner_emission_share: float = 0.41
    blocks_per_day: float = 7200.0

    # --- Validator loop ---
    validator_wait: int = 60  # seconds slept between steps
    validator_steps_interval: int = 240  # steps between full reward cycles (~4 h)
    max_accounts_per_synapse: int = 1000
    credential_batch_size: int = 8  # tokens evaluated per miner re-query batch
    discrete_mode: bool = True  # publish hashed channel/video ids instead of raw ones

    # --- YouTube scoring (consensus-critical) ---
    yt_lookback: int = 90  # days of channel history considered
    yt_rolling_window: int = 7  # days in each scoring average window
    yt_scoring_window: int = 14  # days a video remains scoreable
    yt_reward_delay: int = 3  # days analytics lag behind realtime
    yt_video_release_buffer: int = 3  # days a video may precede its brief start
    yt_max_videos: int = 75
    yt_max_concurrent_videos: int = 6  # videos evaluated in parallel within one channel
    yt_max_concurrent_analytics: int = 4  # Analytics requests in flight per OAuth user
    yt_analytics_queries_per_minute: int = 480  # sustained project-wide rate; v1's observed pace

    yt_scaling_factor_dedicated: int = 1800
    yt_scaling_factor_ad_read: int = 400
    yt_scaling_factor_product_placement: int = 200  # doubled 29 Jul 2026, half an integration's rate
    yt_lifetime_deduction: float = 100.0  # USD, dedicated format
    yt_lifetime_deduction_ad_read: float = 25.0
    yt_lifetime_deduction_product_placement: float = 6.25

    yt_min_emissions: float = 0.0  # global emission floor (fraction of total)
    yt_curve_dampening_factor: float = 0.1

    yt_score_cap_start_days: int = 60  # median threshold window: T-60 .. T-30
    yt_score_cap_end_days: int = 30

    yt_min_channel_age: int = 21  # days
    yt_min_subs: int = 100
    yt_max_subs: int = 500_000
    yt_min_mins_watched: int = 1000  # over the lookback window
    yt_min_channel_retention: int = 10  # average view percentage

    transcript_max_retry: int = 10
    transcript_max_length: int = 250_000  # chars fed to the LLM

    # --- Cache TTLs ---
    youtube_search_cache_ttl: int = 12 * 60 * 60
    llm_cache_ttl: int = 3 * 24 * 60 * 60
    price_cache_ttl: int = 600


CONSENSUS = ConsensusParams()

# Backward-compatible module-level aliases — CONSENSUS is the source of truth.
NETUID = CONSENSUS.netuid
BURN_UID = CONSENSUS.burn_uid
SUBNET_TREASURY_UID = CONSENSUS.subnet_treasury_uid
SUBNET_TREASURY_PERCENTAGE = CONSENSUS.subnet_treasury_percentage
MINER_EMISSION_SHARE = CONSENSUS.miner_emission_share
BLOCKS_PER_DAY = CONSENSUS.blocks_per_day

VALIDATOR_WAIT = CONSENSUS.validator_wait
VALIDATOR_STEPS_INTERVAL = CONSENSUS.validator_steps_interval
MAX_ACCOUNTS_PER_SYNAPSE = CONSENSUS.max_accounts_per_synapse
CREDENTIAL_BATCH_SIZE = CONSENSUS.credential_batch_size
DISCRETE_MODE = CONSENSUS.discrete_mode

YT_LOOKBACK = CONSENSUS.yt_lookback
YT_ROLLING_WINDOW = CONSENSUS.yt_rolling_window
YT_SCORING_WINDOW = CONSENSUS.yt_scoring_window
YT_REWARD_DELAY = CONSENSUS.yt_reward_delay
YT_VIDEO_RELEASE_BUFFER = CONSENSUS.yt_video_release_buffer
YT_MAX_VIDEOS = CONSENSUS.yt_max_videos
YT_MAX_CONCURRENT_VIDEOS = CONSENSUS.yt_max_concurrent_videos
YT_MAX_CONCURRENT_ANALYTICS = CONSENSUS.yt_max_concurrent_analytics
YT_ANALYTICS_QUERIES_PER_MINUTE = CONSENSUS.yt_analytics_queries_per_minute
YT_SCALING_FACTOR_DEDICATED = CONSENSUS.yt_scaling_factor_dedicated
YT_SCALING_FACTOR_AD_READ = CONSENSUS.yt_scaling_factor_ad_read
YT_SCALING_FACTOR_PRODUCT_PLACEMENT = CONSENSUS.yt_scaling_factor_product_placement
YT_LIFETIME_DEDUCTION = CONSENSUS.yt_lifetime_deduction
YT_LIFETIME_DEDUCTION_AD_READ = CONSENSUS.yt_lifetime_deduction_ad_read
YT_LIFETIME_DEDUCTION_PRODUCT_PLACEMENT = CONSENSUS.yt_lifetime_deduction_product_placement
YT_MIN_EMISSIONS = CONSENSUS.yt_min_emissions
YT_CURVE_DAMPENING_FACTOR = CONSENSUS.yt_curve_dampening_factor
YT_SCORE_CAP_START_DAYS = CONSENSUS.yt_score_cap_start_days
YT_SCORE_CAP_END_DAYS = CONSENSUS.yt_score_cap_end_days
YT_MIN_CHANNEL_AGE = CONSENSUS.yt_min_channel_age
YT_MIN_SUBS = CONSENSUS.yt_min_subs
YT_MAX_SUBS = CONSENSUS.yt_max_subs
YT_MIN_MINS_WATCHED = CONSENSUS.yt_min_mins_watched
YT_MIN_CHANNEL_RETENTION = CONSENSUS.yt_min_channel_retention
TRANSCRIPT_MAX_RETRY = CONSENSUS.transcript_max_retry
TRANSCRIPT_MAX_LENGTH = CONSENSUS.transcript_max_length

YOUTUBE_SEARCH_CACHE_TTL = CONSENSUS.youtube_search_cache_ttl
LLM_CACHE_TTL = CONSENSUS.llm_cache_ttl
PRICE_CACHE_TTL = CONSENSUS.price_cache_ttl


# ---------------------------------------------------------------------------
# Environment-driven settings groups (env names frozen — old .env keeps working)
# ---------------------------------------------------------------------------


class EndpointSettings(BaseSettings):
    """External service endpoints and subnet mechanism id."""

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    bitcast_api_url: str = Field(default="https://bitcast-api.bitcast.network", alias="BITCAST_API_URL")
    data_client_url: str = Field(default="http://44.254.20.95", alias="DATA_CLIENT_URL")
    mechid: int = Field(default=0, alias="MECHID")  # subnet mechanism id for emission split
    # Full-URL override for the briefs server, independent of bitcast_api_url.
    briefs_endpoint_override: str | None = Field(default=None, alias="BITCAST_BRIEFS_ENDPOINT")

    @property
    def briefs_endpoint(self) -> str:
        """Briefs URL: the explicit override, else derived from the API url.

        A blank override falls back to the derived default — an empty endpoint
        would fail every briefs fetch and burn the whole emission.
        """
        return self.briefs_endpoint_override or f"{self.bitcast_api_url}/api/v2/validator/briefs"

    @property
    def youtube_submit_endpoint(self) -> str:
        return f"{self.data_client_url}/api/v1/youtube/submit"

    @property
    def weight_corrections_endpoint(self) -> str:
        return f"{self.data_client_url}/api/v1/weight-corrections"


class ApiKeySettings(BaseSettings):
    """API keys and provider selection."""

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    rapid_api_key: str | None = Field(default=None, alias="RAPID_API_KEY")
    chutes_api_key: str | None = Field(default=None, alias="CHUTES_API_KEY")
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    bitcast_api_key: str | None = Field(default=None, alias="BITCAST_API_KEY")
    llm_provider: str = Field(default="chutes", alias="LLM_PROVIDER")  # "chutes" | "openrouter"

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _lowercase(cls, v: object) -> object:
        return v.lower() if isinstance(v, str) else v


class MinerSettings(BaseSettings):
    """Miner token source configuration."""

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    token_source: str = Field(default="local", alias="TOKEN_SOURCE")  # "local" | "api"
    secrets_dir: str = Field(default="~/.bitcast/secrets", alias="BITCAST_SECRETS_DIR")

    @field_validator("token_source", mode="before")
    @classmethod
    def _lowercase(cls, v: object) -> object:
        return v.lower() if isinstance(v, str) else v


class ObservabilitySettings(BaseSettings):
    """Sentry + Grafana Loki configuration."""

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    sentry_dsn: str | None = Field(default=None, alias="SENTRY_DSN")
    sentry_environment: str = Field(default="production", alias="SENTRY_ENVIRONMENT")

    # Grafana Loki — decentralized log aggregation. Configure via deployment
    # env/secrets (LOKI_URL / LOKI_USERNAME / LOKI_TOKEN). With any value
    # missing, Loki is disabled. Set LOKI_URL="" to disable explicitly.
    loki_url: str | None = Field(default="https://logs-prod-042.grafana.net", alias="LOKI_URL")
    loki_username: str | None = Field(default=None, alias="LOKI_USERNAME")
    loki_token: str | None = Field(
        default=None,
        alias="LOKI_TOKEN",
    )


class FeatureFlagSettings(BaseSettings):
    """Operational feature flags."""

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    enable_data_publish: bool = Field(default=False, alias="ENABLE_DATA_PUBLISH")
    eco_mode: bool = Field(default=True, alias="ECO_MODE")  # only LLM-check videos that pass every other gate
    disable_prompt_injection: bool = Field(default=True, alias="DISABLE_PROMPT_INJECTION")
    disable_llm_caching: bool = Field(default=False, alias="DISABLE_LLM_CACHING")


class Settings(BaseModel):
    """Aggregate settings — typed groups plus frozen consensus constants.

    Flat backward-compat properties delegate to the groups so existing
    ``settings.chutes_api_key`` style access keeps working. A ``before``
    validator routes flat constructor kwargs (``Settings(sentry_dsn=…)``) to the
    right group so existing call sites and tests are unchanged.
    """

    model_config = ConfigDict(frozen=True)

    endpoints: EndpointSettings
    keys: ApiKeySettings
    miner: MinerSettings
    observability: ObservabilitySettings
    features: FeatureFlagSettings
    consensus: ConsensusParams = Field(default=CONSENSUS)

    # Flat backward-compat read-access (delegates to groups).
    @property
    def bitcast_api_url(self) -> str:
        return self.endpoints.bitcast_api_url

    @property
    def data_client_url(self) -> str:
        return self.endpoints.data_client_url

    @property
    def mechid(self) -> int:
        return self.endpoints.mechid

    @property
    def rapid_api_key(self) -> str | None:
        return self.keys.rapid_api_key

    @property
    def chutes_api_key(self) -> str | None:
        return self.keys.chutes_api_key

    @property
    def openrouter_api_key(self) -> str | None:
        return self.keys.openrouter_api_key

    @property
    def bitcast_api_key(self) -> str | None:
        return self.keys.bitcast_api_key

    @property
    def llm_provider(self) -> str:
        return self.keys.llm_provider

    @property
    def token_source(self) -> str:
        return self.miner.token_source

    @property
    def secrets_dir(self) -> str:
        return self.miner.secrets_dir

    @property
    def sentry_dsn(self) -> str | None:
        return self.observability.sentry_dsn

    @property
    def sentry_environment(self) -> str:
        return self.observability.sentry_environment

    @property
    def loki_url(self) -> str | None:
        return self.observability.loki_url

    @property
    def loki_username(self) -> str | None:
        return self.observability.loki_username

    @property
    def loki_token(self) -> str | None:
        return self.observability.loki_token

    @property
    def enable_data_publish(self) -> bool:
        return self.features.enable_data_publish

    @property
    def eco_mode(self) -> bool:
        return self.features.eco_mode

    @property
    def disable_prompt_injection(self) -> bool:
        return self.features.disable_prompt_injection

    @property
    def disable_llm_caching(self) -> bool:
        return self.features.disable_llm_caching

    # Derived endpoint properties (backward-compat surface).
    @property
    def briefs_endpoint(self) -> str:
        return self.endpoints.briefs_endpoint

    @property
    def youtube_submit_endpoint(self) -> str:
        return self.endpoints.youtube_submit_endpoint

    @property
    def weight_corrections_endpoint(self) -> str:
        return self.endpoints.weight_corrections_endpoint

    @model_validator(mode="before")
    @classmethod
    def _route_flat_kwargs(cls, data: object) -> object:
        """Accept flat constructor kwargs (``Settings(sentry_dsn=…)``) for backward compat."""
        if not isinstance(data, dict):
            return data
        group_names = ("endpoints", "keys", "miner", "observability", "features", "consensus")
        has_groups = any(k in data for k in group_names)
        if has_groups:
            return data  # already passing group instances — no routing needed
        routed: dict[str, dict[str, object]] = {g: {} for g in group_names if g != "consensus"}
        for key, val in data.items():
            group = _FLAT_FIELD_TO_GROUP.get(key)
            if group is not None:
                routed[group][key] = val
        return routed


# Maps flat settings field names to their group (for the before-validator).
_FLAT_FIELD_TO_GROUP: dict[str, str] = {
    "bitcast_api_url": "endpoints",
    "data_client_url": "endpoints",
    "mechid": "endpoints",
    "briefs_endpoint_override": "endpoints",
    "rapid_api_key": "keys",
    "chutes_api_key": "keys",
    "openrouter_api_key": "keys",
    "bitcast_api_key": "keys",
    "llm_provider": "keys",
    "token_source": "miner",
    "secrets_dir": "miner",
    "sentry_dsn": "observability",
    "sentry_environment": "observability",
    "loki_url": "observability",
    "loki_username": "observability",
    "loki_token": "observability",
    "enable_data_publish": "features",
    "eco_mode": "features",
    "disable_prompt_injection": "features",
    "disable_llm_caching": "features",
}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton (built from the environment)."""
    return Settings(
        endpoints=EndpointSettings(),
        keys=ApiKeySettings(),
        miner=MinerSettings(),
        observability=ObservabilitySettings(),
        features=FeatureFlagSettings(),
    )


# --- CLI config -------------------------------------------------------------


class WalletConfig(BaseModel):
    name: str = "default"
    hotkey: str = "default"
    path: str = "~/.bittensor/wallets/"


class SubtensorConfig(BaseModel):
    network: str = "finney"


class AxonConfig(BaseModel):
    port: int = 8091
    ip: str = "[::]"
    external_ip: str | None = None
    external_port: int | None = None


class LoggingConfig(BaseModel):
    debug: bool = False
    trace: bool = False


class BlacklistConfig(BaseModel):
    force_validator_permit: bool = True
    allow_non_registered: bool = False
    min_stake: int = 30_000


class NeuronConfig(BaseModel):
    name: str = "neuron"
    epoch_length: int = 100  # blocks between weight settings / syncs
    timeout: float = 10.0  # miner query timeout (validator only)
    moving_average_alpha: float = 0.6  # EMA weight for new rewards (validator only)
    disable_set_weights: bool = False


class BitcastConfig(BaseModel):
    """Full CLI configuration for a Bitcast neuron."""

    netuid: int = NETUID
    dev_mode: bool = False
    wallet: WalletConfig = WalletConfig()
    subtensor: SubtensorConfig = SubtensorConfig()
    axon: AxonConfig = AxonConfig()
    logging: LoggingConfig = LoggingConfig()
    blacklist: BlacklistConfig = BlacklistConfig()
    neuron: NeuronConfig = NeuronConfig()

    def state_path(self) -> Path:
        """Directory where this neuron persists state, created on first use."""
        path = (
            Path.home() / ".bitcast" / self.wallet.name / self.wallet.hotkey / f"netuid{self.netuid}" / self.neuron.name
        )
        path.mkdir(parents=True, exist_ok=True)
        return path


def build_config(neuron_type: str, args: list[str] | None = None) -> BitcastConfig:
    """Parse CLI arguments into a :class:`BitcastConfig`.

    Args:
        neuron_type: Either ``"miner"`` or ``"validator"``.
        args: Argument list override, used by tests. Defaults to ``sys.argv``.
    """
    if neuron_type not in ("miner", "validator"):
        raise ValueError(f"Unknown neuron type: {neuron_type}")

    parser = argparse.ArgumentParser(description=f"Bitcast {neuron_type}")
    parser.add_argument("--netuid", type=int, default=NETUID)
    parser.add_argument("--dev_mode", action="store_true")
    parser.add_argument("--wallet.name", type=str, default="default")
    parser.add_argument("--wallet.hotkey", type=str, default="default")
    parser.add_argument("--wallet.path", type=str, default="~/.bittensor/wallets/")
    parser.add_argument("--subtensor.network", type=str, default="finney")
    parser.add_argument("--axon.port", type=int, default=8091)
    parser.add_argument("--axon.ip", type=str, default="[::]")
    parser.add_argument("--axon.external_ip", type=str, default=None)
    parser.add_argument("--axon.external_port", type=int, default=None)
    parser.add_argument("--logging.debug", action="store_true")
    parser.add_argument("--logging.trace", action="store_true")
    parser.add_argument("--neuron.name", type=str, default=neuron_type)
    parser.add_argument("--neuron.epoch_length", type=int, default=100)
    if neuron_type == "miner":
        parser.add_argument("--blacklist.force_validator_permit", action="store_true", default=True)
        parser.add_argument("--blacklist.allow_non_registered", action="store_true", default=False)
        parser.add_argument("--blacklist.min_stake", type=int, default=30_000)
    else:
        parser.add_argument("--neuron.timeout", type=float, default=10.0)
        parser.add_argument("--neuron.moving_average_alpha", type=float, default=0.6)
        parser.add_argument("--neuron.disable_set_weights", action="store_true", default=False)

    parsed = vars(parser.parse_args(args))

    def sub(prefix: str) -> dict:
        return {key.removeprefix(prefix): value for key, value in parsed.items() if key.startswith(prefix)}

    return BitcastConfig(
        netuid=parsed["netuid"],
        dev_mode=parsed["dev_mode"],
        wallet=WalletConfig(**sub("wallet.")),
        subtensor=SubtensorConfig(**sub("subtensor.")),
        axon=AxonConfig(**sub("axon.")),
        logging=LoggingConfig(**sub("logging.")),
        blacklist=BlacklistConfig(**sub("blacklist.")),
        neuron=NeuronConfig(**sub("neuron.")),
    )
