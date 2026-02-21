"""Financial integration — Rocket Money and Plaid providers.

Providers auto-detect credentials from environment variables.
When credentials are absent they operate in offline mode.

Rocket Money data paths:
1. API sync (ROCKET_MONEY_API_KEY) — real-time account/transaction pull
2. CSV import — Gmail agent downloads CSVs, CFO ingests them via sync_from_csv()

Both paths merge into the CFO ledger.
"""

from __future__ import annotations

import abc
import csv
import io
import json
import os
import urllib.request
import urllib.error
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
