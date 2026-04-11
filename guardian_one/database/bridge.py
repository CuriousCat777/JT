"""Bridge between Guardian One's existing systems and the database.

Provides hooks to automatically persist audit entries and financial
sync results into the SQLite database alongside the existing JSONL
and JSON stores.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from guardian_one.database.manager import GuardianDatabase
from guardian_one.database.models import (
    CrawlRecord,
    FinancialAccount,
    FinancialTransaction,
    SystemCode,
    SystemLog,
)


def _s(d: dict[str, Any], key: str, default: str = "") -> str:
    """Get a string field, coercing ``None`` → default.

    ``dict.get(key, default)`` returns ``None`` when the key is present
    but holds a JSON ``null``, which then violates ``NOT NULL``
    constraints downstream.  This helper treats ``None`` the same as a
    missing key.
    """
    value = d.get(key, default)
    return default if value is None else value


def _f(d: dict[str, Any], key: str, default: float = 0.0) -> float:
    """Get a float field, coercing ``None`` → default."""
    value = d.get(key, default)
    return default if value is None else value


class DatabaseBridge:
    """Connects existing Guardian One subsystems to the database.

    Usage:
        bridge = DatabaseBridge()
        bridge.log_audit_entry(agent="cfo", action="sync", ...)
        bridge.sync_accounts(accounts_list)
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db = GuardianDatabase(db_path)

    def log_audit_entry(
        self,
        agent: str,
        action: str,
        severity: str = "info",
        details: dict[str, Any] | None = None,
        component: str = "agent",
        source: str = "audit_bridge",
    ) -> int:
        """Persist an audit entry to the database."""
        return self.db.insert_log(SystemLog(
            agent=agent,
            action=action,
            severity=severity,
            component=component,
            message=action,
            details=json.dumps(details or {}),
            source=source,
        ))

    def sync_accounts(self, accounts: list[dict[str, Any]], source: str = "sync") -> int:
        """Upsert a batch of account snapshots from financial sync.

        Fields are normalized via ``_s``/``_f`` so that JSON ``null``
        values from upstream providers don't propagate into the
        ``NOT NULL`` columns and abort the whole sync.
        """
        count = 0
        for acct in accounts:
            self.db.upsert_account(FinancialAccount(
                name=_s(acct, "name"),
                account_type=_s(acct, "account_type"),
                balance=_f(acct, "balance"),
                institution=_s(acct, "institution"),
                source=source,
                last_synced=_s(acct, "last_synced", _s(acct, "last_updated")),
            ))
            count += 1
        return count

    def sync_transactions(
        self, transactions: list[dict[str, Any]], source: str = "sync"
    ) -> int:
        """Insert a batch of transactions with deduplication.

        Fields are normalized via ``_s``/``_f`` so that JSON ``null``
        values from upstream providers don't propagate as Python
        ``None`` into string/float columns.
        """
        txns = [
            FinancialTransaction(
                date=_s(t, "date"),
                description=_s(t, "description"),
                amount=_f(t, "amount"),
                category=_s(t, "category"),
                account=_s(t, "account"),
                institution=_s(t, "institution"),
                transaction_type=_s(t, "transaction_type"),
                source=source,
                reference_id=_s(t, "reference_id", _s(t, "id")),
                notes=_s(t, "notes"),
            )
            for t in transactions
        ]
        return self.db.insert_transactions_batch(txns)

    def store_crawl(
        self,
        bot_name: str,
        target_url: str,
        status_code: int = 200,
        content_type: str = "",
        title: str = "",
        content_summary: str = "",
        raw_data: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        crawl_duration_ms: int = 0,
    ) -> int:
        """Store a single crawl bot result."""
        return self.db.insert_crawl(CrawlRecord(
            bot_name=bot_name,
            target_url=target_url,
            status_code=status_code,
            content_type=content_type,
            title=title,
            content_summary=content_summary,
            raw_data=json.dumps(raw_data or {}),
            tags=",".join(tags or []),
            crawl_duration_ms=crawl_duration_ms,
        ))

    def store_code(
        self,
        code_id: str,
        code_type: str = "",
        description: str = "",
        status: str = "active",
        expires_at: str | None = None,
        associated_entity: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Store a system code entry."""
        return self.db.insert_code(SystemCode(
            code_id=code_id,
            code_type=code_type,
            description=description,
            status=status,
            expires_at=expires_at,
            associated_entity=associated_entity,
            metadata=json.dumps(metadata or {}),
        ))
