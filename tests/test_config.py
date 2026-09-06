"""Settings composition: derived endpoints and the flat backward-compat surface."""

import pytest
from pydantic import ValidationError

from bitcast.config import CONSENSUS, EndpointSettings, Settings, build_config


class TestDerivedEndpoints:
    def test_briefs_endpoint_derives_from_the_api_url(self):
        endpoints = EndpointSettings(bitcast_api_url="https://api.example")
        assert endpoints.briefs_endpoint == "https://api.example/api/v2/validator/briefs"

    def test_briefs_endpoint_can_be_overridden_wholesale(self, monkeypatch):
        monkeypatch.setenv("BITCAST_BRIEFS_ENDPOINT", "https://staging.example/briefs")
        endpoints = EndpointSettings(bitcast_api_url="https://api.example")
        assert endpoints.briefs_endpoint == "https://staging.example/briefs"

    def test_blank_override_falls_back_to_the_derived_default(self, monkeypatch):
        monkeypatch.setenv("BITCAST_BRIEFS_ENDPOINT", "")
        endpoints = EndpointSettings(bitcast_api_url="https://api.example")
        assert endpoints.briefs_endpoint == "https://api.example/api/v2/validator/briefs"

    def test_submit_and_corrections_endpoints_derive_from_the_data_client(self):
        endpoints = EndpointSettings(data_client_url="http://data.example")
        assert endpoints.youtube_submit_endpoint == "http://data.example/api/v1/youtube/submit"
        assert endpoints.weight_corrections_endpoint == "http://data.example/api/v1/weight-corrections"


class TestFlatCompatSurface:
    def test_flat_kwargs_route_to_their_group(self):
        settings = Settings(sentry_dsn="https://x@y/1", eco_mode=False, llm_provider="OpenRouter")
        assert settings.observability.sentry_dsn == "https://x@y/1"
        assert settings.features.eco_mode is False
        assert settings.keys.llm_provider == "openrouter"  # lowercased by validator

    def test_flat_properties_delegate_to_groups(self):
        settings = Settings(bitcast_api_url="https://api.example", data_client_url="http://data.example")
        assert settings.bitcast_api_url == "https://api.example"
        assert settings.briefs_endpoint == settings.endpoints.briefs_endpoint
        assert settings.youtube_submit_endpoint == settings.endpoints.youtube_submit_endpoint

    def test_settings_are_frozen(self):
        settings = Settings()
        with pytest.raises(ValidationError):
            settings.features = None


class TestConsensusConstants:
    """These feed on-chain weight math; a change here diverges from the subnet."""

    def test_consensus_params_are_frozen(self):
        with pytest.raises(ValidationError):
            CONSENSUS.netuid = 1

    def test_pinned_values(self):
        assert CONSENSUS.netuid == 93
        assert CONSENSUS.burn_uid == 0
        assert CONSENSUS.miner_emission_share == 0.41
        assert CONSENSUS.yt_scaling_factor_dedicated == 1800
        assert CONSENSUS.yt_scaling_factor_ad_read == 400
        assert CONSENSUS.yt_scaling_factor_product_placement == 200
        assert CONSENSUS.yt_curve_dampening_factor == 0.1
        assert CONSENSUS.yt_rolling_window == 7
        assert CONSENSUS.yt_scoring_window == 14
        assert CONSENSUS.yt_reward_delay == 3

    def test_non_ypp_proxy_constants_are_gone(self):
        """Non-YPP scoring was removed; its constants must not linger."""
        assert not hasattr(CONSENSUS, "yt_non_ypp_revenue_multiplier")
        assert not hasattr(CONSENSUS, "yt_min_alpha_stake_threshold")


class TestCliConfig:
    def test_validator_defaults(self):
        config = build_config("validator", [])
        assert config.netuid == CONSENSUS.netuid
        assert config.neuron.moving_average_alpha == 0.6
        assert config.neuron.disable_set_weights is False

    def test_dotted_args_populate_nested_models(self):
        config = build_config("validator", ["--wallet.name", "alice", "--subtensor.network", "test"])
        assert config.wallet.name == "alice"
        assert config.subtensor.network == "test"

    def test_unknown_neuron_type_raises(self):
        with pytest.raises(ValueError, match="Unknown neuron type"):
            build_config("oracle", [])
