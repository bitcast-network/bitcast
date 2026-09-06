"""YouTube OAuth token management for the miner.

Two sources, selected by ``TOKEN_SOURCE``:

* ``local`` — credential files in ``BITCAST_SECRETS_DIR`` (default
  ``~/.bitcast/secrets``). Two formats are supported:

  - **JSON** (``*.json``) — the preferred format, holding ``client_id``,
    ``client_secret`` and ``refresh_token``.
  - **Pickle** (``*.pkl``) — legacy V1 format containing a pickled
    ``google.oauth2.credentials.Credentials`` object. The three fields are
    extracted to the same dict shape so the refresh path is shared. Miners
    upgrading from V1 can use existing ``.pkl`` files without conversion.

* ``api`` — the Bitcast credentials API serves ready-to-use access tokens
  (it owns the refresh tokens).

Tokens are loaded fresh on every validator request so they are never stale.
"""

import json
import pickle
import time
from pathlib import Path

import bittensor as bt
import httpx

from bitcast.config import Settings, get_settings

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

_REQUEST_TIMEOUT = 30.0
_EXPIRY_MARGIN = 300.0  # refresh this many seconds before actual expiry


class TokenConfigError(Exception):
    """The miner's token source is misconfigured."""


class TokenManager:
    """Loads and refreshes the miner's YouTube access tokens."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.secrets_dir = Path(self.settings.secrets_dir).expanduser()
        self._token_cache: dict[str, tuple[str, float]] = {}  # file name -> (token, expires_at)

    def init(self) -> None:
        """Validate the configured token source; raise before serving if unusable."""
        if self.settings.token_source == "api":
            if not self.settings.bitcast_api_url or not self.settings.bitcast_api_key:
                raise TokenConfigError("TOKEN_SOURCE=api requires BITCAST_API_URL and BITCAST_API_KEY")
            return
        if not self._credential_files():
            raise TokenConfigError(
                f"No credential files found in {self.secrets_dir}. Add JSON files with "
                "client_id, client_secret and refresh_token."
            )

    def _credential_files(self) -> list[Path]:
        if not self.secrets_dir.is_dir():
            return []
        json_files = sorted(self.secrets_dir.glob("*.json"))
        pkl_files = sorted(self.secrets_dir.glob("*.pkl"))
        return json_files + pkl_files

    async def load_tokens(self) -> list[str]:
        """Current access tokens for every configured account."""
        if self.settings.token_source == "api":
            return await self._load_from_api()
        return await self._load_from_local()

    async def _load_from_api(self) -> list[str]:
        url = f"{self.settings.bitcast_api_url}/api/v2/youtube/credentials/access-tokens"
        headers = {"X-API-Key": self.settings.bitcast_api_key or ""}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
                response.raise_for_status()
                data = response.json()
                return [item["access_token"] for item in data.get("tokens", []) if item.get("access_token")]
        except (httpx.HTTPError, TimeoutError, KeyError) as err:
            bt.logging.error(f"Failed to load tokens from API: {err}")
            return []

    async def _load_from_local(self) -> list[str]:
        tokens = []
        async with httpx.AsyncClient() as session:
            for path in self._credential_files():
                token = await self._token_for_file(session, path)
                if token:
                    tokens.append(token)
        return tokens

    async def _token_for_file(self, session: httpx.AsyncClient, path: Path) -> str | None:
        cached = self._token_cache.get(path.name)
        if cached and time.monotonic() < cached[1]:
            return cached[0]

        try:
            credentials = self._load_pkl_credentials(path) if path.suffix == ".pkl" else json.loads(path.read_text())
            token, expires_in = await self._refresh(session, credentials)
        except (
            OSError,
            json.JSONDecodeError,
            KeyError,
            ValueError,
            pickle.UnpicklingError,
            httpx.HTTPError,
            TimeoutError,
        ) as err:
            bt.logging.error(f"Could not refresh token from {path.name}: {err}")
            return None

        self._token_cache[path.name] = (token, time.monotonic() + expires_in - _EXPIRY_MARGIN)
        return token

    @staticmethod
    def _load_pkl_credentials(path: Path) -> dict[str, str]:
        """Load a V1 ``.pkl`` credentials file and extract the OAuth fields.

        V1 pickles ``google.oauth2.credentials.Credentials`` objects. We only
        need ``client_id``, ``client_secret`` and ``refresh_token`` — the same
        three fields the JSON format carries. The google-auth library is an
        optional dependency (V2 doesn't need it for anything else), so if it
        isn't installed we fall back to ``pickle.loads`` and pull the attributes
        off the raw object.
        """
        try:
            with open(path, "rb") as fh:
                creds = pickle.load(fh)
        except Exception as err:
            raise ValueError(f"Failed to unpickle {path.name}: {err}") from err

        client_id = str(getattr(creds, "client_id", "") or "")
        client_secret = str(getattr(creds, "client_secret", "") or "")
        refresh_token = str(getattr(creds, "refresh_token", "") or "")
        if not (client_id and client_secret and refresh_token):
            missing = [
                k
                for k, v in [
                    ("client_id", client_id),
                    ("client_secret", client_secret),
                    ("refresh_token", refresh_token),
                ]
                if not v
            ]
            raise ValueError(f"{path.name} missing OAuth fields: {missing}")
        return {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        }

    @staticmethod
    async def _refresh(session: httpx.AsyncClient, credentials: dict) -> tuple[str, float]:
        """Exchange a refresh token for a fresh access token at Google's OAuth endpoint."""
        payload = {
            "client_id": credentials["client_id"],
            "client_secret": credentials["client_secret"],
            "refresh_token": credentials["refresh_token"],
            "grant_type": "refresh_token",
        }
        response = await session.post(GOOGLE_TOKEN_URL, data=payload, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        return data["access_token"], float(data.get("expires_in", 3600))
