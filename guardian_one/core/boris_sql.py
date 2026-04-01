"""Boris SQL Store — Self-enriching SQLite log database.

All Boris observations (connectivity checks, breach alerts, repairs,
token audits, system health) are persisted in a SQLite database that
enriches itself from cross-referencing system data.

Tables:
    events      — every observation Boris makes
    connections — MCP/service connectivity snapshots
    repairs     — component repair lifecycle
    breaches    — security breach / anomaly records
    health      — system resource snapshots (CPU, memory, disk)
    enrichments — auto-generated correlations
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'boris',
    category    TEXT NOT NULL,
    severity    TEXT NOT NULL DEFAULT 'info',
    title       TEXT NOT NULL,
    details     TEXT DEFAULT '{}',
    acknowledged INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS connections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    server_id   TEXT NOT NULL,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL,
    tools_count INTEGER DEFAULT 0,
    latency_ms  REAL DEFAULT 0,
    error       TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS repairs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    component   TEXT NOT NULL,
    issue       TEXT NOT NULL,
    severity    TEXT NOT NULL DEFAULT 'medium',
    status      TEXT NOT NULL DEFAULT 'open',
    created_at  TEXT NOT NULL,
    resolved_at TEXT DEFAULT '',
    notes       TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS breaches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    breach_type TEXT NOT NULL,
    target      TEXT NOT NULL,
    severity    TEXT NOT NULL DEFAULT 'high',
    description TEXT NOT NULL,
    evidence    TEXT DEFAULT '{}',
    resolved    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS health (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    cpu_pct     REAL DEFAULT 0,
    memory_pct  REAL DEFAULT 0,
    memory_mb   REAL DEFAULT 0,
    disk_pct    REAL DEFAULT 0,
    open_fds    INTEGER DEFAULT 0,
    py_objects  INTEGER DEFAULT 0,
    alerts      TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS enrichments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    rule            TEXT NOT NULL,
    source_events   TEXT NOT NULL DEFAULT '[]',
    conclusion      TEXT NOT NULL,
    severity        TEXT NOT NULL DEFAULT 'info',
    auto_generated  INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_events_cat ON events(category);
CREATE INDEX IF NOT EXISTS idx_events_sev ON events(severity);
CREATE INDEX IF NOT EXISTS idx_events_ts  ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_breaches_type ON breaches(breach_type);
CREATE INDEX IF NOT EXISTS idx_health_ts ON health(timestamp);
"""

# Enrichment rules: if we see pattern X in recent data, conclude Y
_ENRICHMENT_RULES = [
    {
        "rule": "repeated_disconnect",
        "description": "Same server disconnected 3+ times in 1 hour → escalate",
        "query": """
            SELECT server_id, COUNT(*) as cnt
            FROM connections
            WHERE status = 'disconnected'
              AND timestamp > datetime('now', '-1 hour')
            GROUP BY server_id
            HAVING cnt >= 3
        """,
        "severity": "high",
        "conclusion_template": "Server {server_id} disconnected {cnt}x in last hour — possible outage",
    },
    {
        "rule": "breach_cluster",
        "description": "Multiple breaches within 30 minutes → coordinated attack",
        "query": """
            SELECT breach_type, COUNT(*) as cnt
            FROM breaches
            WHERE timestamp > datetime('now', '-30 minutes')
              AND resolved = 0
            GROUP BY breach_type
            HAVING cnt >= 2
        """,
        "severity": "critical",
        "conclusion_template": "Cluster of {cnt} {breach_type} breaches in 30min — possible coordinated attack",
    },
    {
        "rule": "memory_trend",
        "description": "Memory usage above 85% for 3+ consecutive checks → leak suspected",
        "query": """
            SELECT COUNT(*) as cnt, AVG(memory_pct) as avg_mem
            FROM (
                SELECT memory_pct FROM health
                ORDER BY timestamp DESC LIMIT 5
            )
            WHERE memory_pct > 85
        """,
        "severity": "high",
        "conclusion_template": "Memory at {avg_mem:.0f}% for {cnt} consecutive checks — possible leak",
    },
    {
        "rule": "repair_backlog",
        "description": "More than 5 open repairs → system maintenance overdue",
        "query": """
            SELECT COUNT(*) as cnt
            FROM repairs
            WHERE status IN ('open', 'in_progress')
        """,
        "severity": "medium",
        "conclusion_template": "{cnt} open repairs — maintenance backlog growing",
    },
]


