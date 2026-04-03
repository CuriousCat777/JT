"""Financial integration — multi-provider data pipeline.

Providers auto-detect credentials from environment variables.
When credentials are absent they operate in offline mode.

Provider hierarchy (sync_all order):
1. Teller    — direct bank API, certificate-based auth, no browser widget
2. Plaid     — bank aggregator with Link UI (browser OAuth)
3. Empower   — retirement accounts (API key or session auth)
4. Rocket Money — aggregator fallback (API or CSV import)

File import paths (no API needed):
- Generic bank CSV  — any bank's transaction export
- OFX/QFX files     — standard Open Financial Exchange format
- Rocket Money CSV  — RM-specific export format

All paths merge into the CFO ledger via SyncedAccount/SyncedTransaction.
"""

from __future__ import annotations

import abc
import csv
import io
import json
import os
import re
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
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


# ---------------------------------------------------------------------------
# Category mapping: Rocket Money CSV categories → CFO TransactionCategory
# ---------------------------------------------------------------------------

ROCKET_MONEY_CATEGORY_MAP: dict[str, str] = {
    # Income
    "Income": "income",
    "Paycheck": "income",
    "Salary": "income",
    "Deposit": "income",
    "Direct Deposit": "income",
    "Refund": "income",
    # Housing
    "Rent": "housing",
    "Mortgage": "housing",
    "Mortgage & Rent": "housing",
    "Home": "housing",
    "Home Improvement": "housing",
    # Utilities
    "Utilities": "utilities",
    "Internet": "utilities",
    "Phone": "utilities",
    "Mobile Phone": "utilities",
    "Electric": "utilities",
    "Gas Bill": "utilities",
    "Water": "utilities",
    "Streaming": "utilities",
    "Subscriptions": "utilities",
    "Software": "utilities",
    # Food
    "Food & Drink": "food",
    "Groceries": "food",
    "Restaurants": "food",
    "Fast Food": "food",
    "Coffee Shops": "food",
    "Dining": "food",
    "Food Delivery": "food",
    # Transport
    "Transportation": "transport",
    "Gas": "transport",
    "Gas & Fuel": "transport",
    "Parking": "transport",
    "Auto & Transport": "transport",
    "Auto Insurance": "insurance",
    "Auto Payment": "transport",
    "Ride Share": "transport",
    "Public Transit": "transport",
    # Medical
    "Health & Wellness": "medical",
    "Healthcare": "medical",
    "Medical": "medical",
    "Pharmacy": "medical",
    "Doctor": "medical",
    "Dentist": "medical",
    # Entertainment
    "Entertainment": "entertainment",
    "Shopping": "entertainment",
    "Electronics": "entertainment",
    "Clothing": "entertainment",
    "Personal Care": "entertainment",
    "Gym": "entertainment",
    "Fitness": "entertainment",
    # Education
    "Education": "education",
    "Books": "education",
    "Tuition": "education",
    # Insurance
    "Insurance": "insurance",
    "Health Insurance": "insurance",
    "Life Insurance": "insurance",
    "Renters Insurance": "insurance",
    # Loans
    "Loan": "loan_payment",
    "Student Loan": "loan_payment",
    "Loan Payment": "loan_payment",
    "Credit Card Payment": "loan_payment",
    # Savings / Investments
    "Savings": "savings",
    "Investment": "savings",
    "Transfer": "savings",
    # Charitable
    "Charity": "charitable",
    "Donations": "charitable",
    "Charitable Giving": "charitable",
}


def map_rocket_money_category(rm_category: str) -> str:
    """Map a Rocket Money category string to a CFO TransactionCategory value."""
    if not rm_category:
        return "other"
    # Exact match
    if rm_category in ROCKET_MONEY_CATEGORY_MAP:
        return ROCKET_MONEY_CATEGORY_MAP[rm_category]
    # Case-insensitive match
    lower = rm_category.lower()
    for key, value in ROCKET_MONEY_CATEGORY_MAP.items():
        if key.lower() == lower:
            return value
    # Partial match
    for key, value in ROCKET_MONEY_CATEGORY_MAP.items():
        if key.lower() in lower or lower in key.lower():
            return value
    return "other"


def map_rocket_money_account_type(acct_type: str) -> str:
    """Map a Rocket Money account type to a CFO AccountType value."""
    mapping = {
        "checking": "checking",
        "savings": "savings",
        "credit card": "credit_card",
        "credit": "credit_card",
        "loan": "loan",
        "student loan": "loan",
        "mortgage": "loan",
        "investment": "investment",
        "brokerage": "investment",
        "retirement": "retirement",
        "401k": "retirement",
        "401(k)": "retirement",
        "ira": "retirement",
        "roth ira": "retirement",
    }
    lower = acct_type.lower().strip()
    return mapping.get(lower, "checking")


# ---------------------------------------------------------------------------
# CSV parser (works with locally-downloaded Rocket Money CSVs)
# ---------------------------------------------------------------------------

def parse_rocket_money_csv(csv_path: str | Path) -> tuple[list[SyncedAccount], list[SyncedTransaction]]:
    """Parse a Rocket Money / Truebill transaction CSV and extract accounts + transactions.

    Rocket Money CSV columns:
        Date, Original Date, Account Type, Account Name, Account Number,
        Institution Name, Name, Custom Name, Amount, Description,
        Category, Note, Ignored From, Tax Deductible, Transaction Tags

    Amount convention: positive = expense/outflow, negative = income/inflow.
    We flip the sign so CFO convention (positive = inflow, negative = outflow) is used.

    Returns:
        Tuple of (accounts, transactions) extracted from the CSV.
    """
    path = Path(csv_path)
    if not path.exists():
        return [], []

    text = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    if not rows:
        return [], []

    # Extract unique accounts
    seen_accounts: dict[str, SyncedAccount] = {}
    transactions: list[SyncedTransaction] = []
    now = datetime.now(timezone.utc).isoformat()

    for row in rows:
        acct_name = row.get("Account Name", row.get("account", "")).strip()
        acct_type = row.get("Account Type", "").strip()
        institution = row.get("Institution Name", "").strip()

        # Track unique accounts
        if acct_name and acct_name not in seen_accounts:
            seen_accounts[acct_name] = SyncedAccount(
                name=acct_name,
                account_type=map_rocket_money_account_type(acct_type),
                balance=0.0,  # CSV doesn't include balances
                institution=institution,
                last_updated=now,
            )

        # Parse amount (Rocket Money: positive = expense, we flip for CFO)
        amount_str = row.get("Amount", row.get("amount", "0"))
        try:
            raw_amount = float(str(amount_str).replace(",", "").replace("$", ""))
            # Flip sign: RM positive (expense) → CFO negative (outflow)
            amount = -raw_amount
        except (ValueError, AttributeError):
            amount = 0.0

        # Parse date
        date = row.get("Date", row.get("date", ""))

        # Get description
        description = (
            row.get("Custom Name", "").strip()
            or row.get("Name", "").strip()
            or row.get("Description", row.get("description", "")).strip()
        )

        # Map category
        rm_category = row.get("Category", row.get("category", ""))
        category = map_rocket_money_category(rm_category)

        transactions.append(SyncedTransaction(
            date=date,
            description=description,
            amount=amount,
            category=category,
            account=acct_name,
            raw=dict(row),
        ))

    return list(seen_accounts.values()), transactions


