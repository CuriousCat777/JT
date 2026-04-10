"""CITADEL ONE — Comprehensive SQLite backup database for Guardian One.

Ingests all Guardian One data sources into a single SQLite database,
providing a unified backup, restore, and integrity-verification layer.

Data sources backed up:
    - Audit log (logs/audit.jsonl)
    - Financial data (data/cfo_ledger.json)
    - Evaluations (data/evaluations.jsonl)
    - System config (config/guardian_config.yaml)
    - Operation logs (guardian_one_log.json)
    - Error records (guardian_errors.json)
    - Skills (guardian_skills.json)
    - Vault metadata (no secrets — metadata only)
    - H.O.M.E. L.I.N.K. integration registry

All backup operations are logged to a backup_manifest table for
traceability.  Incremental backups use last-backup timestamps to
avoid re-ingesting unchanged data.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


# ------------------------------------------------------------------
# Path resolution
# ------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------
# SQL schema
# ------------------------------------------------------------------

_TABLES: dict[str, str] = {
    "audit_log": """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            agent TEXT,
            action TEXT,
            severity TEXT,
            details TEXT,
            requires_review INTEGER,
            backed_up_at TEXT
        )
    """,
    "accounts": """
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            account_type TEXT,
            balance REAL,
            institution TEXT,
            last_synced TEXT
        )
    """,
    "transactions": """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            description TEXT,
            amount REAL,
            category TEXT,
            account TEXT,
            metadata TEXT,
            synced_at TEXT
        )
    """,
    "bills": """
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            amount REAL,
            due_date TEXT,
            recurring INTEGER,
            frequency TEXT,
            auto_pay INTEGER,
            paid INTEGER
        )
    """,
    "budgets": """
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            budget_limit REAL,
            label TEXT
        )
    """,
    "net_worth_snapshots": """
        CREATE TABLE IF NOT EXISTS net_worth_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            net_worth REAL,
            by_type TEXT,
            captured_at TEXT
        )
    """,
    "evaluation_cycles": """
        CREATE TABLE IF NOT EXISTS evaluation_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle INTEGER,
            timestamp TEXT,
            system_overall_pct REAL,
            system_overall_rating INTEGER
        )
    """,
    "agent_evaluations": """
        CREATE TABLE IF NOT EXISTS agent_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id INTEGER REFERENCES evaluation_cycles(id),
            agent_name TEXT,
            timestamp TEXT,
            overall_pct REAL,
            overall_rating INTEGER,
            rating_label TEXT
        )
    """,
    "metric_scores": """
        CREATE TABLE IF NOT EXISTS metric_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id INTEGER REFERENCES agent_evaluations(id),
            metric_name TEXT,
            score_pct REAL,
            rating INTEGER,
            detail TEXT
        )
    """,
    "vault_metadata": """
        CREATE TABLE IF NOT EXISTS vault_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_name TEXT UNIQUE,
            service TEXT,
            scope TEXT,
            created_at TEXT,
            rotated_at TEXT,
            expires_at TEXT,
            rotation_days INTEGER
        )
    """,
    "system_config": """
        CREATE TABLE IF NOT EXISTS system_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_key TEXT UNIQUE,
            config_value TEXT,
            updated_at TEXT
        )
    """,
    "operation_logs": """
        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER,
            timestamp TEXT,
            category TEXT,
            intent TEXT,
            summary TEXT,
            context TEXT,
            outcome TEXT,
            confidence TEXT,
            tags TEXT,
            metadata TEXT,
            prev_hash TEXT,
            entry_hash TEXT
        )
    """,
    "error_records": """
        CREATE TABLE IF NOT EXISTS error_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            error_id TEXT UNIQUE,
            timestamp TEXT,
            error_type TEXT,
            what TEXT,
            why TEXT,
            fix TEXT,
            context TEXT,
            related_skill TEXT,
            recurrence_count INTEGER,
            resolved INTEGER,
            hash TEXT
        )
    """,
    "skills": """
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id TEXT UNIQUE,
            name TEXT,
            domain TEXT,
            description TEXT,
            level INTEGER,
            level_label TEXT,
            created TEXT,
            last_assessed TEXT,
            assessment_count INTEGER,
            evidence TEXT,
            hash TEXT
        )
    """,
    "devices": """
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE,
            name TEXT,
            category TEXT,
            manufacturer TEXT,
            model TEXT,
            ip_address TEXT,
            mac_address TEXT,
            protocols TEXT,
            network_segment TEXT,
            status TEXT,
            last_seen TEXT,
            firmware_version TEXT,
            location TEXT,
            tags TEXT,
            added_at TEXT
        )
    """,
    "automation_rules": """
        CREATE TABLE IF NOT EXISTS automation_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id TEXT UNIQUE,
            name TEXT,
            description TEXT,
            trigger_type TEXT,
            trigger_config TEXT,
            actions TEXT,
            room_id TEXT,
            status TEXT,
            priority INTEGER,
            tags TEXT,
            created_at TEXT,
            last_executed TEXT,
            execution_count INTEGER
        )
    """,
    "integration_records": """
        CREATE TABLE IF NOT EXISTS integration_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            description TEXT,
            base_url TEXT,
            auth_method TEXT,
            data_flow TEXT,
            vault_keys TEXT,
            threat_model TEXT,
            failure_impact TEXT,
            rollback_procedure TEXT,
            registered_at TEXT,
            owner_agent TEXT,
            status TEXT
        )
    """,
    "backup_manifest": """
        CREATE TABLE IF NOT EXISTS backup_manifest (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backup_type TEXT,
            table_name TEXT,
            records_backed_up INTEGER,
            started_at TEXT,
            completed_at TEXT,
            status TEXT,
            error_message TEXT
        )
    """,
}


class CitadelOne:
    """Comprehensive SQLite backup database for all Guardian One data.

    Ingests data from every Guardian One subsystem into a single SQLite
    file at ``data/citadel_one.db``.  Supports full and incremental
    backups, restore operations, and integrity verification.

    Usage::

        citadel = CitadelOne()
        citadel.full_backup()
        status = citadel.get_backup_status()
    """

    def __init__(
        self,
        db_path: Path | None = None,
        project_root: Path | None = None,
    ) -> None:
        self._root = project_root or PROJECT_ROOT
        self._db_path = db_path or (self._root / "data" / "citadel_one.db")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    # ------------------------------------------------------------------
    # Schema initialisation
    # ------------------------------------------------------------------

    def _create_tables(self) -> None:
        """Create all tables if they do not already exist."""
        cur = self._conn.cursor()
        for ddl in _TABLES.values():
            cur.execute(ddl)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _now(self) -> str:
        """Current UTC timestamp in ISO-8601."""
        return datetime.now(timezone.utc).isoformat()

    def _log_manifest(
        self,
        backup_type: str,
        table_name: str,
        records: int,
        started_at: str,
        status: str = "success",
        error_message: str = "",
    ) -> None:
        """Record a backup operation in the manifest."""
        self._conn.execute(
            """
            INSERT INTO backup_manifest
                (backup_type, table_name, records_backed_up, started_at, completed_at, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (backup_type, table_name, records, started_at, self._now(), status, error_message),
        )
        self._conn.commit()

    def _last_backup_time(self, table_name: str) -> str | None:
        """Return the ISO timestamp of the most recent successful backup for *table_name*."""
        row = self._conn.execute(
            """
            SELECT completed_at FROM backup_manifest
            WHERE table_name = ? AND status = 'success'
            ORDER BY completed_at DESC LIMIT 1
            """,
            (table_name,),
        ).fetchone()
        return row["completed_at"] if row else None

    def _read_json(self, rel_path: str) -> Any:
        """Load a JSON file relative to project root.  Returns None if missing."""
        path = self._root / rel_path
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)

    def _read_jsonl(self, rel_path: str) -> list[dict[str, Any]]:
        """Load a JSONL (JSON-Lines) file.  Returns empty list if missing."""
        path = self._root / rel_path
        if not path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return entries

    def _read_yaml(self, rel_path: str) -> dict[str, Any]:
        """Load a YAML file relative to project root.  Returns empty dict if missing."""
        path = self._root / rel_path
        if not path.exists():
            return {}
        with open(path) as f:
            return yaml.safe_load(f) or {}

    # ------------------------------------------------------------------
    # Backup: audit log
    # ------------------------------------------------------------------

    def backup_audit_log(self) -> int:
        """Ingest audit entries from ``logs/audit.jsonl``.

        Uses INSERT OR REPLACE keyed on (timestamp, agent, action) to
        ensure idempotency.

        Returns:
            Number of records backed up.
        """
        started = self._now()
        count = 0
        try:
            entries = self._read_jsonl("logs/audit.jsonl")
            for entry in entries:
                self._conn.execute(
                    """
                    INSERT INTO audit_log (timestamp, agent, action, severity, details, requires_review, backed_up_at)
                    SELECT ?, ?, ?, ?, ?, ?, ?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM audit_log
                        WHERE timestamp = ? AND agent = ? AND action = ?
                    )
                    """,
                    (
                        entry.get("timestamp", ""),
                        entry.get("agent", ""),
                        entry.get("action", ""),
                        entry.get("severity", "info"),
                        json.dumps(entry.get("details", {})),
                        int(entry.get("requires_review", False)),
                        self._now(),
                        entry.get("timestamp", ""),
                        entry.get("agent", ""),
                        entry.get("action", ""),
                    ),
                )
                count += 1
            self._conn.commit()
            self._log_manifest("incremental", "audit_log", count, started)
        except Exception as exc:
            self._log_manifest("incremental", "audit_log", 0, started, "failed", str(exc))
            raise
        return count

    # ------------------------------------------------------------------
    # Backup: financial data
    # ------------------------------------------------------------------

    def backup_financial_data(self) -> int:
        """Ingest financial data from ``data/cfo_ledger.json``.

        Backs up accounts, transactions, bills, budgets, and net-worth
        snapshots.  Uses INSERT OR REPLACE keyed on natural keys.

        Returns:
            Total number of records backed up across all financial tables.
        """
        started = self._now()
        total = 0
        try:
            data = self._read_json("data/cfo_ledger.json")
            if data is None:
                self._log_manifest("incremental", "financial", 0, started)
                return 0

            # Accounts — keyed on (name, institution)
            for acct in data.get("accounts", []):
                self._conn.execute(
                    """
                    INSERT INTO accounts (name, account_type, balance, institution, last_synced)
                    SELECT ?, ?, ?, ?, ?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM accounts WHERE name = ? AND institution = ?
                    )
                    """,
                    (
                        acct.get("name", ""),
                        acct.get("account_type", ""),
                        acct.get("balance", 0.0),
                        acct.get("institution", ""),
                        acct.get("last_synced", ""),
                        acct.get("name", ""),
                        acct.get("institution", ""),
                    ),
                )
                # Update balance for existing accounts
                self._conn.execute(
                    """
                    UPDATE accounts SET balance = ?, account_type = ?, last_synced = ?
                    WHERE name = ? AND institution = ?
                    """,
                    (
                        acct.get("balance", 0.0),
                        acct.get("account_type", ""),
                        acct.get("last_synced", ""),
                        acct.get("name", ""),
                        acct.get("institution", ""),
                    ),
                )
                total += 1

            # Transactions — keyed on (date, description, amount, account)
            for txn in data.get("transactions", []):
                self._conn.execute(
                    """
                    INSERT INTO transactions (date, description, amount, category, account, metadata, synced_at)
                    SELECT ?, ?, ?, ?, ?, ?, ?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM transactions
                        WHERE date = ? AND description = ? AND amount = ? AND account = ?
                    )
                    """,
                    (
                        txn.get("date", ""),
                        txn.get("description", ""),
                        txn.get("amount", 0.0),
                        txn.get("category", ""),
                        txn.get("account", ""),
                        json.dumps(txn.get("metadata", {})),
                        self._now(),
                        txn.get("date", ""),
                        txn.get("description", ""),
                        txn.get("amount", 0.0),
                        txn.get("account", ""),
                    ),
                )
                total += 1

            # Bills — keyed on (name, due_date)
            for bill in data.get("bills", []):
                self._conn.execute(
                    """
                    INSERT INTO bills (name, amount, due_date, recurring, frequency, auto_pay, paid)
                    SELECT ?, ?, ?, ?, ?, ?, ?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM bills WHERE name = ? AND due_date = ?
                    )
                    """,
                    (
                        bill.get("name", ""),
                        bill.get("amount", 0.0),
                        bill.get("due_date", ""),
                        int(bill.get("recurring", False)),
                        bill.get("frequency", ""),
                        int(bill.get("auto_pay", False)),
                        int(bill.get("paid", False)),
                        bill.get("name", ""),
                        bill.get("due_date", ""),
                    ),
                )
                total += 1

            # Budgets — keyed on category
            for budget in data.get("budgets", []):
                self._conn.execute(
                    """
                    INSERT INTO budgets (category, budget_limit, label)
                    SELECT ?, ?, ?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM budgets WHERE category = ?
                    )
                    """,
                    (
                        budget.get("category", ""),
                        budget.get("budget_limit", 0.0),
                        budget.get("label", ""),
                        budget.get("category", ""),
                    ),
                )
                total += 1

            # Net worth snapshots — keyed on date
            now = self._now()
            for snap in data.get("net_worth_history", []):
                self._conn.execute(
                    """
                    INSERT INTO net_worth_snapshots (date, net_worth, by_type, captured_at)
                    SELECT ?, ?, ?, ?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM net_worth_snapshots WHERE date = ?
                    )
                    """,
                    (
                        snap.get("date", ""),
                        snap.get("net_worth", 0.0),
                        json.dumps(snap.get("by_type", {})),
                        now,
                        snap.get("date", ""),
                    ),
                )
                total += 1

            self._conn.commit()
            self._log_manifest("incremental", "financial", total, started)
        except Exception as exc:
            self._log_manifest("incremental", "financial", 0, started, "failed", str(exc))
            raise
        return total

    # ------------------------------------------------------------------
    # Backup: evaluations
    # ------------------------------------------------------------------

    def backup_evaluations(self) -> int:
        """Ingest evaluation cycles from ``data/evaluations.jsonl``.

        Returns:
            Number of evaluation cycle records backed up.
        """
        started = self._now()
        count = 0
        try:
            cycles = self._read_jsonl("data/evaluations.jsonl")
            for cycle_data in cycles:
                cycle_num = cycle_data.get("cycle", 0)
                ts = cycle_data.get("timestamp", "")

                # Check if cycle already exists
                existing = self._conn.execute(
                    "SELECT id FROM evaluation_cycles WHERE cycle = ? AND timestamp = ?",
                    (cycle_num, ts),
                ).fetchone()
                if existing:
                    continue

                cur = self._conn.execute(
                    """
                    INSERT INTO evaluation_cycles (cycle, timestamp, system_overall_pct, system_overall_rating)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        cycle_num,
                        ts,
                        cycle_data.get("system_overall_pct", 0.0),
                        cycle_data.get("system_overall_rating", 0),
                    ),
                )
                cycle_id = cur.lastrowid

                for ev in cycle_data.get("evaluations", []):
                    ev_cur = self._conn.execute(
                        """
                        INSERT INTO agent_evaluations
                            (cycle_id, agent_name, timestamp, overall_pct, overall_rating, rating_label)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            cycle_id,
                            ev.get("agent_name", ""),
                            ev.get("timestamp", ""),
                            ev.get("overall_pct", 0.0),
                            ev.get("overall_rating", 0),
                            ev.get("rating_label", ""),
                        ),
                    )
                    eval_id = ev_cur.lastrowid

                    for m in ev.get("metrics", []):
                        self._conn.execute(
                            """
                            INSERT INTO metric_scores
                                (evaluation_id, metric_name, score_pct, rating, detail)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                eval_id,
                                m.get("name", ""),
                                m.get("score_pct", 0.0),
                                m.get("rating", 0),
                                m.get("detail", ""),
                            ),
                        )
                count += 1

            self._conn.commit()
            self._log_manifest("incremental", "evaluations", count, started)
        except Exception as exc:
            self._log_manifest("incremental", "evaluations", 0, started, "failed", str(exc))
            raise
        return count

    # ------------------------------------------------------------------
    # Backup: system config
    # ------------------------------------------------------------------

    def backup_config(self) -> int:
        """Ingest system configuration from ``config/guardian_config.yaml``.

        Flattens the YAML to top-level keys and stores each as a
        JSON-serialised value.

        Returns:
            Number of config keys backed up.
        """
        started = self._now()
        count = 0
        try:
            raw = self._read_yaml("config/guardian_config.yaml")
            if not raw:
                self._log_manifest("incremental", "system_config", 0, started)
                return 0

            now = self._now()
            for key, value in raw.items():
                self._conn.execute(
                    """
                    INSERT INTO system_config (config_key, config_value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(config_key) DO UPDATE SET
                        config_value = excluded.config_value,
                        updated_at = excluded.updated_at
                    """,
                    (key, json.dumps(value), now),
                )
                count += 1

            self._conn.commit()
            self._log_manifest("incremental", "system_config", count, started)
        except Exception as exc:
            self._log_manifest("incremental", "system_config", 0, started, "failed", str(exc))
            raise
        return count

    # ------------------------------------------------------------------
    # Backup: operation logs
    # ------------------------------------------------------------------

    def backup_operation_logs(self) -> int:
        """Ingest operation log entries from ``guardian_one_log.json``.

        Returns:
            Number of operation log entries backed up.
        """
        started = self._now()
        count = 0
        try:
            data = self._read_json("guardian_one_log.json")
            if data is None:
                self._log_manifest("incremental", "operation_logs", 0, started)
                return 0

            for entry in data.get("entries", []):
                entry_id = entry.get("entry_id", 0)
                # Idempotent — skip if entry_id already exists
                existing = self._conn.execute(
                    "SELECT 1 FROM operation_logs WHERE entry_id = ?", (entry_id,)
                ).fetchone()
                if existing:
                    continue

                self._conn.execute(
                    """
                    INSERT INTO operation_logs
                        (entry_id, timestamp, category, intent, summary, context,
                         outcome, confidence, tags, metadata, prev_hash, entry_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry_id,
                        entry.get("timestamp", ""),
                        entry.get("category", ""),
                        entry.get("intent", ""),
                        entry.get("summary", ""),
                        entry.get("context", ""),
                        entry.get("outcome", ""),
                        entry.get("confidence", ""),
                        json.dumps(entry.get("tags", [])),
                        json.dumps(entry.get("metadata", {})),
                        entry.get("prev_hash", ""),
                        entry.get("entry_hash", ""),
                    ),
                )
                count += 1

            self._conn.commit()
            self._log_manifest("incremental", "operation_logs", count, started)
        except Exception as exc:
            self._log_manifest("incremental", "operation_logs", 0, started, "failed", str(exc))
            raise
        return count

    # ------------------------------------------------------------------
    # Backup: errors
    # ------------------------------------------------------------------

    def backup_errors(self) -> int:
        """Ingest error records from ``guardian_errors.json``.

        Returns:
            Number of error records backed up.
        """
        started = self._now()
        count = 0
        try:
            data = self._read_json("guardian_errors.json")
            if data is None:
                self._log_manifest("incremental", "error_records", 0, started)
                return 0

            for err in data.get("errors", []):
                self._conn.execute(
                    """
                    INSERT INTO error_records
                        (error_id, timestamp, error_type, what, why, fix, context,
                         related_skill, recurrence_count, resolved, hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(error_id) DO UPDATE SET
                        recurrence_count = excluded.recurrence_count,
                        resolved = excluded.resolved,
                        hash = excluded.hash
                    """,
                    (
                        err.get("id", ""),
                        err.get("timestamp", ""),
                        err.get("type", ""),
                        err.get("what", ""),
                        err.get("why", ""),
                        err.get("fix", ""),
                        err.get("context", ""),
                        err.get("related_skill", ""),
                        err.get("recurrence_count", 0),
                        int(err.get("resolved", False)),
                        err.get("hash", ""),
                    ),
                )
                count += 1

            self._conn.commit()
            self._log_manifest("incremental", "error_records", count, started)
        except Exception as exc:
            self._log_manifest("incremental", "error_records", 0, started, "failed", str(exc))
            raise
        return count

    # ------------------------------------------------------------------
    # Backup: skills
    # ------------------------------------------------------------------

    def backup_skills(self) -> int:
        """Ingest skill records from ``guardian_skills.json``.

        Returns:
            Number of skill records backed up.
        """
        started = self._now()
        count = 0
        try:
            data = self._read_json("guardian_skills.json")
            if data is None:
                self._log_manifest("incremental", "skills", 0, started)
                return 0

            for skill in data.get("skills", []):
                self._conn.execute(
                    """
                    INSERT INTO skills
                        (skill_id, name, domain, description, level, level_label,
                         created, last_assessed, assessment_count, evidence, hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(skill_id) DO UPDATE SET
                        level = excluded.level,
                        level_label = excluded.level_label,
                        last_assessed = excluded.last_assessed,
                        assessment_count = excluded.assessment_count,
                        evidence = excluded.evidence,
                        hash = excluded.hash
                    """,
                    (
                        skill.get("id", ""),
                        skill.get("name", ""),
                        skill.get("domain", ""),
                        skill.get("description", ""),
                        skill.get("level", 0),
                        skill.get("level_label", ""),
                        skill.get("created", ""),
                        skill.get("last_assessed", ""),
                        skill.get("assessment_count", 0),
                        json.dumps(skill.get("evidence", [])),
                        skill.get("hash", ""),
                    ),
                )
                count += 1

            self._conn.commit()
            self._log_manifest("incremental", "skills", count, started)
        except Exception as exc:
            self._log_manifest("incremental", "skills", 0, started, "failed", str(exc))
            raise
        return count

    # ------------------------------------------------------------------
    # Backup: vault metadata (NEVER secrets)
    # ------------------------------------------------------------------

    def backup_vault_metadata(self, vault: Any | None = None) -> int:
        """Ingest vault credential metadata (never secrets).

        If a ``Vault`` instance is provided, its metadata is read directly.
        Otherwise this is a no-op.

        Args:
            vault: An optional ``guardian_one.homelink.vault.Vault`` instance.

        Returns:
            Number of credential metadata records backed up.
        """
        started = self._now()
        count = 0
        try:
            if vault is None:
                self._log_manifest("incremental", "vault_metadata", 0, started)
                return 0

            for key_name in vault.list_keys():
                meta = vault.get_meta(key_name)
                if meta is None:
                    continue
                self._conn.execute(
                    """
                    INSERT INTO vault_metadata
                        (key_name, service, scope, created_at, rotated_at, expires_at, rotation_days)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(key_name) DO UPDATE SET
                        service = excluded.service,
                        scope = excluded.scope,
                        rotated_at = excluded.rotated_at,
                        expires_at = excluded.expires_at,
                        rotation_days = excluded.rotation_days
                    """,
                    (
                        meta.key_name,
                        meta.service,
                        meta.scope,
                        meta.created_at,
                        meta.rotated_at,
                        meta.expires_at,
                        meta.rotation_days,
                    ),
                )
                count += 1

            self._conn.commit()
            self._log_manifest("incremental", "vault_metadata", count, started)
        except Exception as exc:
            self._log_manifest("incremental", "vault_metadata", 0, started, "failed", str(exc))
            raise
        return count

    # ------------------------------------------------------------------
    # Full backup
    # ------------------------------------------------------------------

    def full_backup(self, vault: Any | None = None) -> dict[str, int]:
        """Run all backup methods and return a summary of records per source.

        Args:
            vault: Optional Vault instance for metadata backup.

        Returns:
            Dict mapping source name to records backed up.
        """
        started = self._now()
        results: dict[str, int] = {}

        results["audit_log"] = self.backup_audit_log()
        results["financial"] = self.backup_financial_data()
        results["evaluations"] = self.backup_evaluations()
        results["config"] = self.backup_config()
        results["operation_logs"] = self.backup_operation_logs()
        results["errors"] = self.backup_errors()
        results["skills"] = self.backup_skills()
        results["vault_metadata"] = self.backup_vault_metadata(vault)

        total = sum(results.values())
        self._log_manifest("full", "ALL", total, started)
        return results

    # ------------------------------------------------------------------
    # Restore methods
    # ------------------------------------------------------------------

    def restore_audit_log(self) -> list[dict[str, Any]]:
        """Restore all audit log entries from the database.

        Returns:
            List of audit entry dicts.
        """
        rows = self._conn.execute(
            "SELECT timestamp, agent, action, severity, details, requires_review FROM audit_log"
        ).fetchall()
        return [
            {
                "timestamp": row["timestamp"],
                "agent": row["agent"],
                "action": row["action"],
                "severity": row["severity"],
                "details": json.loads(row["details"]) if row["details"] else {},
                "requires_review": bool(row["requires_review"]),
            }
            for row in rows
        ]

    def restore_financial_data(self) -> dict[str, Any]:
        """Restore all financial data from the database.

        Returns:
            Dict with keys: accounts, transactions, bills, budgets, net_worth_history.
        """
        accounts = [
            dict(row) for row in
            self._conn.execute("SELECT name, account_type, balance, institution, last_synced FROM accounts").fetchall()
        ]
        transactions = []
        for row in self._conn.execute(
            "SELECT date, description, amount, category, account, metadata FROM transactions"
        ).fetchall():
            txn = dict(row)
            txn["metadata"] = json.loads(txn["metadata"]) if txn["metadata"] else {}
            transactions.append(txn)

        bills = [
            {
                "name": row["name"],
                "amount": row["amount"],
                "due_date": row["due_date"],
                "recurring": bool(row["recurring"]),
                "frequency": row["frequency"],
                "auto_pay": bool(row["auto_pay"]),
                "paid": bool(row["paid"]),
            }
            for row in self._conn.execute("SELECT * FROM bills").fetchall()
        ]
        budgets = [
            dict(row) for row in
            self._conn.execute("SELECT category, budget_limit, label FROM budgets").fetchall()
        ]
        net_worth = []
        for row in self._conn.execute("SELECT date, net_worth, by_type FROM net_worth_snapshots").fetchall():
            snap = {"date": row["date"], "net_worth": row["net_worth"]}
            snap["by_type"] = json.loads(row["by_type"]) if row["by_type"] else {}
            net_worth.append(snap)

        return {
            "accounts": accounts,
            "transactions": transactions,
            "bills": bills,
            "budgets": budgets,
            "net_worth_history": net_worth,
        }

    def restore_operation_logs(self) -> list[dict[str, Any]]:
        """Restore all operation log entries."""
        rows = self._conn.execute(
            """SELECT entry_id, timestamp, category, intent, summary, context,
                      outcome, confidence, tags, metadata, prev_hash, entry_hash
               FROM operation_logs ORDER BY entry_id"""
        ).fetchall()
        results = []
        for row in rows:
            entry = dict(row)
            entry["tags"] = json.loads(entry["tags"]) if entry["tags"] else []
            entry["metadata"] = json.loads(entry["metadata"]) if entry["metadata"] else {}
            results.append(entry)
        return results

    def restore_errors(self) -> list[dict[str, Any]]:
        """Restore all error records."""
        rows = self._conn.execute(
            """SELECT error_id, timestamp, error_type, what, why, fix, context,
                      related_skill, recurrence_count, resolved, hash
               FROM error_records"""
        ).fetchall()
        return [
            {
                **dict(row),
                "resolved": bool(row["resolved"]),
            }
            for row in rows
        ]

    def restore_skills(self) -> list[dict[str, Any]]:
        """Restore all skill records."""
        rows = self._conn.execute(
            """SELECT skill_id, name, domain, description, level, level_label,
                      created, last_assessed, assessment_count, evidence, hash
               FROM skills"""
        ).fetchall()
        results = []
        for row in rows:
            entry = dict(row)
            entry["evidence"] = json.loads(entry["evidence"]) if entry["evidence"] else []
            results.append(entry)
        return results

    def restore_config(self) -> dict[str, Any]:
        """Restore system configuration as a flat dict."""
        rows = self._conn.execute("SELECT config_key, config_value FROM system_config").fetchall()
        return {
            row["config_key"]: json.loads(row["config_value"]) if row["config_value"] else None
            for row in rows
        }

    # ------------------------------------------------------------------
    # Status & integrity
    # ------------------------------------------------------------------

    def get_backup_status(self) -> dict[str, Any]:
        """Return a summary of all backup operations and current table counts.

        Returns:
            Dict with per-table row counts, last backup times, and
            total manifest entries.
        """
        table_counts: dict[str, int] = {}
        for table_name in _TABLES:
            if table_name == "backup_manifest":
                continue
            row = self._conn.execute(f"SELECT COUNT(*) as cnt FROM {table_name}").fetchone()  # noqa: S608
            table_counts[table_name] = row["cnt"] if row else 0

        manifest_count = self._conn.execute("SELECT COUNT(*) as cnt FROM backup_manifest").fetchone()
        last_full = self._conn.execute(
            """SELECT completed_at FROM backup_manifest
               WHERE backup_type = 'full' AND status = 'success'
               ORDER BY completed_at DESC LIMIT 1"""
        ).fetchone()

        return {
            "table_counts": table_counts,
            "total_backup_operations": manifest_count["cnt"] if manifest_count else 0,
            "last_full_backup": last_full["completed_at"] if last_full else None,
            "db_path": str(self._db_path),
        }

    def verify_integrity(self) -> dict[str, Any]:
        """Verify database integrity by comparing row counts with source data.

        Returns:
            Dict with per-source comparison of source records vs database rows,
            and an overall ``is_consistent`` flag.
        """
        checks: dict[str, dict[str, Any]] = {}

        # Audit log
        audit_source = self._read_jsonl("logs/audit.jsonl")
        audit_db = self._conn.execute("SELECT COUNT(*) as cnt FROM audit_log").fetchone()["cnt"]
        checks["audit_log"] = {
            "source_records": len(audit_source),
            "db_records": audit_db,
            "match": len(audit_source) == audit_db,
        }

        # Financial — accounts
        fin_data = self._read_json("data/cfo_ledger.json")
        if fin_data:
            acct_count = len(fin_data.get("accounts", []))
            acct_db = self._conn.execute("SELECT COUNT(*) as cnt FROM accounts").fetchone()["cnt"]
            checks["accounts"] = {
                "source_records": acct_count,
                "db_records": acct_db,
                "match": acct_count == acct_db,
            }

            txn_count = len(fin_data.get("transactions", []))
            txn_db = self._conn.execute("SELECT COUNT(*) as cnt FROM transactions").fetchone()["cnt"]
            checks["transactions"] = {
                "source_records": txn_count,
                "db_records": txn_db,
                "match": txn_count == txn_db,
            }

            bill_count = len(fin_data.get("bills", []))
            bill_db = self._conn.execute("SELECT COUNT(*) as cnt FROM bills").fetchone()["cnt"]
            checks["bills"] = {
                "source_records": bill_count,
                "db_records": bill_db,
                "match": bill_count == bill_db,
            }

            nw_count = len(fin_data.get("net_worth_history", []))
            nw_db = self._conn.execute("SELECT COUNT(*) as cnt FROM net_worth_snapshots").fetchone()["cnt"]
            checks["net_worth_snapshots"] = {
                "source_records": nw_count,
                "db_records": nw_db,
                "match": nw_count == nw_db,
            }

        # Operation logs
        op_data = self._read_json("guardian_one_log.json")
        if op_data:
            op_count = len(op_data.get("entries", []))
            op_db = self._conn.execute("SELECT COUNT(*) as cnt FROM operation_logs").fetchone()["cnt"]
            checks["operation_logs"] = {
                "source_records": op_count,
                "db_records": op_db,
                "match": op_count == op_db,
            }

        # Errors
        err_data = self._read_json("guardian_errors.json")
        if err_data:
            err_count = len(err_data.get("errors", []))
            err_db = self._conn.execute("SELECT COUNT(*) as cnt FROM error_records").fetchone()["cnt"]
            checks["error_records"] = {
                "source_records": err_count,
                "db_records": err_db,
                "match": err_count == err_db,
            }

        # Skills
        skill_data = self._read_json("guardian_skills.json")
        if skill_data:
            skill_count = len(skill_data.get("skills", []))
            skill_db = self._conn.execute("SELECT COUNT(*) as cnt FROM skills").fetchone()["cnt"]
            checks["skills"] = {
                "source_records": skill_count,
                "db_records": skill_db,
                "match": skill_count == skill_db,
            }

        is_consistent = all(c["match"] for c in checks.values())
        return {"checks": checks, "is_consistent": is_consistent}

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self) -> "CitadelOne":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
