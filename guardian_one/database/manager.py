"""Guardian One Database Manager — SQLite-backed repository.

Provides a single unified database for:
- System logs (audit trails, agent activity, errors)
- System codes (device codes, config keys, activation tokens)
- Crawl records (query bot results)
- Financial transactions (Rocket Money, Plaid, Empower)
- Financial accounts (balance snapshots)

Thread-safe via SQLite WAL mode and connection-per-call pattern.
Data sovereignty: everything stays local, encrypted-at-rest via OS/disk
encryption, queryable with SQL.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from guardian_one.database.models import (
    CrawlRecord,
    FinancialAccount,
    FinancialTransaction,
    SystemCode,
    SystemLog,
)


_SCHEMA_VERSION = 1


def _coerce_str(d: dict[str, Any], key: str, default: str = "") -> str:
    """Get a string field from a dict, coercing ``None`` → default and
    always returning ``str``.

    - ``None`` values are treated like missing keys (prevents NOT NULL
      violations when a JSON ``null`` is present).
    - Non-string values are cast to ``str`` so an integer reference ID
      (``{"reference_id": 123}``) round-trips consistently through the
      TEXT column instead of being stored as an int and breaking
      later dedup pre-checks against the stored ``'123'``.
    """
    value = d.get(key, default)
    if value is None:
        return default
    return value if isinstance(value, str) else str(value)


def _coerce_float(d: dict[str, Any], key: str, default: float = 0.0) -> float:
    """Get a float field from a dict, parsing strings and falling back.

    Imported ledger files sometimes contain amounts as strings (e.g.
    ``"1238.93"`` or even ``"1,238.93 USD"``).  Passing those through
    unchanged corrupts REAL columns via SQLite's type affinity, which
    then breaks numeric comparisons (``amount < 0``) and format
    specifiers (``:,.2f``). Parse to ``float`` where possible; fall
    back to the default when the value is missing, ``None``, or not
    convertible.
    """
    value = d.get(key, default)
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_dict(d: dict[str, Any], key: str) -> dict[str, Any]:
    """Get a dict field, coercing missing / ``None`` → empty dict."""
    value = d.get(key)
    return value if isinstance(value, dict) else {}

_SCHEMA_SQL = """
-- System logs table
CREATE TABLE IF NOT EXISTS system_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    agent           TEXT NOT NULL DEFAULT '',
    action          TEXT NOT NULL DEFAULT '',
    severity        TEXT NOT NULL DEFAULT 'info',
    component       TEXT NOT NULL DEFAULT '',
    message         TEXT NOT NULL DEFAULT '',
    details         TEXT NOT NULL DEFAULT '',
    source          TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON system_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_logs_agent ON system_logs(agent);
CREATE INDEX IF NOT EXISTS idx_logs_severity ON system_logs(severity);
CREATE INDEX IF NOT EXISTS idx_logs_component ON system_logs(component);

-- System codes table
CREATE TABLE IF NOT EXISTS system_codes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    code_id             TEXT NOT NULL,
    code_type           TEXT NOT NULL DEFAULT '',
    description         TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'active',
    issued_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    expires_at          TEXT,
    associated_entity   TEXT NOT NULL DEFAULT '',
    metadata            TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_codes_code_id ON system_codes(code_id);
CREATE INDEX IF NOT EXISTS idx_codes_type ON system_codes(code_type);
CREATE INDEX IF NOT EXISTS idx_codes_status ON system_codes(status);