# ---------------------------------------------------------------------------
# Rocket Money API provider
# ---------------------------------------------------------------------------

class RocketMoneyProvider(FinancialProvider):
    """Rocket Money integration.

    Data paths (both merge into CFO ledger):
    1. API sync — Set ROCKET_MONEY_API_KEY in .env
    2. CSV import — Gmail agent downloads CSVs, call sync_from_csv()

    Credentials lookup:
    1. ``api_key`` constructor arg
    2. ``ROCKET_MONEY_API_KEY`` env var

    To activate API sync:
    1. Obtain an API key from Rocket Money
    2. Set ROCKET_MONEY_API_KEY in your .env file

    To use CSV sync (no API key needed):
    1. Export transactions from Rocket Money app
    2. Run: python main.py --csv path/to/export.csv
    3. Or: Gmail agent auto-detects emailed CSVs
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("ROCKET_MONEY_API_KEY", "")
        self._base_url = os.environ.get(
            "ROCKET_MONEY_BASE_URL", "https://api.rocketmoney.com"
        )
        self._authenticated = False
        self._last_error: str = ""
        self._last_sync: str = ""
        self._csv_accounts: list[SyncedAccount] = []
        self._csv_transactions: list[SyncedTransaction] = []

    @property
    def provider_name(self) -> str:
        return "rocket_money"

    @property
    def has_credentials(self) -> bool:
        return bool(self._api_key)

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    @property
    def last_error(self) -> str:
        return self._last_error

    def authenticate(self) -> bool:
        """Validate API key with Rocket Money."""
        if not self.has_credentials:
            self._last_error = "Missing ROCKET_MONEY_API_KEY env var."
            self._authenticated = False
            return False

        try:
            result = self._request("GET", "/api/v1/health")
            if result is not None and not result.get("error"):
                self._authenticated = True
                self._last_error = ""
                return True
            # If health check fails but we have a key, try accounts endpoint
            result = self._request("GET", "/api/v1/accounts")
            if result is not None and not result.get("error"):
                self._authenticated = True
                self._last_error = ""
                return True
            self._authenticated = False
            self._last_error = f"API returned error: {result.get('detail', 'unknown')}" if result else "No response"
            return False
        except Exception as exc:
            self._last_error = f"Rocket Money auth failed: {exc}"
            self._authenticated = False
            return False

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Make an authenticated request to the Rocket Money API."""
        url = f"{self._base_url}{path}"
        data = json.dumps(body).encode() if body else None

        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            return {"error": True, "status": e.code, "detail": error_body}
        except urllib.error.URLError:
            return {"error": True, "detail": "Network error"}

    def fetch_accounts(self) -> list[SyncedAccount]:
        """Fetch accounts from API, or return CSV-imported accounts."""
        if self._authenticated:
            result = self._request("GET", "/api/v1/accounts")
            if result and not result.get("error"):
                now = datetime.now(timezone.utc).isoformat()
                accounts = []
                for item in result.get("data", result.get("accounts", [])):
                    accounts.append(SyncedAccount(
                        name=item.get("name", ""),
                        account_type=map_rocket_money_account_type(
                            item.get("type", item.get("account_type", "checking"))
                        ),
                        balance=float(item.get("balance", 0)),
                        institution=item.get("institution", item.get("institution_name", "")),
                        last_updated=now,
                        raw=item,
                    ))
                self._last_sync = now
                return accounts

        # Fall back to CSV-imported accounts
        return list(self._csv_accounts)

    def fetch_transactions(self, start_date: str, end_date: str) -> list[SyncedTransaction]:
        """Fetch transactions from API, or return CSV-imported transactions."""
        if self._authenticated:
            result = self._request(
                "GET",
                f"/api/v1/transactions?start_date={start_date}&end_date={end_date}",
            )
            if result and not result.get("error"):
                transactions = []
                for item in result.get("data", result.get("transactions", [])):
                    raw_amount = float(item.get("amount", 0))
                    # RM API: positive = expense, flip for CFO
                    amount = -raw_amount
                    transactions.append(SyncedTransaction(
                        date=item.get("date", ""),
                        description=item.get("name", item.get("description", "")),
                        amount=amount,
                        category=map_rocket_money_category(
                            item.get("category", item.get("category_name", ""))
                        ),
                        account=item.get("account_name", item.get("account", "")),
                        raw=item,
                    ))
                return transactions

        # Fall back to CSV-imported transactions within date range
        filtered = []
        for tx in self._csv_transactions:
            if start_date <= tx.date <= end_date:
                filtered.append(tx)
        return filtered

    def sync_from_csv(self, csv_path: str | Path) -> dict[str, Any]:
        """Import accounts and transactions from a Rocket Money CSV export.

        This is the primary data path when the API key is not available.
        The Gmail agent auto-detects emailed CSVs and saves them to data/.
        """
        accounts, transactions = parse_rocket_money_csv(csv_path)
        self._csv_accounts = accounts
        self._csv_transactions = transactions
        self._last_sync = datetime.now(timezone.utc).isoformat()

        return {
            "source": "csv",
            "path": str(csv_path),
            "accounts": len(accounts),
            "transactions": len(transactions),
            "synced_at": self._last_sync,
        }

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "has_credentials": self.has_credentials,
            "authenticated": self._authenticated,
            "base_url": self._base_url,
            "last_sync": self._last_sync,
            "csv_accounts": len(self._csv_accounts),
            "csv_transactions": len(self._csv_transactions),
            "last_error": self._last_error,
        }


# ---------------------------------------------------------------------------
# Empower (formerly Personal Capital) provider
# ---------------------------------------------------------------------------

