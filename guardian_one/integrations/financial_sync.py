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
