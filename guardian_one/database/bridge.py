"""Bridge between Guardian One's existing systems and the database.

Provides hooks to automatically persist audit entries and financial
sync results into the SQLite database alongside the existing JSONL
and JSON stores.
"""

from __future__ import annotations

import json
import re
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
    """Get a string field, coercing ``None`` → default and always
    returning ``str``.

    Two concerns are handled here:

    1. ``dict.get(key, default)`` returns ``None`` when the key is
       present but holds a JSON ``null``, which then violates
       ``NOT NULL`` constraints downstream.  This helper treats
       ``None`` the same as a missing key.

    2. Upstream providers sometimes serialize string-like fields as
       numbers — most importantly transaction IDs such as
       ``"reference_id": 123``.  If the int is stored as-is in the
       TEXT column, SQLite keeps it as an int, and on the next sync
       ``insert_transactions_batch``'s dedup pre-check compares
       ``'123'`` (stored) against ``123`` (incoming), fails to spot
       the duplicate, then hits the UNIQUE constraint and blows up.
       Casting to ``str`` here makes re-sync idempotent.
    """
    value = d.get(key, default)
    if value is None:
        return default
    return value if isinstance(value, str) else str(value)


_NUMERIC_EXTRACT = re.compile(r"-?\d+(?:\.\d+)?")


def _first_nonempty_id(d: dict[str, Any], *keys: str) -> str:
    """Return the first non-empty id-like field, coerced to ``str``.

    ``_s`` treats an empty string as a valid value and does not fall
    through to a secondary default, so ``_s(t, "reference_id", _s(t,
    "id"))`` fails to recover when an upstream payload sets
    ``reference_id: ""`` alongside a real ``id``. The empty
    reference_id then bypasses dedup entirely (the partial unique
    index only covers ``reference_id != ''``), so re-syncing the
    same payload would produce duplicate rows.

    This helper walks the provided keys in order and returns the
    first value that is both present and non-empty after string
    coercion. ``None`` / missing / empty-string are all treated as
    "missing" for dedup purposes.
    """
    for key in keys:
        value = d.get(key)
        if value is None:
            continue
        text = value if isinstance(value, str) else str(value)
        if text:
            return text
    return ""