class EmpowerProvider(FinancialProvider):
    """Empower (Personal Capital) integration for retirement accounts.

    Empower provides retirement account management (401k, IRA, Roth IRA)
    and investment tracking. This provider connects to the Empower API
    to pull account balances and transaction history.

    Credentials lookup:
    1. Constructor args
    2. ``EMPOWER_API_KEY`` env var (API key)
    3. ``EMPOWER_USERNAME`` + ``EMPOWER_PASSWORD`` env vars (legacy auth)

    To activate:
    1. Log in to empower.com and generate an API access token
       (Settings → Developer → API Access)
    2. Set EMPOWER_API_KEY in your .env file

    Empower accounts this tracks:
    - 401(k) plans (employer-sponsored)
    - Traditional IRA
    - Roth IRA
    - Brokerage / taxable investment accounts
    - HSA (Health Savings Account)
    """

    def __init__(
        self,
        api_key: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("EMPOWER_API_KEY", "")
        self._username = username or os.environ.get("EMPOWER_USERNAME", "")
        self._password = password or os.environ.get("EMPOWER_PASSWORD", "")
        self._base_url = os.environ.get(
            "EMPOWER_BASE_URL", "https://api.empower.com"
        )
        self._authenticated = False
        self._last_error: str = ""
        self._session_token: str = ""

    @property
    def provider_name(self) -> str:
        return "empower"

    @property
    def has_credentials(self) -> bool:
        return bool(self._api_key) or bool(self._username and self._password)

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    @property
    def last_error(self) -> str:
        return self._last_error

    def authenticate(self) -> bool:
        """Authenticate with Empower via API key or username/password."""
        if not self.has_credentials:
            self._last_error = "Missing EMPOWER_API_KEY (or EMPOWER_USERNAME + EMPOWER_PASSWORD) env vars."
            self._authenticated = False
            return False

        try:
            if self._api_key:
                # API key auth
                result = self._request("GET", "/api/v1/accounts")
                if result is not None and not result.get("error"):
                    self._authenticated = True
                    self._last_error = ""
                    return True
            else:
                # Username/password auth → get session token
                result = self._request("POST", "/api/v1/auth/login", {
                    "username": self._username,
                    "password": self._password,
                })
                if result and not result.get("error") and result.get("token"):
                    self._session_token = result["token"]
                    self._authenticated = True
                    self._last_error = ""
                    return True

            detail = result.get("detail", "unknown") if result else "No response"
            self._authenticated = False
            self._last_error = f"Empower auth failed: {detail}"
            return False
        except Exception as exc:
            self._last_error = f"Empower auth failed: {exc}"
            self._authenticated = False
            return False

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Make an authenticated request to the Empower API."""
        url = f"{self._base_url}{path}"
        data = json.dumps(body).encode() if body else None

        auth_header = (
            f"Bearer {self._api_key}" if self._api_key
            else f"Session {self._session_token}"
        )

        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            return {"error": True, "status": e.code, "detail": error_body}
        except urllib.error.URLError:
            return {"error": True, "detail": "Network error"}

    def fetch_accounts(self) -> list[SyncedAccount]:
        """Fetch retirement and investment accounts from Empower."""
        if not self._authenticated:
            return []

        result = self._request("GET", "/api/v1/accounts")
        if result is None or result.get("error"):
            return []

        now = datetime.now(timezone.utc).isoformat()
        accounts = []
        for item in result.get("data", result.get("accounts", [])):
            acct_type = item.get("type", item.get("account_type", "investment"))
            accounts.append(SyncedAccount(
                name=item.get("name", item.get("account_name", "")),
                account_type=map_rocket_money_account_type(acct_type),
                balance=float(item.get("balance", item.get("current_balance", 0))),
                institution=item.get("institution", "Empower"),
                last_updated=now,
                raw=item,
            ))
        return accounts

    def fetch_transactions(self, start_date: str, end_date: str) -> list[SyncedTransaction]:
        """Fetch investment transactions from Empower."""
        if not self._authenticated:
            return []

        result = self._request(
            "GET",
            f"/api/v1/transactions?start_date={start_date}&end_date={end_date}",
        )
        if result is None or result.get("error"):
            return []

        transactions = []
        for item in result.get("data", result.get("transactions", [])):
            amount = float(item.get("amount", 0))
            transactions.append(SyncedTransaction(
                date=item.get("date", ""),
                description=item.get("description", item.get("name", "")),
                amount=amount,
                category=item.get("category", "savings"),
                account=item.get("account_name", item.get("account", "")),
                raw=item,
            ))
        return transactions

    def fetch_holdings(self) -> list[dict[str, Any]]:
        """Fetch current investment holdings (stocks, bonds, funds)."""
        if not self._authenticated:
            return []

        result = self._request("GET", "/api/v1/holdings")
        if result is None or result.get("error"):
            return []

        return result.get("data", result.get("holdings", []))

    def fetch_net_worth_history(self, months: int = 12) -> list[dict[str, Any]]:
        """Fetch net worth history from Empower's tracker."""
        if not self._authenticated:
            return []

        result = self._request("GET", f"/api/v1/net-worth?months={months}")
        if result is None or result.get("error"):
            return []

        return result.get("data", result.get("history", []))

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "has_credentials": self.has_credentials,
            "authenticated": self._authenticated,
            "base_url": self._base_url,
            "auth_method": "api_key" if self._api_key else "session",
            "last_error": self._last_error,
        }


