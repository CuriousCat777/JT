"""Data models for the Guardian One database.

These dataclasses mirror the SQLite tables and provide a clean Python
interface for inserting, querying, and serializing records.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# System Logs — audit trails, agent activity, errors
# ---------------------------------------------------------------------------

@dataclass
class SystemLog:
    """A single log entry from any Guardian One component."""
    timestamp: str = field(default_factory=_now_iso)
    agent: str = ""
    action: str = ""
    severity: str = "info"          # info | warning | error | critical
    component: str = ""             # core, agent, integration, homelink
    message: str = ""
    details: str = ""               # JSON-encoded extra data
    source: str = ""                # where the log originated (file, webhook, etc.)
    id: int | None = None           # set by DB on insert

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("id", None)
        return d


# ---------------------------------------------------------------------------
# System Codes — configuration codes, access tokens, device codes, etc.
# ---------------------------------------------------------------------------

@dataclass
class SystemCode:
    """A trackable code entry (device codes, config codes, activation keys)."""
    code_id: str = ""               # unique identifier / code value
    code_type: str = ""             # device | config | access | activation | alert
    description: str = ""
    status: str = "active"          # active | used | expired | revoked
    issued_at: str = field(default_factory=_now_iso)
    expires_at: str | None = None
    associated_entity: str = ""     # device name, user, agent, etc.
    metadata: str = ""              # JSON-encoded extra data
    id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("id", None)
        return d


# ---------------------------------------------------------------------------
# Crawl Records — data from query crawl bots
# ---------------------------------------------------------------------------

@dataclass
class CrawlRecord:
    """A single crawl result from query bots."""
    crawl_timestamp: str = field(default_factory=_now_iso)
    bot_name: str = ""              # which bot performed the crawl
    target_url: str = ""
    status_code: int = 0
    content_type: str = ""
    title: str = ""
    content_summary: str = ""       # extracted text or summary
    raw_data: str = ""              # JSON-encoded full response
    tags: str = ""                  # comma-separated tags
    crawl_duration_ms: int = 0
    id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("id", None)
        return d


# ---------------------------------------------------------------------------
# Financial Transactions — Rocket Money, Plaid, Empower
# ---------------------------------------------------------------------------

@dataclass
class FinancialTransaction:
    """A financial transaction record."""
    date: str = ""
    description: str = ""
    amount: float = 0.0
    category: str = ""
    account: str = ""
    institution: str = ""
    transaction_type: str = ""      # debit | credit | transfer
    source: str = ""                # rocket_money | plaid | empower | manual
    reference_id: str = ""          # external transaction ID for dedup
    notes: str = ""
    recorded_at: str = field(default_factory=_now_iso)
    id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("id", None)
        return d


# ---------------------------------------------------------------------------
# Financial Accounts — account snapshots
# ---------------------------------------------------------------------------

@dataclass
class FinancialAccount:
    """A snapshot of a financial account at a point in time."""
    name: str = ""
    account_type: str = ""          # checking | savings | credit_card | retirement
    balance: float = 0.0
    institution: str = ""
    source: str = ""                # rocket_money | plaid | empower
    last_synced: str = field(default_factory=_now_iso)
    metadata: str = ""              # JSON-encoded extra data
    id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("id", None)
        return d