-- Crawl records table
CREATE TABLE IF NOT EXISTS crawl_records (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    crawl_timestamp     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    bot_name            TEXT NOT NULL DEFAULT '',
    target_url          TEXT NOT NULL DEFAULT '',
    status_code         INTEGER NOT NULL DEFAULT 0,
    content_type        TEXT NOT NULL DEFAULT '',
    title               TEXT NOT NULL DEFAULT '',
    content_summary     TEXT NOT NULL DEFAULT '',
    raw_data            TEXT NOT NULL DEFAULT '',
    tags                TEXT NOT NULL DEFAULT '',
    crawl_duration_ms   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_crawl_timestamp ON crawl_records(crawl_timestamp);
CREATE INDEX IF NOT EXISTS idx_crawl_bot ON crawl_records(bot_name);
CREATE INDEX IF NOT EXISTS idx_crawl_url ON crawl_records(target_url);

-- Financial transactions table
CREATE TABLE IF NOT EXISTS financial_transactions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL DEFAULT '',
    description         TEXT NOT NULL DEFAULT '',
    amount              REAL NOT NULL DEFAULT 0.0,
    category            TEXT NOT NULL DEFAULT '',
    account             TEXT NOT NULL DEFAULT '',
    institution         TEXT NOT NULL DEFAULT '',
    transaction_type    TEXT NOT NULL DEFAULT '',
    source              TEXT NOT NULL DEFAULT '',
    reference_id        TEXT NOT NULL DEFAULT '',
    notes               TEXT NOT NULL DEFAULT '',
    recorded_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_txn_date ON financial_transactions(date);
CREATE INDEX IF NOT EXISTS idx_txn_category ON financial_transactions(category);
CREATE INDEX IF NOT EXISTS idx_txn_account ON financial_transactions(account);
CREATE INDEX IF NOT EXISTS idx_txn_source ON financial_transactions(source);
CREATE UNIQUE INDEX IF NOT EXISTS idx_txn_ref ON financial_transactions(reference_id)
    WHERE reference_id != '';

-- Financial accounts table
CREATE TABLE IF NOT EXISTS financial_accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL DEFAULT '',
    account_type    TEXT NOT NULL DEFAULT '',
    balance         REAL NOT NULL DEFAULT 0.0,
    institution     TEXT NOT NULL DEFAULT '',
    source          TEXT NOT NULL DEFAULT '',
    last_synced     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    metadata        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_acct_name ON financial_accounts(name);
CREATE INDEX IF NOT EXISTS idx_acct_institution ON financial_accounts(institution);
CREATE INDEX IF NOT EXISTS idx_acct_type ON financial_accounts(account_type);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_meta (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);
"""


class GuardianDatabase:
    """Thread-safe SQLite database manager for Guardian One.

    Usage:
        db = GuardianDatabase(Path("data/guardian.db"))
        db.insert_log(SystemLog(agent="cfo", action="sync", message="Fetched accounts"))
        logs = db.query_logs(agent="cfo", limit=50)
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is not None:
            self._db_path = Path(db_path)
        else:
            # Honor the same GUARDIAN_DATA_DIR used by Docker, compose, and
            # the rest of the codebase so local and containerized runs agree.
            data_dir = Path(os.environ.get("GUARDIAN_DATA_DIR", "data"))
            self._db_path = data_dir / "guardian.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_schema(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(_SCHEMA_SQL)
                conn.execute(
                    "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
                    ("version", str(_SCHEMA_VERSION)),
                )
                conn.commit()
            finally:
                conn.close()

    # =======================================================================
    # System Logs
    # =======================================================================

    def insert_log(self, log: SystemLog) -> int:
        """Insert a system log entry. Returns the row ID."""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """INSERT INTO system_logs
                       (timestamp, agent, action, severity, component, message, details, source)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (log.timestamp, log.agent, log.action, log.severity,
                     log.component, log.message, log.details, log.source),
                )
                conn.commit()
                return cur.lastrowid or 0
            finally:
                conn.close()

    def insert_logs_batch(self, logs: list[SystemLog]) -> int:
        """Bulk-insert system logs in a single transaction.

        Much faster than calling :meth:`insert_log` per row for large
        imports because it uses one connection, one transaction, and a
        single ``executemany`` call.
        """
        if not logs:
            return 0
        with self._lock:
            conn = self._connect()
            try:
                conn.executemany(
                    """INSERT INTO system_logs
                       (timestamp, agent, action, severity, component, message, details, source)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (log.timestamp, log.agent, log.action, log.severity,
                         log.component, log.message, log.details, log.source)
                        for log in logs
                    ],
                )
                conn.commit()
                return len(logs)
            finally:
                conn.close()

    def query_logs(
        self,
        agent: str | None = None,
        severity: str | None = None,
        component: str | None = None,
        since: str | None = None,
        until: str | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SystemLog]:
        """Query system logs with optional filters."""
        clauses: list[str] = []
        params: list[Any] = []
        if agent:
            clauses.append("agent = ?")
            params.append(agent)
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        if component:
            clauses.append("component = ?")
            params.append(component)
        if since:
            clauses.append("timestamp >= ?")
            params.append(since)
        if until:
            clauses.append("timestamp <= ?")
            params.append(until)
        if search:
            clauses.append("(message LIKE ? OR details LIKE ? OR action LIKE ?)")
            params.extend([f"%{search}%"] * 3)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM system_logs {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [SystemLog(**dict(r)) for r in rows]
        finally:
            conn.close()

    def count_logs(self, severity: str | None = None) -> int:
        """Count log entries, optionally filtered by severity."""
        conn = self._connect()
        try:
            if severity:
                row = conn.execute(
                    "SELECT COUNT(*) FROM system_logs WHERE severity = ?", (severity,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM system_logs").fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    # =======================================================================
    # System Codes
    # =======================================================================

    def insert_code(self, code: SystemCode) -> int:
        """Insert a system code. Returns the row ID."""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """INSERT INTO system_codes
                       (code_id, code_type, description, status, issued_at,
                        expires_at, associated_entity, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (code.code_id, code.code_type, code.description, code.status,
                     code.issued_at, code.expires_at, code.associated_entity,
                     code.metadata),
                )
                conn.commit()
                return cur.lastrowid or 0
            finally:
                conn.close()

    def query_codes(
        self,
        code_type: str | None = None,
        status: str | None = None,
        entity: str | None = None,
        limit: int = 100,
    ) -> list[SystemCode]:
        """Query system codes with optional filters."""
        clauses: list[str] = []
        params: list[Any] = []
        if code_type:
            clauses.append("code_type = ?")
            params.append(code_type)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if entity:
            clauses.append("associated_entity = ?")
            params.append(entity)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM system_codes {where} ORDER BY issued_at DESC LIMIT ?"
        params.append(limit)

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [SystemCode(**dict(r)) for r in rows]
        finally:
            conn.close()

    def update_code_status(self, code_id: str, new_status: str) -> bool:
        """Update the status of a system code. Returns True if updated."""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "UPDATE system_codes SET status = ? WHERE code_id = ?",
                    (new_status, code_id),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    # =======================================================================
    # Crawl Records
    # =======================================================================

    def insert_crawl(self, record: CrawlRecord) -> int:
        """Insert a crawl bot record. Returns the row ID."""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """INSERT INTO crawl_records
                       (crawl_timestamp, bot_name, target_url, status_code,
                        content_type, title, content_summary, raw_data,
                        tags, crawl_duration_ms)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (record.crawl_timestamp, record.bot_name, record.target_url,
                     record.status_code, record.content_type, record.title,
                     record.content_summary, record.raw_data, record.tags,
                     record.crawl_duration_ms),
                )
                conn.commit()
                return cur.lastrowid or 0
            finally:
                conn.close()

    def insert_crawls_batch(self, records: list[CrawlRecord]) -> int:
        """Bulk insert crawl records. Returns count inserted."""
        if not records:
            return 0
        with self._lock:
            conn = self._connect()
            try:
                conn.executemany(
                    """INSERT INTO crawl_records
                       (crawl_timestamp, bot_name, target_url, status_code,
                        content_type, title, content_summary, raw_data,
                        tags, crawl_duration_ms)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (r.crawl_timestamp, r.bot_name, r.target_url,
                         r.status_code, r.content_type, r.title,
                         r.content_summary, r.raw_data, r.tags,
                         r.crawl_duration_ms)
                        for r in records
                    ],
                )
                conn.commit()
                return len(records)
            finally:
                conn.close()

    def query_crawls(
        self,
        bot_name: str | None = None,
        url_contains: str | None = None,
        tag: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[CrawlRecord]:
        """Query crawl records with optional filters."""
        clauses: list[str] = []
        params: list[Any] = []
        if bot_name:
            clauses.append("bot_name = ?")
            params.append(bot_name)
        if url_contains:
            clauses.append("target_url LIKE ?")
            params.append(f"%{url_contains}%")
        if tag:
            clauses.append("tags LIKE ?")
            params.append(f"%{tag}%")
        if since:
            clauses.append("crawl_timestamp >= ?")
            params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM crawl_records {where} ORDER BY crawl_timestamp DESC LIMIT ?"
        params.append(limit)

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [CrawlRecord(**dict(r)) for r in rows]
        finally:
            conn.close()

    # =======================================================================
    # Financial Transactions
    # =======================================================================

    def insert_transaction(self, txn: FinancialTransaction) -> int:
        """Insert a financial transaction.

        Deduplicates on non-empty ``reference_id`` via an explicit
        pre-check. Returns ``0`` if the row was skipped as a duplicate,
        otherwise the new row id.

        Unlike ``INSERT OR IGNORE``, this only suppresses the
        *reference-id* conflict. Any other constraint violation
        (``NOT NULL``, type mismatch, …) surfaces as
        ``sqlite3.IntegrityError`` so bad input is not silently dropped.
        """
        with self._lock:
            conn = self._connect()
            try:
                if txn.reference_id:
                    existing = conn.execute(
                        "SELECT id FROM financial_transactions WHERE reference_id = ?",
                        (txn.reference_id,),
                    ).fetchone()
                    if existing:
                        return 0
                cur = conn.execute(
                    """INSERT INTO financial_transactions
                       (date, description, amount, category, account, institution,
                        transaction_type, source, reference_id, notes, recorded_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (txn.date, txn.description, txn.amount, txn.category,
                     txn.account, txn.institution, txn.transaction_type,
                     txn.source, txn.reference_id, txn.notes, txn.recorded_at),
                )
                conn.commit()
                return cur.lastrowid or 0
            finally:
                conn.close()

    def insert_transactions_batch(self, txns: list[FinancialTransaction]) -> int:
        """Bulk insert transactions with explicit dedup on reference_id.

        Returns the number of rows actually inserted (excluding
        duplicates).  Dedup is performed by pre-fetching the set of
        existing non-empty ``reference_id`` values and also tracking
        duplicates *within* the batch itself. Real constraint
        violations propagate as ``sqlite3.IntegrityError``.
        """
        if not txns:
            return 0
        with self._lock:
            conn = self._connect()
            try:
                # Pre-fetch already-stored reference_ids so we only
                # skip the ones we know collide.  An empty reference_id
                # is treated as "no dedup key" and always inserted.
                refs = [t.reference_id for t in txns if t.reference_id]
                existing: set[str] = set()
                if refs:
                    placeholders = ",".join("?" * len(refs))
                    rows = conn.execute(
                        f"SELECT reference_id FROM financial_transactions "
                        f"WHERE reference_id IN ({placeholders})",
                        refs,
                    ).fetchall()
                    existing = {row["reference_id"] for row in rows}

                seen_in_batch: set[str] = set()
                new_txns: list[FinancialTransaction] = []
                for t in txns:
                    if t.reference_id:
                        if t.reference_id in existing or t.reference_id in seen_in_batch:
                            continue
                        seen_in_batch.add(t.reference_id)
                    new_txns.append(t)

                if not new_txns:
                    return 0

                conn.executemany(
                    """INSERT INTO financial_transactions
                       (date, description, amount, category, account, institution,
                        transaction_type, source, reference_id, notes, recorded_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (t.date, t.description, t.amount, t.category,
                         t.account, t.institution, t.transaction_type,
                         t.source, t.reference_id, t.notes, t.recorded_at)
                        for t in new_txns
                    ],
                )
                conn.commit()
                return len(new_txns)
            finally:
                conn.close()

    def query_transactions(
        self,
        category: str | None = None,
        account: str | None = None,
        source: str | None = None,
        since: str | None = None,
        until: str | None = None,
        min_amount: float | None = None,
        max_amount: float | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FinancialTransaction]:
        """Query financial transactions with optional filters."""
        clauses: list[str] = []
        params: list[Any] = []
        if category:
            clauses.append("category = ?")
            params.append(category)
        if account:
            clauses.append("account = ?")
            params.append(account)
        if source:
            clauses.append("source = ?")
            params.append(source)
        if since:
            clauses.append("date >= ?")
            params.append(since)
        if until:
            clauses.append("date <= ?")
            params.append(until)
        if min_amount is not None:
            clauses.append("amount >= ?")
            params.append(min_amount)
        if max_amount is not None:
            clauses.append("amount <= ?")
            params.append(max_amount)
        if search:
            clauses.append("(description LIKE ? OR notes LIKE ?)")
            params.extend([f"%{search}%"] * 2)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM financial_transactions {where} ORDER BY date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [FinancialTransaction(**dict(r)) for r in rows]
        finally:
            conn.close()

    def spending_summary(
        self,
        since: str | None = None,
        until: str | None = None,
    ) -> dict[str, float]:
        """Get spending totals grouped by category."""
        clauses: list[str] = ["amount < 0"]
        params: list[Any] = []
        if since:
            clauses.append("date >= ?")
            params.append(since)
        if until:
            clauses.append("date <= ?")
            params.append(until)
        where = f"WHERE {' AND '.join(clauses)}"
        sql = f"""SELECT category, SUM(amount) as total
                  FROM financial_transactions {where}
                  GROUP BY category ORDER BY total ASC"""

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            return {row["category"]: row["total"] for row in rows}
        finally:
            conn.close()

    # =======================================================================
    # Financial Accounts
    # =======================================================================

    def upsert_account(self, acct: FinancialAccount) -> int:
        """Insert or update an account snapshot (by name + institution)."""
        with self._lock:
            conn = self._connect()
            try:
                existing = conn.execute(
                    "SELECT id FROM financial_accounts WHERE name = ? AND institution = ?",
                    (acct.name, acct.institution),
                ).fetchone()
                if existing:
                    conn.execute(
                        """UPDATE financial_accounts
                           SET balance = ?, account_type = ?, source = ?,
                               last_synced = ?, metadata = ?
                           WHERE id = ?""",
                        (acct.balance, acct.account_type, acct.source,
                         acct.last_synced, acct.metadata, existing["id"]),
                    )
                    conn.commit()
                    return existing["id"]
                else:
                    cur = conn.execute(
                        """INSERT INTO financial_accounts
                           (name, account_type, balance, institution, source,
                            last_synced, metadata)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (acct.name, acct.account_type, acct.balance,
                         acct.institution, acct.source, acct.last_synced,
                         acct.metadata),
                    )
                    conn.commit()
                    return cur.lastrowid or 0
            finally:
                conn.close()

    def get_accounts(
        self,
        institution: str | None = None,
        account_type: str | None = None,
    ) -> list[FinancialAccount]:
        """Retrieve account snapshots."""
        clauses: list[str] = []
        params: list[Any] = []
        if institution:
            clauses.append("institution = ?")
            params.append(institution)
        if account_type:
            clauses.append("account_type = ?")
            params.append(account_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM financial_accounts {where} ORDER BY institution, name"

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [FinancialAccount(**dict(r)) for r in rows]
        finally:
            conn.close()

    def net_worth(self) -> dict[str, Any]:
        """Calculate net worth from current account balances."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT account_type, SUM(balance) as total FROM financial_accounts GROUP BY account_type"
            ).fetchall()
            by_type = {row["account_type"]: row["total"] for row in rows}
            total = sum(by_type.values())
            return {"by_type": by_type, "total": total}
        finally:
            conn.close()

    # =======================================================================
    # Import helpers — ingest existing Guardian One data
    # =======================================================================

    def import_audit_jsonl(self, jsonl_path: Path | str) -> int:
        """Import existing audit.jsonl entries into system_logs.

        Uses a single bulk insert so importing a large audit log stays
        fast and does not hold the DB lock longer than necessary.

        Fields are coerced via ``_coerce_str`` so lines with explicit
        ``null`` values (e.g. ``"severity": null``) don't propagate
        as Python ``None`` into ``NOT NULL`` columns and abort the
        whole batch.
        """
        path = Path(jsonl_path)
        if not path.exists():
            return 0
        logs: list[SystemLog] = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if not isinstance(data, dict):
                        continue
                    logs.append(SystemLog(
                        timestamp=_coerce_str(data, "timestamp"),
                        agent=_coerce_str(data, "agent"),
                        action=_coerce_str(data, "action"),
                        severity=_coerce_str(data, "severity", "info"),
                        component="audit",
                        message=_coerce_str(data, "action"),
                        details=json.dumps(_coerce_dict(data, "details")),
                        source="audit.jsonl",
                    ))
                except (json.JSONDecodeError, TypeError):
                    continue
        return self.insert_logs_batch(logs)

    def import_cfo_ledger(self, ledger_path: Path | str) -> int:
        """Import existing cfo_ledger.json accounts into financial_accounts.

        Fields are coerced via ``_coerce_str`` / ``_coerce_float`` so
        ledger entries with explicit ``null`` values don't propagate
        as Python ``None`` into ``NOT NULL`` columns and abort the
        whole ledger import.

        A malformed or truncated ledger file is tolerated the same
        way ``import_audit_jsonl`` tolerates bad JSONL lines: the
        method logs a warning to stderr and returns ``0`` instead of
        raising ``json.JSONDecodeError``. This matters during Docker
        first-run initialization, where a corrupt optional seed file
        should not take down ``--db-init`` entirely.
        """
        path = Path(ledger_path)
        if not path.exists():
            return 0
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            # Mirror the per-line tolerance in import_audit_jsonl:
            # skip the import, keep going. The caller still gets 0.
            print(
                f"  [WARN] Skipping {path}: malformed or unreadable JSON ({exc})"
            )
            return 0
        if not isinstance(data, dict):
            return 0
        count = 0
        for acct in data.get("accounts", []) or []:
            if not isinstance(acct, dict):
                continue
            self.upsert_account(FinancialAccount(
                name=_coerce_str(acct, "name"),
                account_type=_coerce_str(acct, "account_type"),
                balance=_coerce_float(acct, "balance"),
                institution=_coerce_str(acct, "institution"),
                source="cfo_ledger",
                last_synced=_coerce_str(acct, "last_synced"),
            ))
            count += 1
        return count

    # =======================================================================
    # Database stats & maintenance
    # =======================================================================

    def stats(self) -> dict[str, Any]:
        """Return row counts for all tables."""
        conn = self._connect()
        try:
            tables = ["system_logs", "system_codes", "crawl_records",
                       "financial_transactions", "financial_accounts"]
            result: dict[str, Any] = {}
            for table in tables:
                row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                result[table] = row[0] if row else 0
            result["db_path"] = str(self._db_path)
            result["db_size_bytes"] = self._db_path.stat().st_size if self._db_path.exists() else 0
            return result
        finally:
            conn.close()

    def execute_raw(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Execute a raw read-only SQL query. For advanced queries.

        Enforcement is layered:

        1. Fast prefix check rejects obviously mutating statements before
           they even reach SQLite (INSERT/UPDATE/DELETE/DROP/ALTER/…).
        2. The SQL is executed on a connection opened with
           ``file:...?mode=ro``, so the SQLite engine itself refuses any
           write.  This blocks constructs like
           ``WITH x AS (SELECT 1) DELETE FROM system_logs`` that begin
           with a harmless keyword but still mutate state.

        Any write attempt is converted to ``ValueError``.
        """
        stripped = re.sub(r"--[^\n]*", "", sql)
        stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.DOTALL)
        head = stripped.strip().lstrip("(").lstrip().upper()
        if not (head.startswith("SELECT") or head.startswith("WITH")):
            raise ValueError(
                "execute_raw() is read-only; only SELECT or WITH statements "
                "are permitted. Use the typed helper methods for mutations."
            )
        # Open a *read-only* connection so the SQLite engine refuses any
        # mutating statement even if it sneaks past the prefix check
        # (e.g. ``WITH x AS (SELECT 1) DELETE ...``).
        uri = f"file:{self._db_path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError as exc:
            # Only remap *readonly-attempt* errors into ValueError. Other
            # OperationalError cases (missing table, syntax error, …)
            # are real query problems and should propagate unchanged so
            # callers can handle them properly.
            if "readonly" in str(exc).lower():
                raise ValueError(
                    f"execute_raw() refused mutating statement: {exc}"
                ) from exc
            raise
        finally:
            conn.close()

    def vacuum(self) -> None:
        """Compact the database file."""
        conn = self._connect()
        try:
            conn.execute("VACUUM")
        finally:
            conn.close()