def _f(d: dict[str, Any], key: str, default: float = 0.0) -> float:
    """Get a float field, parsing strings and coercing bad values → default.

    Upstream financial providers emit amounts in all kinds of shapes:

    * plain numbers (``-20.0``)
    * plain numeric strings (``"-20.00"``)
    * thousand-separated strings (``"1,238.93"``, ``"-1,234,567.89"``)
    * currency-prefixed strings (``"$500.00"``, ``"-$99.99"``)
    * currency-suffixed strings (``"-20.00 USD"``, ``"1,238.93 USD"``)
    * garbage (``"N/A"``, ``None``)

    Silently returning 0.0 for ``"1,238.93"`` or flipping the sign
    on ``"-$99.99"`` would corrupt balances and spending totals.
    The parser:

      1. returns ``default`` for ``None`` / missing keys,
      2. fast-paths ``int``/``float``,
      3. strips thousand-separator commas and tries ``float(value)``,
      4. regex-extracts the first signed numeric token as a last
         resort. If the prefix before the matched token contains a
         bare ``-`` (as in ``"-$99.99"`` where the ``$`` separates
         the sign from the digits), the sign is re-applied so
         debits aren't silently flipped into credits,
      5. falls back to ``default`` only when no numeric token is
         present.
    """
    value = d.get(key, default)
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    # Strip thousand separators before the first float() attempt so
    # ``"1,238.93"`` → ``1238.93`` directly.
    cleaned = value.replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        pass
    match = _NUMERIC_EXTRACT.search(cleaned)
    if match:
        try:
            parsed = float(match.group())
        except ValueError:
            return default
        # Regex-matched number may or may not include its sign
        # depending on whether a currency symbol sat between the
        # ``-`` and the digits. If the prefix before the match has
        # a bare ``-`` and the match itself is positive, apply the
        # sign so ``"-$99.99"`` stays negative.
        if parsed >= 0 and "-" in cleaned[: match.start()]:
            parsed = -parsed
        return parsed
    return default


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

        Non-dict entries in the input list (e.g. a stray ``null`` in
        the provider's JSON array) are skipped so one bad element
        does not raise ``AttributeError`` and abort the entire batch.

        **Note:** this method only *adds* or *updates* accounts; it
        never removes rows that have disappeared from the upstream
        snapshot. For a full-snapshot replace (needed when an
        account is closed or disconnected and must drop out of
        ``financial_accounts``), use ``replace_accounts`` instead.
        """
        count = 0
        for acct in accounts:
            if not isinstance(acct, dict):
                continue
            self.db.upsert_account(self._build_account(acct, source))
            count += 1
        return count

    def replace_accounts(
        self, accounts: list[dict[str, Any]], source: str = "sync"
    ) -> int:
        """Replace all account rows tagged with ``source`` in one
        transaction. Use this when mirroring a full snapshot from a
        provider — a ``sync_accounts`` upsert loop would leave stale
        rows behind whenever an account is closed or disconnected
        upstream, which corrupts ``net_worth()`` and ``--db-accounts``.

        Non-dict entries are filtered out; the DELETE still runs so
        the slice converges to the current snapshot.
        """
        accts = [
            self._build_account(a, source)
            for a in accounts
            if isinstance(a, dict)
        ]
        return self.db.replace_accounts_for_source(source, accts)

    def _build_account(
        self, acct: dict[str, Any], source: str
    ) -> FinancialAccount:
        """Shared payload normalization for sync/replace account paths."""
        return FinancialAccount(
            name=_s(acct, "name"),
            account_type=_s(acct, "account_type"),
            balance=_f(acct, "balance"),
            institution=_s(acct, "institution"),
            source=source,
            last_synced=_s(acct, "last_synced", _s(acct, "last_updated")),
        )

    def sync_transactions(
        self, transactions: list[dict[str, Any]], source: str = "sync"
    ) -> int:
        """Insert a batch of transactions with deduplication.

        Fields are normalized via ``_s``/``_f`` so that JSON ``null``
        values from upstream providers don't propagate as Python
        ``None`` into string/float columns.

        Non-dict entries in the input list are skipped so one bad
        element does not raise ``AttributeError`` and abort the
        whole sync.
        """
        txns = self._build_txn_objects(transactions, source)
        return self.db.insert_transactions_batch(txns)

    def replace_transactions(
        self, transactions: list[dict[str, Any]], source: str = "sync"
    ) -> int:
        """Replace all rows tagged with ``source`` in one transaction.

        Use this when mirroring a mutable in-memory ledger where
        rows may be reordered or removed between calls — e.g.
        CFO's ``save_ledger``. ``sync_transactions``' dedup pre-
        check assumes stable reference_ids across calls, which
        falls apart for freshly-synthesized composite keys whose
        position in the list can drift.
        """
        txns = self._build_txn_objects(transactions, source)
        return self.db.replace_transactions_for_source(source, txns)

    def _build_txn_objects(
        self, transactions: list[dict[str, Any]], source: str
    ) -> list[FinancialTransaction]:
        """Shared payload normalization for sync/replace paths."""
        return [
            FinancialTransaction(
                date=_s(t, "date"),
                description=_s(t, "description"),
                amount=_f(t, "amount"),
                category=_s(t, "category"),
                account=_s(t, "account"),
                institution=_s(t, "institution"),
                transaction_type=_s(t, "transaction_type"),
                source=source,
                # ``_first_nonempty_id`` treats "" the same as a
                # missing key so a payload like
                # ``{"reference_id": "", "id": "abc"}`` still gets
                # a stable dedup key instead of silently becoming
                # "" (which would bypass the UNIQUE index and
                # duplicate on re-sync).
                reference_id=_first_nonempty_id(t, "reference_id", "id"),
                notes=_s(t, "notes"),
            )
            for t in transactions
            if isinstance(t, dict)
        ]

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