class BorisSQLStore:
    """Thread-safe SQLite store for all Boris telemetry.

    Self-enriches by running correlation rules against stored data
    after each write batch.
    """

    def __init__(self, db_path: Path | str) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def log_event(
        self,
        category: str,
        title: str,
        severity: str = "info",
        details: dict[str, Any] | None = None,
        source: str = "boris",
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO events (timestamp, source, category, severity, title, details) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (now, source, category, severity, title, json.dumps(details or {})),
            )
            self._conn.commit()
            return cur.lastrowid or 0

    def query_events(
        self,
        category: str | None = None,
        severity: str | None = None,
        limit: int = 100,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if category:
            clauses.append("category = ?")
            params.append(category)
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        if since:
            clauses.append("timestamp >= ?")
            params.append(since)
        where = " AND ".join(clauses) if clauses else "1=1"
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM events WHERE {where} ORDER BY timestamp DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def event_stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            by_cat = self._conn.execute(
                "SELECT category, COUNT(*) as cnt FROM events GROUP BY category"
            ).fetchall()
            by_sev = self._conn.execute(
                "SELECT severity, COUNT(*) as cnt FROM events GROUP BY severity"
            ).fetchall()
        return {
            "total": total,
            "by_category": {r["category"]: r["cnt"] for r in by_cat},
            "by_severity": {r["severity"]: r["cnt"] for r in by_sev},
        }

    # ------------------------------------------------------------------
    # Connections
    # ------------------------------------------------------------------

    def log_connection(
        self,
        server_id: str,
        name: str,
        status: str,
        tools_count: int = 0,
        latency_ms: float = 0,
        error: str = "",
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO connections (timestamp, server_id, name, status, tools_count, latency_ms, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (now, server_id, name, status, tools_count, latency_ms, error),
            )
            self._conn.commit()
            return cur.lastrowid or 0

    def connection_history(self, server_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            if server_id:
                rows = self._conn.execute(
                    "SELECT * FROM connections WHERE server_id = ? ORDER BY timestamp DESC LIMIT ?",
                    (server_id, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM connections ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Breaches
    # ------------------------------------------------------------------

    def log_breach(
        self,
        breach_type: str,
        target: str,
        description: str,
        severity: str = "high",
        evidence: dict[str, Any] | None = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO breaches (timestamp, breach_type, target, severity, description, evidence) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (now, breach_type, target, severity, description, json.dumps(evidence or {})),
            )
            self._conn.commit()
            self.log_event(
                category="breach",
                title=f"[{breach_type}] {target}: {description}",
                severity=severity,
                details=evidence,
            )
            return cur.lastrowid or 0

    def unresolved_breaches(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM breaches WHERE resolved = 0 ORDER BY timestamp DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def resolve_breach(self, breach_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE breaches SET resolved = 1 WHERE id = ?", (breach_id,)
            )
            self._conn.commit()
            return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Health snapshots
    # ------------------------------------------------------------------

    def log_health(
        self,
        cpu_pct: float,
        memory_pct: float,
        memory_mb: float,
        disk_pct: float,
        open_fds: int = 0,
        py_objects: int = 0,
        alerts: list[str] | None = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO health (timestamp, cpu_pct, memory_pct, memory_mb, disk_pct, open_fds, py_objects, alerts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (now, cpu_pct, memory_pct, memory_mb, disk_pct, open_fds, py_objects,
                 json.dumps(alerts or [])),
            )
            self._conn.commit()
            return cur.lastrowid or 0

    def health_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM health ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Repairs (SQL-backed)
    # ------------------------------------------------------------------

    def log_repair(
        self,
        component: str,
        issue: str,
        severity: str = "medium",
        status: str = "open",
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO repairs (component, issue, severity, status, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (component, issue, severity, status, now),
            )
            self._conn.commit()
            return cur.lastrowid or 0

    def resolve_repair_sql(self, repair_id: int, notes: str = "") -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.execute(
                "UPDATE repairs SET status = 'resolved', resolved_at = ?, notes = ? WHERE id = ?",
                (now, notes, repair_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def open_repairs(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM repairs WHERE status IN ('open', 'in_progress') ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Self-enrichment engine
    # ------------------------------------------------------------------

    def enrich(self) -> list[dict[str, Any]]:
        """Run all enrichment rules against current data.

        Returns list of new enrichments generated this cycle.
        """
        new_enrichments: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc).isoformat()

        for rule in _ENRICHMENT_RULES:
            try:
                with self._lock:
                    rows = self._conn.execute(rule["query"]).fetchall()
                for row in rows:
                    row_dict = dict(row)
                    conclusion = rule["conclusion_template"].format(**row_dict)

                    # Deduplicate: don't re-create the same enrichment within 1 hour
                    with self._lock:
                        existing = self._conn.execute(
                            "SELECT id FROM enrichments WHERE rule = ? AND conclusion = ? "
                            "AND timestamp > datetime('now', '-1 hour')",
                            (rule["rule"], conclusion),
                        ).fetchone()

                    if existing:
                        continue

                    with self._lock:
                        self._conn.execute(
                            "INSERT INTO enrichments (timestamp, rule, source_events, conclusion, severity) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (now, rule["rule"], json.dumps(list(row_dict.keys())),
                             conclusion, rule["severity"]),
                        )
                        self._conn.commit()

                    enrichment = {
                        "rule": rule["rule"],
                        "conclusion": conclusion,
                        "severity": rule["severity"],
                        "timestamp": now,
                    }
                    new_enrichments.append(enrichment)

            except Exception:
                continue  # Rule failure shouldn't crash the enrichment cycle

        return new_enrichments

    def recent_enrichments(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM enrichments ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Summary for Varys
    # ------------------------------------------------------------------

    def intelligence_summary(self) -> dict[str, Any]:
        """Full intelligence package for Varys consumption."""
        return {
            "events": self.event_stats(),
            "unresolved_breaches": len(self.unresolved_breaches()),
            "open_repairs": len(self.open_repairs()),
            "recent_health": self.health_history(limit=1),
            "enrichments": self.recent_enrichments(limit=5),
        }
