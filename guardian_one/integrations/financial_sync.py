"""Financial integration — stubs for Rocket Money and accounting sync.

Rocket Money (formerly Truebill) provides account aggregation.
These are interface definitions with placeholder implementations.
"""

from __future__ import annotations

import abc
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


class RocketMoneyProvider(FinancialProvider):
    """Rocket Money integration stub.

    To activate:
    1. Set ROCKET_MONEY_API_KEY env var (or use OAuth token)
    2. Optionally set ROCKET_MONEY_BASE_URL for sandbox testing
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key
        self._authenticated = False

    def authenticate(self) -> bool:
        # TODO: Validate API key / OAuth token with Rocket Money
        self._authenticated = False
        return self._authenticated

    def fetch_accounts(self) -> list[SyncedAccount]:
        if not self._authenticated:
            return []
        # TODO: Call Rocket Money accounts endpoint
        return []

    def fetch_transactions(self, start_date: str, end_date: str) -> list[SyncedTransaction]:
        if not self._authenticated:
            return []
        # TODO: Call Rocket Money transactions endpoint
        return []


class PlaidProvider(FinancialProvider):
    """Plaid integration stub (alternative to Rocket Money).

    To activate:
    1. Obtain Plaid client_id and secret from dashboard.plaid.com
    2. Set PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ENV env vars
    """

    def __init__(self, client_id: str | None = None, secret: str | None = None) -> None:
        self._client_id = client_id
        self._secret = secret
        self._authenticated = False

    def authenticate(self) -> bool:
        # TODO: Implement Plaid Link token exchange
        self._authenticated = False
        return self._authenticated

    def fetch_accounts(self) -> list[SyncedAccount]:
        if not self._authenticated:
            return []
        # TODO: Call Plaid /accounts/get
        return []

    def fetch_transactions(self, start_date: str, end_date: str) -> list[SyncedTransaction]:
        if not self._authenticated:
            return []
        # TODO: Call Plaid /transactions/get
        return []