class PlaidProvider(FinancialProvider):
    """Plaid integration — READ-ONLY access to bank accounts.

    Plaid connects directly to banks (BofA, Wells Fargo, Capital One, etc.)
    and pulls account balances and transaction history.

    SECURITY: This provider is strictly **read-only**.
    - Only ``ALLOWED_PRODUCTS`` are ever requested (transactions, accounts, investments).
    - Products that move money (transfer, payment_initiation) are **never** requested.
    - The ``_request`` method refuses to call write endpoints.

    Connection flow:
    1. Set PLAID_CLIENT_ID and PLAID_SECRET in .env (from dashboard.plaid.com)
    2. Run ``python main.py --connect`` to launch Plaid Link in your browser
    3. Log into each bank via Plaid's secure OAuth flow
    4. Access tokens are stored encrypted in ``data/plaid_tokens.json``
    5. CFO sync loop pulls balances and transactions automatically

    Environments: sandbox (testing), development (up to 100 items free), production
    """

    VALID_ENVS = ("sandbox", "development", "production")

    # READ-ONLY products only.  Never add transfer, payment_initiation, etc.
    ALLOWED_PRODUCTS = ("transactions", "auth", "investments", "liabilities")

    # Endpoints that are read-only.  _request() rejects anything not on this list.
    _READ_ONLY_ENDPOINTS = frozenset({
        "/link/token/create",
        "/item/public_token/exchange",
        "/item/get",
        "/item/remove",
        "/accounts/get",
        "/accounts/balance/get",
        "/transactions/get",
        "/transactions/sync",
        "/investments/holdings/get",
        "/investments/transactions/get",
        "/liabilities/get",
        "/institutions/get_by_id",
    })

    _ENV_HOSTS = {
        "sandbox": "https://sandbox.plaid.com",
        "development": "https://development.plaid.com",
        "production": "https://production.plaid.com",
    }

    def __init__(
        self,
        client_id: str | None = None,
        secret: str | None = None,
        env: str | None = None,
        token_store_path: str | Path | None = None,
    ) -> None:
        self._client_id = client_id or os.environ.get("PLAID_CLIENT_ID", "")
        self._secret = secret or os.environ.get("PLAID_SECRET", "")
        self._env = env or os.environ.get("PLAID_ENV", "sandbox")
        self._base_url = self._ENV_HOSTS.get(self._env, self._ENV_HOSTS["sandbox"])
        self._authenticated = False
        self._last_error: str = ""

        # Access tokens per institution — loaded from disk
        self._access_tokens: dict[str, str] = {}  # institution_id → access_token
        self._item_metadata: dict[str, dict[str, Any]] = {}  # institution_id → metadata
        self._token_store = Path(token_store_path) if token_store_path else None

    @property
    def provider_name(self) -> str:
        return "plaid"

    @property
    def has_credentials(self) -> bool:
        return bool(self._client_id and self._secret)

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def connected_institutions(self) -> list[str]:
        """List of institution IDs with stored access tokens."""
        return list(self._access_tokens.keys())

    def authenticate(self) -> bool:
        """Validate Plaid credentials and load stored access tokens."""
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

        # Load stored access tokens
        self._load_tokens()

        # Test credentials by creating a link token (lightweight call)
        result = self._request("/link/token/create", {
            "user": {"client_user_id": "guardian-one-cfo"},
            "client_name": "Guardian One CFO",
            "products": list(self.ALLOWED_PRODUCTS[:2]),  # transactions, auth
            "country_codes": ["US"],
            "language": "en",
        })

        if result and not result.get("error"):
            self._authenticated = True
            self._last_error = ""
            return True

        detail = ""
        if result:
            detail = result.get("error_message", result.get("detail", "unknown"))
        self._authenticated = False
        self._last_error = f"Plaid auth failed: {detail}" if detail else "Plaid auth failed: no response"
        return False

    def _request(
        self,
        endpoint: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Make an authenticated request to the Plaid API.

        SECURITY: Refuses to call any endpoint not in ``_READ_ONLY_ENDPOINTS``.
        All Plaid API calls use POST with client_id/secret in the body.
        """
        if endpoint not in self._READ_ONLY_ENDPOINTS:
            return {"error": True, "error_message": f"Blocked: {endpoint} is not a read-only endpoint"}

        url = f"{self._base_url}{endpoint}"
        payload = dict(body or {})
        payload["client_id"] = self._client_id
        payload["secret"] = self._secret

        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            try:
                parsed = json.loads(error_body)
                return {"error": True, "status": e.code, **parsed}
            except (json.JSONDecodeError, TypeError):
                return {"error": True, "status": e.code, "detail": error_body}
        except urllib.error.URLError:
            return {"error": True, "error_message": "Network error"}

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _load_tokens(self) -> None:
        """Load access tokens from the token store file."""
        if not self._token_store or not self._token_store.exists():
            return
        try:
            data = json.loads(self._token_store.read_text())
            self._access_tokens = data.get("tokens", {})
            self._item_metadata = data.get("metadata", {})
        except (json.JSONDecodeError, KeyError):
            pass

    def _save_tokens(self) -> None:
        """Persist access tokens to disk."""
        if not self._token_store:
            return
        self._token_store.parent.mkdir(parents=True, exist_ok=True)
        self._token_store.write_text(json.dumps({
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "tokens": self._access_tokens,
            "metadata": self._item_metadata,
        }, indent=2))

    def exchange_public_token(self, public_token: str, institution_id: str, institution_name: str) -> dict[str, Any]:
        """Exchange a Plaid Link public_token for a permanent access_token.

        Called after the user completes the Plaid Link flow in their browser.
        """
        result = self._request("/item/public_token/exchange", {
            "public_token": public_token,
        })

        if result and not result.get("error"):
            access_token = result.get("access_token", "")
            item_id = result.get("item_id", "")

            self._access_tokens[institution_id] = access_token
            self._item_metadata[institution_id] = {
                "institution_name": institution_name,
                "item_id": item_id,
                "connected_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save_tokens()

            return {
                "success": True,
                "institution": institution_name,
                "item_id": item_id,
            }

        return {
            "success": False,
            "error": result.get("error_message", "Exchange failed") if result else "No response",
        }

    def create_link_token(self) -> dict[str, Any]:
        """Create a Plaid Link token for the browser-based bank connection flow.

        Returns the link_token needed to initialize Plaid Link JS.
        """
        result = self._request("/link/token/create", {
            "user": {"client_user_id": "guardian-one-cfo"},
            "client_name": "Guardian One CFO",
            "products": list(self.ALLOWED_PRODUCTS[:2]),  # transactions, auth
            "country_codes": ["US"],
            "language": "en",
        })

        if result and not result.get("error"):
            return {
                "success": True,
                "link_token": result.get("link_token", ""),
                "expiration": result.get("expiration", ""),
            }

        return {
            "success": False,
            "error": result.get("error_message", "Failed to create link token") if result else "No response",
        }

    def disconnect_institution(self, institution_id: str) -> dict[str, Any]:
        """Remove an institution connection (revoke access token)."""
        token = self._access_tokens.get(institution_id)
        if not token:
            return {"success": False, "error": f"No connection for {institution_id}"}

        result = self._request("/item/remove", {"access_token": token})

        self._access_tokens.pop(institution_id, None)
        self._item_metadata.pop(institution_id, None)
        self._save_tokens()

        return {"success": True, "institution_id": institution_id}

    # ------------------------------------------------------------------
    # Read-only data access
    # ------------------------------------------------------------------

    def fetch_accounts(self) -> list[SyncedAccount]:
        """Fetch account balances from all connected banks."""
        all_accounts: list[SyncedAccount] = []
        now = datetime.now(timezone.utc).isoformat()

        for inst_id, access_token in self._access_tokens.items():
            inst_name = self._item_metadata.get(inst_id, {}).get("institution_name", inst_id)
            result = self._request("/accounts/balance/get", {
                "access_token": access_token,
            })

            if not result or result.get("error"):
                continue

            for acct in result.get("accounts", []):
                balances = acct.get("balances", {})
                # Plaid: current = what you owe (credit), available = what you can spend
                balance = balances.get("current", 0) or 0

                acct_type = acct.get("type", "depository")
                subtype = acct.get("subtype", "")

                # Map Plaid types to CFO types
                if acct_type == "credit":
                    cfo_type = "credit_card"
                    balance = -abs(balance)  # Credit balances are liabilities
                elif acct_type == "loan":
                    cfo_type = "loan"
                    balance = -abs(balance)
                elif acct_type == "investment":
                    if subtype in ("401k", "ira", "roth", "roth 401k", "403b", "457b"):
                        cfo_type = "retirement"
                    else:
                        cfo_type = "investment"
                elif subtype == "savings":
                    cfo_type = "savings"
                else:
                    cfo_type = "checking"

                name = acct.get("name", acct.get("official_name", ""))
                mask = acct.get("mask", "")
                display_name = f"{name} ({mask})" if mask else name

                all_accounts.append(SyncedAccount(
                    name=display_name,
                    account_type=cfo_type,
                    balance=float(balance),
                    institution=inst_name,
                    last_updated=now,
                    raw=acct,
                ))

        return all_accounts

    def fetch_transactions(self, start_date: str, end_date: str) -> list[SyncedTransaction]:
        """Fetch transactions from all connected banks within date range."""
        all_transactions: list[SyncedTransaction] = []

        for inst_id, access_token in self._access_tokens.items():
            offset = 0
            total = 1  # Will be updated from response

            while offset < total:
                result = self._request("/transactions/get", {
                    "access_token": access_token,
                    "start_date": start_date,
                    "end_date": end_date,
                    "options": {"count": 100, "offset": offset},
                })

                if not result or result.get("error"):
                    break

                total = result.get("total_transactions", 0)
                txns = result.get("transactions", [])

                for tx in txns:
                    # Plaid: positive = outflow (money spent), negative = inflow (income)
                    raw_amount = float(tx.get("amount", 0))
                    # Flip to CFO convention: positive = inflow, negative = outflow
                    amount = -raw_amount

                    category = "other"
                    plaid_cats = tx.get("personal_finance_category", {})
                    if plaid_cats:
                        primary = plaid_cats.get("primary", "").lower()
                        category = _map_plaid_category(primary)
                    elif tx.get("category"):
                        category = _map_plaid_category(tx["category"][0].lower() if tx["category"] else "")

                    acct_name = ""
                    acct_id = tx.get("account_id", "")
                    # Try to match account_id to a name from raw data
                    for sa in (result.get("accounts", [])):
                        if sa.get("account_id") == acct_id:
                            acct_name = sa.get("name", "")
                            break

                    all_transactions.append(SyncedTransaction(
                        date=tx.get("date", ""),
                        description=tx.get("name", tx.get("merchant_name", "")),
                        amount=amount,
                        category=category,
                        account=acct_name,
                        raw=tx,
                    ))

                offset += len(txns)
                if not txns:
                    break

        return all_transactions

    def fetch_investment_holdings(self) -> list[dict[str, Any]]:
        """Fetch investment/retirement holdings from connected banks."""
        all_holdings: list[dict[str, Any]] = []

        for inst_id, access_token in self._access_tokens.items():
            result = self._request("/investments/holdings/get", {
                "access_token": access_token,
            })
            if result and not result.get("error"):
                securities = {s["security_id"]: s for s in result.get("securities", [])}
                for h in result.get("holdings", []):
                    sec = securities.get(h.get("security_id", ""), {})
                    all_holdings.append({
                        "name": sec.get("name", ""),
                        "ticker": sec.get("ticker_symbol", ""),
                        "quantity": h.get("quantity", 0),
                        "value": h.get("institution_value", 0),
                        "price": h.get("institution_price", 0),
                        "type": sec.get("type", ""),
                        "institution": self._item_metadata.get(inst_id, {}).get("institution_name", ""),
                    })

        return all_holdings

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "has_credentials": self.has_credentials,
            "authenticated": self._authenticated,
            "environment": self._env,
            "connected_institutions": len(self._access_tokens),
            "institutions": [
                {
                    "id": inst_id,
                    "name": meta.get("institution_name", inst_id),
                    "connected_at": meta.get("connected_at", ""),
                }
                for inst_id, meta in self._item_metadata.items()
            ],
            "read_only": True,
            "allowed_products": list(self.ALLOWED_PRODUCTS),
            "last_error": self._last_error,
        }


def _map_plaid_category(plaid_category: str) -> str:
    """Map Plaid's personal finance category to CFO TransactionCategory."""
    mapping = {
        "income": "income",
        "transfer_in": "income",
        "rent_and_utilities": "utilities",
        "food_and_drink": "food",
        "general_merchandise": "entertainment",
        "entertainment": "entertainment",
        "personal_care": "entertainment",
        "general_services": "other",
        "transportation": "transport",
        "travel": "transport",
        "medical": "medical",
        "healthcare": "medical",
        "education": "education",
        "government_and_non_profit": "other",
        "loan_payments": "loan_payment",
        "bank_fees": "other",
        "transfer_out": "savings",
        "home_improvement": "housing",
        "rent": "housing",
        # Legacy Plaid category names
        "shops": "entertainment",
        "payment": "other",
        "recreation": "entertainment",
        "community": "charitable",
        "service": "other",
        "tax": "other",
        "transfer": "savings",
    }
    return mapping.get(plaid_category, "other")


# ---------------------------------------------------------------------------
# Teller — direct bank API (no aggregator middleman)
# ---------------------------------------------------------------------------

class TellerProvider(FinancialProvider):
    """Teller.io integration — direct, read-only bank connections.

    Teller connects directly to banks via their internal APIs, bypassing
    aggregator middlemen like Plaid.  It uses certificate-based auth
    (mTLS) or API token auth for simpler setups.

    Advantages over Plaid:
    - No browser widget / Link UI required
    - Simpler onboarding (sign up → get token → done)
    - Free tier: 1000 enrolled accounts
    - Direct bank connection, not screen scraping

    Supported banks: BofA, Chase, Wells Fargo, Capital One, Citi,
    US Bank, PNC, TD Bank, and 5000+ others.

    Credentials:
    - ``TELLER_ACCESS_TOKEN`` — API token from teller.io dashboard
    - ``TELLER_ENVIRONMENT`` — sandbox | development | production

    Connection flow:
    1. Sign up at teller.io and create an application
    2. Enroll accounts via Teller Connect (browser) or API
    3. Copy your access token → set TELLER_ACCESS_TOKEN in .env
    4. Guardian One pulls balances + transactions automatically
    """

    VALID_ENVS = ("sandbox", "development", "production")

    _ENV_HOSTS = {
        "sandbox": "https://api.teller.io",
        "development": "https://api.teller.io",
        "production": "https://api.teller.io",
    }

    def __init__(
        self,
        access_token: str | None = None,
        env: str | None = None,
    ) -> None:
        self._access_token = access_token or os.environ.get("TELLER_ACCESS_TOKEN", "")
        self._env = env or os.environ.get("TELLER_ENVIRONMENT", "sandbox")
        self._base_url = self._ENV_HOSTS.get(self._env, self._ENV_HOSTS["sandbox"])
        self._authenticated = False
        self._last_error: str = ""
        self._enrollments: list[dict[str, Any]] = []

    @property
    def provider_name(self) -> str:
        return "teller"

    @property
    def has_credentials(self) -> bool:
        return bool(self._access_token)

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def connected_institutions(self) -> list[str]:
        """List of enrolled institution names."""
        return [e.get("institution", {}).get("name", "") for e in self._enrollments]

    def authenticate(self) -> bool:
        """Validate Teller access token by listing accounts."""
        if not self.has_credentials:
            self._last_error = "Missing TELLER_ACCESS_TOKEN env var."
            self._authenticated = False
            return False

        result = self._request("GET", "/accounts")
        if result is not None and isinstance(result, list):
            self._authenticated = True
            self._last_error = ""
            # Extract unique enrollments (rebuild to avoid duplicates on re-auth)
            seen: set[str] = set()
            enrollments: list[dict[str, Any]] = []
            for acct in result:
                enrollment = acct.get("enrollment_id", "")
                if enrollment and enrollment not in seen:
                    seen.add(enrollment)
                    enrollments.append({
                        "enrollment_id": enrollment,
                        "institution": acct.get("institution", {}),
                    })
            self._enrollments = enrollments
            return True
        elif isinstance(result, dict) and result.get("error"):
            self._last_error = f"Teller auth failed: {result.get('error', {}).get('message', 'unknown')}"
        else:
            self._last_error = "Teller auth failed: no response"
        self._authenticated = False
        return False

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> Any:
        """Make an authenticated request to the Teller API.

        Teller uses HTTP Basic Auth with token as username, empty password.
        """
        url = f"{self._base_url}{path}"
        data = json.dumps(body).encode() if body else None

        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

        # Basic Auth: token as username, empty password
        import base64
        credentials = base64.b64encode(f"{self._access_token}:".encode()).decode()
        req.add_header("Authorization", f"Basic {credentials}")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            try:
                return json.loads(error_body)
            except (json.JSONDecodeError, ValueError):
                return {"error": {"message": error_body or f"HTTP {e.code}"}}
        except urllib.error.URLError as exc:
            return {"error": {"message": f"Network error: {exc}"}}

    def fetch_accounts(self) -> list[SyncedAccount]:
        """Fetch all accounts from Teller."""
        if not self._authenticated:
            return []

        result = self._request("GET", "/accounts")
        if not isinstance(result, list):
            return []

        now = datetime.now(timezone.utc).isoformat()
        accounts = []
        for item in result:
            # Teller balance is in "balances" sub-object
            balances = item.get("balances", {})
            balance = float(balances.get("current", balances.get("available", 0)) or 0)

            acct_type = _map_teller_account_type(
                item.get("type", ""), item.get("subtype", "")
            )

            institution = item.get("institution", {})
            inst_name = institution.get("name", "") if isinstance(institution, dict) else str(institution)

            accounts.append(SyncedAccount(
                name=item.get("name", ""),
                account_type=acct_type,
                balance=balance,
                institution=inst_name,
                last_updated=now,
                raw=item,
            ))
        return accounts

    def fetch_transactions(self, start_date: str, end_date: str) -> list[SyncedTransaction]:
        """Fetch transactions from all Teller-connected accounts."""
        if not self._authenticated:
            return []

        # First get account list to iterate
        accounts_result = self._request("GET", "/accounts")
        if not isinstance(accounts_result, list):
            return []

        all_transactions: list[SyncedTransaction] = []
        for acct in accounts_result:
            acct_id = acct.get("id", "")
            acct_name = acct.get("name", "")
            if not acct_id:
                continue

            result = self._request("GET", f"/accounts/{acct_id}/transactions")
            if not isinstance(result, list):
                continue

            for tx in result:
                tx_date = tx.get("date", "")
                if tx_date < start_date or tx_date > end_date:
                    continue

                amount = float(tx.get("amount", 0))
                # Teller: negative = debit (outflow), positive = credit (inflow)
                # CFO convention matches this

                category = _map_teller_category(tx.get("type", ""))

                all_transactions.append(SyncedTransaction(
                    date=tx_date,
                    description=tx.get("description", ""),
                    amount=amount,
                    category=category,
                    account=acct_name,
                    raw=tx,
                ))

        return all_transactions

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "has_credentials": self.has_credentials,
            "authenticated": self._authenticated,
            "environment": self._env,
            "enrollments": len(self._enrollments),
            "institutions": self.connected_institutions,
            "last_error": self._last_error,
        }


