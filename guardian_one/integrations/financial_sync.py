"""Financial integration — Rocket Money and Plaid providers.

Providers auto-detect credentials from environment variables.
When credentials are absent they operate in offline mode.
"""

from __future__ import annotations

import abc
import os
from dataclasses import dataclass
from typing import Any


@dataclass
class SyncedAccount:
    name: str
    account_type: str
    balance: float
    institution: str
    last_updated: str
    raw: dict[str, Any] | None = None


@dataclass
class SyncedTransaction:
    date: str
    description: str
    amount: float
    category: str
    account: str
    raw: dict[str, Any] | None = None


class FinancialProvider(abc.ABC):
    """Abstract interface for financial data providers."""

    @abc.abstractmethod
    def authenticate(self) -> bool: ...

    @abc.abstractmethod
    def fetch_accounts(self) -> list[SyncedAccount]: ...

    @abc.abstractmethod
    def fetch_transactions(self, start_date: str, end_date: str) -> list[SyncedTransaction]: ...

    @property
    @abc.abstractmethod
    def has_credentials(self) -> bool: ...

    @property
    @abc.abstractmethod
    def provider_name(self) -> str: ...


class RocketMoneyProvider(FinancialProvider):
    """Rocket Money integration.

    Credentials lookup:
    1. ``api_key`` constructor arg
    2. ``ROCKET_MONEY_API_KEY`` env var

    To activate:
    1. Obtain an API key from Rocket Money
    2. Set ROCKET_MONEY_API_KEY env var
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("ROCKET_MONEY_API_KEY", "")
        self._base_url = os.environ.get(
            "ROCKET_MONEY_BASE_URL", "https://api.rocketmoney.com"
        )
        self._authenticated = False
        self._last_error: str = ""

    @property
    def provider_name(self) -> str:
        return "rocket_money"

    @property
    def has_credentials(self) -> bool:
        return bool(self._api_key)

    @property
    def last_error(self) -> str:
        return self._last_error

    def authenticate(self) -> bool:
        if not self.has_credentials:
            self._last_error = "Missing ROCKET_MONEY_API_KEY env var."
            self._authenticated = False
            return False

        try:
            # Real: validate key with Rocket Money health endpoint
            self._authenticated = False
            self._last_error = "API validation not yet implemented — key detected"
            return self._authenticated
        except Exception as exc:
            self._last_error = f"Rocket Money auth failed: {exc}"
            self._authenticated = False
            return False

    def fetch_accounts(self) -> list[SyncedAccount]:
        if not self._authenticated:
            return []
        # Real: GET /api/v1/accounts with API key header
        return []

    def fetch_transactions(self, start_date: str, end_date: str) -> list[SyncedTransaction]:
        if not self._authenticated:
            return []
        # Real: GET /api/v1/transactions?start={start}&end={end}
        return []

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "has_credentials": self.has_credentials,
            "authenticated": self._authenticated,
            "base_url": self._base_url,
            "last_error": self._last_error,
        }


class PlaidProvider(FinancialProvider):
    """Plaid integration (alternative to Rocket Money).

    Credentials lookup:
    1. Constructor args
    2. ``PLAID_CLIENT_ID``, ``PLAID_SECRET``, ``PLAID_ENV`` env vars

    Environments: sandbox, development, production

    To activate:
    1. Obtain client_id and secret from dashboard.plaid.com
    2. Set PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ENV env vars
    """

    VALID_ENVS = ("sandbox", "development", "production")

    def __init__(
        self,
        client_id: str | None = None,
        secret: str | None = None,
        env: str | None = None,
    ) -> None:
        self._client_id = client_id or os.environ.get("PLAID_CLIENT_ID", "")
        self._secret = secret or os.environ.get("PLAID_SECRET", "")
        self._env = env or os.environ.get("PLAID_ENV", "sandbox")
        self._authenticated = False
        self._last_error: str = ""

    @property
    def provider_name(self) -> str:
        return "plaid"

    @property
    def has_credentials(self) -> bool:
        return bool(self._client_id and self._secret)

    @property
    def last_error(self) -> str:
        return self._last_error

    def authenticate(self) -> bool:
        if not self.has_credentials:
            self._last_error = "Missing PLAID_CLIENT_ID or PLAID_SECRET env vars."
            self._authenticated = False
            return False

        if self._env not in self.VALID_ENVS:
            self._last_error = (
                f"Invalid PLAID_ENV '{self._env}'. "
                f"Must be one of: {', '.join(self.VALID_ENVS)}"
            )
            self._authenticated = False
            return False

        try:
            # Real: plaid.Client(client_id, secret, env) → test connection
            self._authenticated = False
            self._last_error = "Plaid client not yet implemented — credentials detected"
            return self._authenticated
        except Exception as exc:
            self._last_error = f"Plaid auth failed: {exc}"
            self._authenticated = False
            return False

    def fetch_accounts(self) -> list[SyncedAccount]:
        if not self._authenticated:
            return []
        # Real: plaid.Accounts.get(access_token)
        return []

    def fetch_transactions(self, start_date: str, end_date: str) -> list[SyncedTransaction]:
        if not self._authenticated:
            return []
        # Real: plaid.Transactions.get(access_token, start, end)
        return []

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "has_credentials": self.has_credentials,
            "authenticated": self._authenticated,
            "environment": self._env,
            "last_error": self._last_error,
        }
