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
    normalize_iso_timestamp,
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


_NUMERIC_EXTRACT = re.compile(r"-?\d+(?:\.\d+)?")


def _coerce_float(d: dict[str, Any], key: str, default: float = 0.0) -> float:
    """Get a float field from a dict, parsing strings and falling back.

    Imported ledger files frequently contain amounts as strings with
    thousand separators (``"1,238.93"``), currency prefixes
    (``"$500.00"``, ``"-$99.99"``), currency suffixes
    (``"1,238.93 USD"``), or as garbage (``"N/A"``). Silently
    returning 0.0 for ``"1,238.93"`` or flipping the sign on
    ``"-$99.99"`` would corrupt balance totals, so we:

      1. fast-path ``int``/``float`` values,
      2. strip commas (thousand separators) and try ``float()``,
      3. regex-extract the first signed numeric token as a last
         resort for currency-prefixed / -suffixed strings; if the
         prefix before the match contains a bare ``-`` (as in
         ``"-$99.99"``), the sign is re-applied so debits aren't
         silently flipped into credits,
      4. fall back to ``default`` only if no numeric token is found.
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
        if parsed >= 0 and "-" in cleaned[: match.start()]:
            parsed = -parsed
        return parsed
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
-- Deduplication is keyed on (source, reference_id) so two different
-- providers (e.g. Plaid and Rocket Money) can legitimately use the
-- same reference_id without colliding. The old single-column
-- idx_txn_ref is dropped on startup for backwards compatibility with
-- existing DB files.
DROP INDEX IF EXISTS idx_txn_ref;
CREATE UNIQUE INDEX IF NOT EXISTS idx_txn_source_ref
    ON financial_transactions(source, reference_id)
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
        """Query system logs with optional filters.

        ``since`` / ``until`` are normalized to the DB's canonical
        millisecond-``Z`` format before being bound into the WHERE
        clause, so callers can pass ordinary ISO-8601 boundaries
        like ``2026-03-02T00:00:00Z`` and still get correct
        lexicographic comparison against stored values such as
        ``2026-03-02T00:00:00.100Z``.
        """
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
            params.append(normalize_iso_timestamp(since))
        if until:
            clauses.append("timestamp <= ?")
            params.append(normalize_iso_timestamp(until))
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
            # Normalize to canonical ms-Z format so boundaries like
            # ``...00:00Z`` compare correctly against stored values
            # like ``...00:00.100Z``.
            clauses.append("crawl_timestamp >= ?")
            params.append(normalize_iso_timestamp(since))
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

        Deduplicates on ``(source, reference_id)`` — a non-empty
        reference_id is only considered a duplicate if *the same
        source* already stored it. This lets multiple providers
        (Plaid, Rocket Money, Empower) use overlapping ID spaces
        without colliding with each other. Returns ``0`` if the row
        was skipped as a duplicate, otherwise the new row id.

        Unlike ``INSERT OR IGNORE``, this only suppresses the
        ``(source, reference_id)`` conflict. Any other constraint
        violation surfaces as ``sqlite3.IntegrityError``.
        """
        with self._lock:
            conn = self._connect()
            try:
                if txn.reference_id:
                    existing = conn.execute(
                        "SELECT id FROM financial_transactions "
                        "WHERE source = ? AND reference_id = ?",
                        (txn.source, txn.reference_id),
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
        """Bulk insert transactions with explicit dedup on
        ``(source, reference_id)``.

        Returns the number of rows actually inserted (excluding
        duplicates). Dedup is performed by pre-fetching the set of
        existing ``(source, reference_id)`` pairs for the incoming
        reference_ids and tracking in-batch collisions with the same
        tuple key. Real constraint violations propagate as
        ``sqlite3.IntegrityError``.
        """
        if not txns:
            return 0
        with self._lock:
            conn = self._connect()
            try:
                # Pre-fetch already-stored (source, reference_id)
                # pairs for any incoming non-empty reference_id, so
                # we only skip rows that actually collide with the
                # same-source record already in the DB.  An empty
                # reference_id is treated as "no dedup key" and
                # always inserted.
                refs = [t.reference_id for t in txns if t.reference_id]
                existing_pairs: set[tuple[str, str]] = set()
                if refs:
                    placeholders = ",".join("?" * len(refs))
                    rows = conn.execute(
                        f"SELECT source, reference_id FROM financial_transactions "
                        f"WHERE reference_id IN ({placeholders})",
                        refs,
                    ).fetchall()
                    existing_pairs = {
                        (row["source"], row["reference_id"]) for row in rows
                    }

                seen_in_batch: set[tuple[str, str]] = set()
                new_txns: list[FinancialTransaction] = []
                for t in txns:
                    if t.reference_id:
                        key = (t.source, t.reference_id)
                        if key in existing_pairs or key in seen_in_batch:
                            continue
                        seen_in_batch.add(key)
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

    def replace_transactions_for_source(
        self,
        source: str,
        txns: list[FinancialTransaction],
    ) -> int:
        """Atomically replace all rows where ``source = <source>``.

        This is the right primitive for mirroring a mutable in-memory
        ledger (such as CFO's ``self._transactions``) where rows can
        be added, removed, and reordered between calls. A plain
        ``insert_transactions_batch`` would rely on stable
        reference_ids that survive reorder/delete, which is
        effectively impossible without a persistent row UUID.

        Delete-and-insert semantics are unconditional: passing an
        empty ``txns`` is a legitimate "the caller has zero rows
        for this source" snapshot and the slice is cleared
        accordingly. This is important because CFO's
        ``save_ledger`` must be able to converge the mirror to an
        empty state after ``clean_ledger`` or a user-initiated
        truncation; a previous version of this method short-
        circuited on empty input and left stale rows behind. Rows
        with other ``source`` values (manual inserts, audit
        mirror, other provider syncs) are untouched.

        **Caller responsibility:** callers with risky upstream
        paths (broken iterators, provider failures) must add their
        own empty-input guard at the call site so an unintended
        no-op doesn't wipe the slice. The manager intentionally
        does not second-guess its callers here.

        Returns the number of rows inserted (0 for an empty
        snapshot, which still runs the DELETE).
        """
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM financial_transactions WHERE source = ?",
                    (source,),
                )
                if txns:
                    conn.executemany(
                        """INSERT INTO financial_transactions
                           (date, description, amount, category, account, institution,
                            transaction_type, source, reference_id, notes, recorded_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        [
                            (t.date, t.description, t.amount, t.category,
                             t.account, t.institution, t.transaction_type,
                             source, t.reference_id, t.notes, t.recorded_at)
                            for t in txns
                        ],
                    )
                conn.commit()
                return len(txns)
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

    def replace_accounts_for_source(
        self,
        source: str,
        accounts: list[FinancialAccount],
    ) -> int:
        """Atomically replace all account rows where ``source = <source>``.

        Symmetric to ``replace_transactions_for_source``. The right
        primitive for mirroring a full provider snapshot: if an
        account was closed or disconnected upstream, it disappears
        from the current payload and the existing DB row for it
        must be removed. A plain ``upsert_account`` loop would
        leave stale rows behind, inflating ``net_worth()`` and
        account listings.

        Rows with other ``source`` values are untouched.

        Delete-and-insert is unconditional: passing an empty
        ``accounts`` list is a legitimate "the caller has zero
        accounts for this source" snapshot and clears the slice.
        Callers with risky upstream paths should add their own
        empty-input guard.

        Returns the number of rows inserted.
        """
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM financial_accounts WHERE source = ?",
                    (source,),
                )
                if accounts:
                    conn.executemany(
                        """INSERT INTO financial_accounts
                           (name, account_type, balance, institution, source,
                            last_synced, metadata)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        [
                            (a.name, a.account_type, a.balance,
                             a.institution, source, a.last_synced,
                             a.metadata)
                            for a in accounts
                        ],
                    )
                conn.commit()
                return len(accounts)
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

    # Canonical "unknown past" timestamp used when an imported audit
    # row has an unparseable ``timestamp`` field. All such rows
    # cluster at epoch-zero so they can never pollute real
    # time-window filters, and ORDER BY DESC still produces a sane
    # ordering (they land at the very end instead of mid-range).
    _EPOCH_ZERO = "1970-01-01T00:00:00.000Z"

    def _parse_audit_file(self, path: Path) -> list[SystemLog] | None:
        """Parse a single audit JSONL file into SystemLog rows.

        Non-UTF-8 bytes are replaced rather than raising, bad lines
        are skipped, and null fields are coerced so ``NOT NULL``
        columns never see Python ``None``. Timestamps are normalized
        to the canonical millisecond-``Z`` format so lex ordering
        matches DB-native rows. Unparseable timestamps are rewritten
        to the canonical epoch-zero sentinel so they can't silently
        land between real rows and corrupt time-window queries.

        Returns ``None`` when the file cannot be read at all (e.g.
        permission error). Callers use that signal to skip the
        delete-and-replace step so a *partial* parse failure across
        rotated siblings never wipes prior audit history.
        Returns an empty list when the file is missing or simply
        contains no valid rows — that is a legitimate "nothing to
        import" outcome, not a read failure.
        """
        if not path.exists():
            return []
        logs: list[SystemLog] = []
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if not isinstance(data, dict):
                            continue
                        raw_ts = _coerce_str(data, "timestamp")
                        canonical = normalize_iso_timestamp(raw_ts)
                        # Shape check AND a real datetime round-trip.
                        # A naive ``len == 24 and endswith('Z')``
                        # check would accept lookalike garbage like
                        # ``2026-13-40T25:61:61.999Z`` (impossible
                        # month/day/hour/minute/second). We verify
                        # the canonical string actually parses back
                        # into a ``datetime`` before trusting it;
                        # anything that fails is rewritten to the
                        # epoch sentinel so bad rows never pollute
                        # lex-ordered TEXT comparisons.
                        valid = (
                            len(canonical) == 24
                            and canonical.endswith("Z")
                            and canonical[19] == "."
                        )
                        if valid:
                            try:
                                datetime.fromisoformat(
                                    canonical.replace("Z", "+00:00")
                                )
                            except ValueError:
                                valid = False
                        if not valid:
                            canonical = self._EPOCH_ZERO
                        logs.append(SystemLog(
                            timestamp=canonical,
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
        except OSError as exc:
            print(f"  [WARN] Skipping {path}: unreadable ({exc})")
            return None
        return logs

    def _rotated_audit_files(self, current: Path) -> list[Path]:
        """Return audit log files in chronological order (oldest first).

        The Guardian One audit subsystem rotates ``audit.jsonl`` into
        ``audit.jsonl.1`` … ``audit.jsonl.5``, where the *higher* the
        numeric suffix the *older* the file. To preserve the original
        event order we return the rotated siblings sorted by suffix
        descending (``.5`` → ``.1``) and then append the current file
        last (newest). Only siblings whose suffix is a pure integer
        are considered so we don't accidentally sweep in other
        artifacts.
        """
        parent = current.parent
        prefix = current.name + "."
        rotated: list[tuple[int, Path]] = []
        if parent.is_dir():
            for sibling in parent.iterdir():
                if not sibling.is_file() or not sibling.name.startswith(prefix):
                    continue
                suffix = sibling.name[len(prefix):]
                if not suffix.isdigit():
                    continue
                rotated.append((int(suffix), sibling))
        rotated.sort(key=lambda pair: pair[0], reverse=True)  # oldest first
        ordered = [p for _, p in rotated]
        if current.exists():
            ordered.append(current)
        return ordered

    def import_audit_jsonl(self, jsonl_path: Path | str) -> int:
        """Import existing audit logs into ``system_logs``.

        Handles rotated siblings (``audit.jsonl.1`` … ``audit.jsonl.5``)
        in chronological order so no history is lost when the log
        has been rotated.

        **Idempotent:** when every file parses cleanly AND at least
        one file yields at least one parseable row, every call
        replaces all rows where ``source = 'audit.jsonl'`` in a
        single transaction, so re-running ``--db-init`` (e.g. after
        an entrypoint sentinel recovery) does not accumulate
        duplicate rows. Rows written directly through ``insert_log``
        with a different ``source`` are untouched.

        **Data-loss guards:** the delete-and-replace is skipped when
        either

          1. *any* file in the rotated set exists but cannot be read
             (``_parse_audit_file`` returns ``None``). Proceeding in
             this state would replace complete history with a
             partial subset. We'd rather keep the existing rows
             stale than silently drop half of them.
          2. no file yields any valid row. This covers missing
             directories, empty files, and fully-corrupt files.

        In either case the method returns ``0`` without touching
        the table.
        """
        path = Path(jsonl_path)
        files = self._rotated_audit_files(path)

        all_logs: list[SystemLog] = []
        for fp in files:
            parsed = self._parse_audit_file(fp)
            if parsed is None:
                # File existed but was unreadable. Refuse to wipe
                # existing history when we can't trust the replacement.
                print(
                    f"  [WARN] Aborting audit import: one or more source "
                    f"files could not be read ({fp}). Existing history "
                    f"left untouched."
                )
                return 0
            all_logs.extend(parsed)

        if not all_logs:
            # Nothing to import — files are missing, empty, or
            # yielded zero valid rows. Skip the delete-and-replace
            # so we don't wipe previously-imported history.
            return 0

        # Delete-and-replace the imported slice atomically so retries
        # from --db-init stay idempotent for the same source file.
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM system_logs WHERE source = ?",
                    ("audit.jsonl",),
                )
                conn.executemany(
                    """INSERT INTO system_logs
                       (timestamp, agent, action, severity, component, message, details, source)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (log.timestamp, log.agent, log.action, log.severity,
                         log.component, log.message, log.details, log.source)
                        for log in all_logs
                    ],
                )
                conn.commit()
                return len(all_logs)
            finally:
                conn.close()

    def import_cfo_ledger(self, ledger_path: Path | str) -> int:
        """Import existing cfo_ledger.json into financial_accounts AND
        financial_transactions.

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

        Snapshot semantics:

        * Accounts are treated as a full snapshot. The ``cfo_ledger``
          slice of ``financial_accounts`` is *replaced* with the
          accounts in the ledger so a closed account that was
          dropped upstream also disappears from the DB. The
          ``accounts`` key is required for this step — if it's
          missing (or not a list), the account slice is left alone.
        * Transactions are also a full snapshot when the
          ``transactions`` key is present. Missing key → slice left
          alone (old-format ledger); explicit ``[]`` → slice wiped.

        Returns the number of *accounts* imported (the historical
        meaning of this method). Transaction counts are logged via
        the standard replace path.
        """
        path = Path(ledger_path)
        if not path.exists():
            return 0
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            print(
                f"  [WARN] Skipping {path}: malformed or unreadable JSON ({exc})"
            )
            return 0
        if not isinstance(data, dict):
            return 0

        # --- Accounts -------------------------------------------------
        # Only touch the account slice when the key is actually
        # present; old-format / partial ledgers are left alone.
        count = 0
        if "accounts" in data:
            raw_accounts = data.get("accounts") or []
            if isinstance(raw_accounts, list):
                parsed_accts: list[FinancialAccount] = []
                for acct in raw_accounts:
                    if not isinstance(acct, dict):
                        continue
                    parsed_accts.append(FinancialAccount(
                        name=_coerce_str(acct, "name"),
                        account_type=_coerce_str(acct, "account_type"),
                        balance=_coerce_float(acct, "balance"),
                        institution=_coerce_str(acct, "institution"),
                        source="cfo_ledger",
                        last_synced=_coerce_str(acct, "last_synced"),
                    ))
                self.replace_accounts_for_source("cfo_ledger", parsed_accts)
                count = len(parsed_accts)

        # --- Transactions ---------------------------------------------
        # Only touch the transactions slice when the key is actually
        # present; old-format ledgers (accounts only) are left alone.
        if "transactions" in data:
            raw_txns = data.get("transactions") or []
            if isinstance(raw_txns, list):
                parsed: list[FinancialTransaction] = []
                occurrence: dict[tuple[str, str, float, str], int] = {}
                for tx in raw_txns:
                    if not isinstance(tx, dict):
                        continue
                    meta = tx.get("metadata") or {}
                    if not isinstance(meta, dict):
                        meta = {}
                    provider_id = (
                        meta.get("id")
                        or meta.get("provider_id")
                        or meta.get("plaid_id")
                        or meta.get("transaction_id")
                    )
                    date = _coerce_str(tx, "date")
                    description = _coerce_str(tx, "description")
                    amount = _coerce_float(tx, "amount")
                    category = _coerce_str(tx, "category")
                    account = _coerce_str(tx, "account")
                    if provider_id:
                        ref = str(provider_id)
                    else:
                        key = (account, date, amount, description)
                        n = occurrence.get(key, 0)
                        occurrence[key] = n + 1
                        ref = (
                            f"cfo_ledger:{account}|{date}|"
                            f"{amount}|{description}#{n}"
                        )
                    parsed.append(FinancialTransaction(
                        date=date,
                        description=description,
                        amount=amount,
                        category=category,
                        account=account,
                        source="cfo_ledger",
                        reference_id=ref,
                    ))
                self.replace_transactions_for_source("cfo_ledger", parsed)

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