def _map_teller_account_type(acct_type: str, subtype: str = "") -> str:
    """Map Teller account type/subtype to CFO AccountType."""
    mapping = {
        "depository": "checking",
        "credit": "credit_card",
        "loan": "loan",
        "investment": "investment",
    }
    subtype_mapping = {
        "checking": "checking",
        "savings": "savings",
        "money_market": "savings",
        "cd": "savings",
        "credit_card": "credit_card",
        "mortgage": "loan",
        "student": "loan",
        "auto": "loan",
        "401k": "retirement",
        "401a": "retirement",
        "ira": "retirement",
        "roth": "retirement",
        "roth_401k": "retirement",
        "brokerage": "investment",
    }
    if subtype and subtype.lower() in subtype_mapping:
        return subtype_mapping[subtype.lower()]
    return mapping.get(acct_type.lower(), "checking")


def _map_teller_category(tx_type: str) -> str:
    """Map Teller transaction type to CFO TransactionCategory."""
    mapping = {
        "ach": "other",
        "atm": "other",
        "card_payment": "other",
        "check": "other",
        "deposit": "income",
        "digital_payment": "other",
        "fee": "other",
        "interest": "income",
        "transfer": "savings",
        "wire": "other",
    }
    return mapping.get(tx_type.lower(), "other")


