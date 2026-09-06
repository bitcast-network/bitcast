"""Protocol round-trip tests."""

from bitcast.protocol import AccessTokenSynapse


def test_synapse_defaults_to_no_tokens():
    synapse = AccessTokenSynapse()
    assert synapse.YT_access_tokens is None


def test_synapse_carries_tokens():
    synapse = AccessTokenSynapse(YT_access_tokens=["token-a", "token-b"])
    assert synapse.YT_access_tokens == ["token-a", "token-b"]


def test_synapse_serialization_round_trip():
    synapse = AccessTokenSynapse(YT_access_tokens=["token-a"])
    restored = AccessTokenSynapse.model_validate(synapse.model_dump())
    assert restored.YT_access_tokens == ["token-a"]
