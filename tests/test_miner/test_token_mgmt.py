"""Miner token management: config validation, refresh flow, caching."""

import json
import time

import pytest

from bitcast.config import Settings
from bitcast.miner.token_mgmt import TokenConfigError, TokenManager


@pytest.fixture
def secrets_dir(tmp_path):
    return tmp_path / "secrets"


def make_settings(secrets_dir, **overrides) -> Settings:
    return Settings(secrets_dir=str(secrets_dir), **overrides)


def write_credentials(secrets_dir, name="acct1.json"):
    secrets_dir.mkdir(parents=True, exist_ok=True)
    (secrets_dir / name).write_text(json.dumps({"client_id": "cid", "client_secret": "sec", "refresh_token": "ref"}))


class _FakeCredentials:
    """Mimics google.oauth2.credentials.Credentials for .pkl test fixtures."""

    client_id = "cid"
    client_secret = "sec"
    refresh_token = "ref"


def write_pkl_credentials(secrets_dir, name="acct1.pkl"):
    """Write a fake V1 .pkl credentials file (pickled object with OAuth attributes)."""
    import pickle

    secrets_dir.mkdir(parents=True, exist_ok=True)
    with open(secrets_dir / name, "wb") as f:
        pickle.dump(_FakeCredentials(), f)


class TestInit:
    def test_local_without_credentials_raises(self, secrets_dir):
        with pytest.raises(TokenConfigError, match="No credential files"):
            TokenManager(make_settings(secrets_dir)).init()

    def test_local_with_credentials_passes(self, secrets_dir):
        write_credentials(secrets_dir)
        TokenManager(make_settings(secrets_dir)).init()

    def test_api_without_key_raises(self, secrets_dir):
        settings = make_settings(secrets_dir, token_source="api", bitcast_api_key=None)
        with pytest.raises(TokenConfigError, match="BITCAST_API_KEY"):
            TokenManager(settings).init()

    def test_api_with_key_passes(self, secrets_dir):
        settings = make_settings(secrets_dir, token_source="api", bitcast_api_key="key")
        TokenManager(settings).init()


class TestLocalTokens:
    async def test_refresh_called_and_cached(self, secrets_dir, monkeypatch):
        write_credentials(secrets_dir)
        manager = TokenManager(make_settings(secrets_dir))
        refresh_calls = []

        async def fake_refresh(session, credentials):
            refresh_calls.append(credentials["refresh_token"])
            return "fresh-token", 3600.0

        monkeypatch.setattr(TokenManager, "_refresh", staticmethod(fake_refresh))

        assert await manager.load_tokens() == ["fresh-token"]
        assert await manager.load_tokens() == ["fresh-token"]
        assert refresh_calls == ["ref"]  # second load served from cache

    async def test_expired_cache_triggers_refresh(self, secrets_dir, monkeypatch):
        write_credentials(secrets_dir)
        manager = TokenManager(make_settings(secrets_dir))
        manager._token_cache["acct1.json"] = ("stale", time.monotonic() - 1)

        async def fake_refresh(session, credentials):
            return "renewed", 3600.0

        monkeypatch.setattr(TokenManager, "_refresh", staticmethod(fake_refresh))
        assert await manager.load_tokens() == ["renewed"]

    async def test_broken_credential_file_skipped(self, secrets_dir, monkeypatch):
        write_credentials(secrets_dir, "good.json")
        secrets_dir.joinpath("bad.json").write_text("{not json")
        manager = TokenManager(make_settings(secrets_dir))

        async def fake_refresh(session, credentials):
            return "good-token", 3600.0

        monkeypatch.setattr(TokenManager, "_refresh", staticmethod(fake_refresh))
        assert await manager.load_tokens() == ["good-token"]

    async def test_multiple_accounts_all_loaded(self, secrets_dir, monkeypatch):
        write_credentials(secrets_dir, "a.json")
        write_credentials(secrets_dir, "b.json")
        manager = TokenManager(make_settings(secrets_dir))

        async def fake_refresh(session, credentials):
            return f"token-{len(manager._token_cache)}", 3600.0

        monkeypatch.setattr(TokenManager, "_refresh", staticmethod(fake_refresh))
        assert len(await manager.load_tokens()) == 2


class TestPklCredentials:
    """Legacy V1 .pkl credential files must work alongside .json files."""

    def test_init_with_pkl_passes(self, secrets_dir):
        """A .pkl file alone should satisfy init()."""
        write_pkl_credentials(secrets_dir)
        TokenManager(make_settings(secrets_dir)).init()

    def test_init_with_pkl_and_json_passes(self, secrets_dir):
        """Mixed .json + .pkl directories work."""
        write_credentials(secrets_dir, "new.json")
        write_pkl_credentials(secrets_dir, "old.pkl")
        TokenManager(make_settings(secrets_dir)).init()

    async def test_pkl_token_loaded(self, secrets_dir, monkeypatch):
        """A .pkl file produces a token through the refresh path."""
        write_pkl_credentials(secrets_dir)
        manager = TokenManager(make_settings(secrets_dir))
        refresh_calls = []

        async def fake_refresh(session, credentials):
            refresh_calls.append(credentials)
            return "pkl-token", 3600.0

        monkeypatch.setattr(TokenManager, "_refresh", staticmethod(fake_refresh))
        assert await manager.load_tokens() == ["pkl-token"]
        assert refresh_calls[0]["refresh_token"] == "ref"
        assert refresh_calls[0]["client_id"] == "cid"

    async def test_mixed_json_and_pkl_both_loaded(self, secrets_dir, monkeypatch):
        """Both file types in the same directory produce tokens."""
        write_credentials(secrets_dir, "json_acct.json")
        write_pkl_credentials(secrets_dir, "pkl_acct.pkl")
        manager = TokenManager(make_settings(secrets_dir))

        async def fake_refresh(session, credentials):
            return f"token-{credentials['client_id']}", 3600.0

        monkeypatch.setattr(TokenManager, "_refresh", staticmethod(fake_refresh))
        tokens = await manager.load_tokens()
        assert len(tokens) == 2

    async def test_corrupt_pkl_skipped(self, secrets_dir, monkeypatch):
        """A corrupt .pkl is skipped without affecting .json files."""
        write_credentials(secrets_dir, "good.json")
        secrets_dir.joinpath("bad.pkl").write_bytes(b"not a pickle")
        manager = TokenManager(make_settings(secrets_dir))

        async def fake_refresh(session, credentials):
            return "good-token", 3600.0

        monkeypatch.setattr(TokenManager, "_refresh", staticmethod(fake_refresh))
        assert await manager.load_tokens() == ["good-token"]

    async def test_pkl_missing_fields_raises(self, secrets_dir, monkeypatch):
        """A .pkl whose Credentials object lacks fields is skipped."""
        # Pickle a bare object with no client_id/secret/refresh_token
        import pickle as pkl_mod

        secrets_dir.mkdir(parents=True, exist_ok=True)
        with open(secrets_dir / "empty.pkl", "wb") as f:
            pkl_mod.dump(object(), f)
        manager = TokenManager(make_settings(secrets_dir))

        async def fake_refresh(session, credentials):
            return "should-not-reach-here", 3600.0

        monkeypatch.setattr(TokenManager, "_refresh", staticmethod(fake_refresh))
        assert await manager.load_tokens() == []