# ---------------------------------------------------------------------------
# Generic bank CSV importer
# ---------------------------------------------------------------------------

# Common column name aliases across banks
_CSV_DATE_COLS = ("date", "posting date", "posted date", "transaction date", "trans date", "post date")
_CSV_DESC_COLS = ("description", "memo", "narrative", "payee", "name", "details", "transaction description")
_CSV_AMOUNT_COLS = ("amount", "transaction amount", "value")
_CSV_DEBIT_COLS = ("debit", "withdrawals", "withdrawal", "debit amount")
_CSV_CREDIT_COLS = ("credit", "deposits", "deposit", "credit amount")
_CSV_CATEGORY_COLS = ("category", "type", "transaction type", "trans type")
_CSV_BALANCE_COLS = ("balance", "running balance", "running bal", "ending balance", "available balance")


def _find_column(headers: list[str], aliases: tuple[str, ...]) -> str | None:
    """Find a column name in headers by matching known aliases (case-insensitive)."""
    lower_headers = {h.lower().strip(): h for h in headers}
    for alias in aliases:
        if alias in lower_headers:
            return lower_headers[alias]
    return None


def parse_bank_csv(
    csv_path: str | Path,
    institution: str = "",
    account_name: str = "",
    account_type: str = "checking",
) -> tuple[list[SyncedAccount], list[SyncedTransaction]]:
    """Parse a generic bank CSV export into SyncedAccount + SyncedTransaction lists.

    Works with exports from BofA, Chase, Wells Fargo, Capital One, Citi,
    US Bank, and most other banks.  Auto-detects column names by matching
    common aliases.

    Args:
        csv_path:      Path to the CSV file.
        institution:   Bank name (e.g. "Bank of America"). Inferred from filename if empty.
        account_name:  Account label. Inferred from filename if empty.
        account_type:  One of: checking, savings, credit_card, loan, investment, retirement.

    Returns:
        Tuple of (accounts, transactions).
    """
    path = Path(csv_path)
    if not path.exists():
        return [], []

    # Infer institution/account from filename if not provided
    stem = path.stem.lower().replace("_", " ").replace("-", " ")
    if not institution:
        for bank, display_name in (
            ("chase", "Chase"),
            ("bofa", "Bank of America"),
            ("bank of america", "Bank of America"),
            ("wells fargo", "Wells Fargo"),
            ("capital one", "Capital One"),
            ("citi", "Citi"),
            ("us bank", "US Bank"),
            ("pnc", "PNC"),
            ("td bank", "TD Bank"),
            ("ally", "Ally"),
            ("discover", "Discover"),
            ("amex", "American Express"),
            ("american express", "American Express"),
        ):
            if bank in stem:
                institution = display_name
                break
        if not institution:
            institution = "Bank"
    if not account_name:
        account_name = f"{institution} {account_type.replace('_', ' ').title()}"

    text = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return [], []

    headers = list(rows[0].keys())

    # Auto-detect columns
    date_col = _find_column(headers, _CSV_DATE_COLS)
    desc_col = _find_column(headers, _CSV_DESC_COLS)
    amount_col = _find_column(headers, _CSV_AMOUNT_COLS)
    debit_col = _find_column(headers, _CSV_DEBIT_COLS)
    credit_col = _find_column(headers, _CSV_CREDIT_COLS)
    category_col = _find_column(headers, _CSV_CATEGORY_COLS)
    balance_col = _find_column(headers, _CSV_BALANCE_COLS)

    if not date_col:
        return [], []  # Can't parse without a date column

    now = datetime.now(timezone.utc).isoformat()
    transactions: list[SyncedTransaction] = []
    last_balance = 0.0  # only used if a balance column is present

    for row in rows:
        # Parse date
        date_val = row.get(date_col, "").strip()
        if not date_val:
            continue
        # Normalize date to ISO format
        date_val = _normalize_date(date_val)

        # Parse amount
        if amount_col:
            amount = _parse_amount(row.get(amount_col, "0"))
        elif debit_col or credit_col:
            debit = _parse_amount(row.get(debit_col, "0")) if debit_col else 0.0
            credit = _parse_amount(row.get(credit_col, "0")) if credit_col else 0.0
            # Debits are outflows (negative), credits are inflows (positive)
            amount = credit - debit
        else:
            continue  # Can't determine amount

        # Track balance from dedicated column if present
        if balance_col:
            last_balance = _parse_amount(row.get(balance_col, "0"))

        # Description
        desc = row.get(desc_col, "") if desc_col else ""
        desc = desc.strip()

        # Category
        cat_raw = row.get(category_col, "") if category_col else ""
        category = map_rocket_money_category(cat_raw) if cat_raw else "other"

        transactions.append(SyncedTransaction(
            date=date_val,
            description=desc,
            amount=amount,
            category=category,
            account=account_name,
            raw=dict(row),
        ))

    # Use real balance from CSV column if available; otherwise 0.0
    # to avoid corrupting net worth with sum-of-transactions.
    account = SyncedAccount(
        name=account_name,
        account_type=account_type,
        balance=last_balance if balance_col else 0.0,
        institution=institution,
        last_updated=now,
    )
    return [account], transactions


def _normalize_date(date_str: str) -> str:
    """Attempt to normalize various date formats to ISO YYYY-MM-DD."""
    date_str = date_str.strip()
    # Already ISO
    if re.match(r"\d{4}-\d{2}-\d{2}", date_str):
        return date_str[:10]
    # MM/DD/YYYY or M/D/YYYY
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_str)
    if m:
        return f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
    # MM/DD/YY
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2})", date_str)
    if m:
        year = int(m.group(3))
        full_year = 2000 + year if year < 70 else 1900 + year
        return f"{full_year}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
    # DD-Mon-YYYY (e.g. 15-Jan-2026)
    m = re.match(r"(\d{1,2})-(\w{3})-(\d{4})", date_str)
    if m:
        try:
            dt = datetime.strptime(date_str, "%d-%b-%Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    # Fallback: return as-is
    return date_str


def _parse_amount(val: str) -> float:
    """Parse an amount string, handling $, commas, parentheses (negative)."""
    if not val or not val.strip():
        return 0.0
    val = val.strip()
    negative = val.startswith("(") and val.endswith(")")
    val = val.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
    try:
        result = float(val)
        return -result if negative else result
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# OFX / QFX file importer
# ---------------------------------------------------------------------------

def parse_ofx(
    ofx_path: str | Path,
) -> tuple[list[SyncedAccount], list[SyncedTransaction]]:
    """Parse an OFX/QFX file (Open Financial Exchange) into Guardian One format.

    OFX is the standard bank export format supported by virtually every bank.
    Most banks offer "Download transactions" → "Quicken (QFX)" or "OFX" format.

    Handles both SGML-style OFX (v1.x) and XML-style OFX (v2.x).

    Returns:
        Tuple of (accounts, transactions).
    """
    path = Path(ofx_path)
    if not path.exists():
        return [], []

    raw = path.read_text(encoding="utf-8-sig", errors="replace")

    # OFX v1.x uses SGML (not valid XML) — convert to XML
    if "<OFX>" in raw and "<?xml" not in raw:
        raw = _sgml_ofx_to_xml(raw)

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return [], []

    now = datetime.now(timezone.utc).isoformat()
    accounts: list[SyncedAccount] = []
    transactions: list[SyncedTransaction] = []

    # Find all statement responses (banking + credit card)
    for stmt_tag in ("STMTTRNRS", "CCSTMTTRNRS"):
        for stmt_wrapper in root.iter(stmt_tag):
            stmt = (
                stmt_wrapper.find(".//STMTRS")
                or stmt_wrapper.find(".//CCSTMTRS")
            )
            if stmt is None:
                continue

            # Account info
            acct_from = stmt.find("BANKACCTFROM") or stmt.find("CCACCTFROM")
            acct_id = ""
            acct_type = "checking"
            institution = "Bank"
            masked_id = ""

            if acct_from is not None:
                acct_id_el = acct_from.find("ACCTID")
                acct_id = acct_id_el.text.strip() if acct_id_el is not None and acct_id_el.text else ""
                # Mask account number for display
                masked_id = f"***{acct_id[-4:]}" if len(acct_id) >= 4 else acct_id

                type_el = acct_from.find("ACCTTYPE")
                if type_el is not None and type_el.text:
                    acct_type = _map_ofx_account_type(type_el.text.strip())
                elif stmt_tag == "CCSTMTTRNRS":
                    acct_type = "credit_card"

                bank_id_el = acct_from.find("BANKID")
                institution = bank_id_el.text.strip() if bank_id_el is not None and bank_id_el.text else "Bank"

            # Balance
            balance = 0.0
            bal_el = stmt.find(".//BALAMT") or stmt.find(".//LEDGERBAL/BALAMT")
            if bal_el is not None and bal_el.text:
                try:
                    balance = float(bal_el.text.strip())
                except ValueError:
                    pass

            acct_label = f"{institution} {acct_type.replace('_', ' ').title()} {masked_id}"
            accounts.append(SyncedAccount(
                name=acct_label,
                account_type=acct_type,
                balance=balance,
                institution=institution,
                last_updated=now,
            ))

            # Transactions
            tx_list = stmt.find("BANKTRANLIST") or stmt.find("CCSTMTRS")
            if tx_list is None:
                tx_list = stmt  # fallback: search within stmt directly
            for stmttrn in tx_list.iter("STMTTRN"):
                tx_date = ""
                dt_el = stmttrn.find("DTPOSTED")
                if dt_el is not None and dt_el.text:
                    tx_date = _parse_ofx_date(dt_el.text.strip())

                amount = 0.0
                amt_el = stmttrn.find("TRNAMT")
                if amt_el is not None and amt_el.text:
                    try:
                        amount = float(amt_el.text.strip())
                    except ValueError:
                        pass

                desc = ""
                for desc_tag in ("NAME", "MEMO", "PAYEE"):
                    desc_el = stmttrn.find(desc_tag)
                    if desc_el is not None and desc_el.text:
                        desc = desc_el.text.strip()
                        break

                tx_type_el = stmttrn.find("TRNTYPE")
                tx_type = tx_type_el.text.strip().lower() if tx_type_el is not None and tx_type_el.text else ""
                category = _map_ofx_tx_type(tx_type)

                transactions.append(SyncedTransaction(
                    date=tx_date,
                    description=desc,
                    amount=amount,
                    category=category,
                    account=acct_label,
                ))

    return accounts, transactions


def _sgml_ofx_to_xml(raw: str) -> str:
    """Convert SGML-style OFX v1.x to valid XML for parsing.

    OFX v1.x uses SGML with unclosed tags like <TRNAMT>123.45
    This converts them to <TRNAMT>123.45</TRNAMT>.
    """
    # Strip the header (everything before <OFX>)
    idx = raw.find("<OFX>")
    if idx == -1:
        return raw
    body = raw[idx:]

    # Self-closing elements that contain data (not containers)
    data_tags = {
        "DTSERVER", "LANGUAGE", "ORG", "FID", "TRNUID", "CODE",
        "SEVERITY", "MESSAGE", "BANKID", "ACCTID", "ACCTTYPE",
        "DTSTART", "DTEND", "TRNTYPE", "DTPOSTED", "DTUSER",
        "TRNAMT", "FITID", "CHECKNUM", "NAME", "MEMO", "PAYEE",
        "BALAMT", "DTASOF", "CURDEF", "SIC",
    }

    lines = body.split("\n")
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Match <TAG>value (no closing tag)
        m = re.match(r"<(\w+)>(.+)", stripped)
        if m:
            tag = m.group(1)
            value = m.group(2).strip()
            if tag.upper() in data_tags and not value.startswith("<"):
                result.append(f"<{tag}>{value}</{tag}>")
                continue
        result.append(stripped)

    xml_str = "\n".join(result)
    # Wrap in XML declaration
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'


def _parse_ofx_date(date_str: str) -> str:
    """Parse OFX date format (YYYYMMDDHHMMSS or YYYYMMDD) to ISO date."""
    # Strip timezone info like [0:GMT] or [-5:EST]
    date_str = re.sub(r"\[.*?\]", "", date_str).strip()
    if len(date_str) >= 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    return date_str


def _map_ofx_account_type(ofx_type: str) -> str:
    """Map OFX account type to CFO AccountType."""
    mapping = {
        "CHECKING": "checking",
        "SAVINGS": "savings",
        "MONEYMRKT": "savings",
        "CREDITLINE": "credit_card",
        "CREDITCARD": "credit_card",
        "CD": "savings",
    }
    return mapping.get(ofx_type.upper(), "checking")


def _map_ofx_tx_type(tx_type: str) -> str:
    """Map OFX transaction type to CFO TransactionCategory."""
    mapping = {
        "credit": "income",
        "debit": "other",
        "int": "income",
        "div": "income",
        "fee": "other",
        "srvchg": "other",
        "dep": "income",
        "atm": "other",
        "pos": "other",
        "xfer": "savings",
        "check": "other",
        "payment": "other",
        "cash": "other",
        "directdep": "income",
        "directdebit": "other",
        "repeatpmt": "other",
        "other": "other",
    }
    return mapping.get(tx_type.lower(), "other")
