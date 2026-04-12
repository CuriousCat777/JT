"""GOOS Database — SQLite persistence layer for the GOOS platform.

Extends CitadelOne with GOOS-specific tables for:
- Client accounts and registration
- Onboarding state
- Varys node registrations
- Session tokens
- Tier management

Uses the same WAL-mode SQLite approach as CitadelOne for reliability.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from guardian_one.goos.client import (
    ClientRegistry,
    ClientStatus,
    ClientTier,
    GOOSClient,
    OnboardingStep,
    VarysNode,
)


_GOOS_TABLES: dict[str, str] = {
    "goos_clients": """
        CREATE TABLE IF NOT EXISTS goos_clients (
            client_id       TEXT PRIMARY KEY,
            email           TEXT UNIQUE NOT NULL,
            display_name    TEXT NOT NULL,
            tier            TEXT NOT NULL DEFAULT 'free',
            status          TEXT NOT NULL DEFAULT 'pending',
            onboarding_step TEXT NOT NULL DEFAULT 'welcome',
            password_hash   TEXT NOT NULL DEFAULT '',
            encryption_key_hash TEXT DEFAULT '',
            created_at      TEXT NOT NULL,
            verified_at     TEXT DEFAULT '',
            onboarded_at    TEXT DEFAULT '',
            agents_enabled  TEXT DEFAULT '[]',
            preferences     TEXT DEFAULT '{}'
        )
    """,
    "goos_varys_nodes": """
        CREATE TABLE IF NOT EXISTS goos_varys_nodes (
            node_id         TEXT PRIMARY KEY,
            client_id       TEXT NOT NULL REFERENCES goos_clients(client_id),
            hostname        TEXT NOT NULL,
            os_type         TEXT NOT NULL DEFAULT 'linux',
            ip_local        TEXT DEFAULT '',
            installed_at    TEXT NOT NULL,
            last_seen       TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'active',
            devices_managed INTEGER DEFAULT 0
        )
    """,
    "goos_sessions": """
        CREATE TABLE IF NOT EXISTS goos_sessions (
            session_token   TEXT PRIMARY KEY,
            client_id       TEXT NOT NULL REFERENCES goos_clients(client_id),
            created_at      TEXT NOT NULL,
            expires_at      TEXT NOT NULL,
            ip_address      TEXT DEFAULT '',
            active          INTEGER DEFAULT 1
        )
    """,
}


class GOOSDatabase:
    """SQLite persistence for GOOS platform data.

    Provides load/save operations that bridge between the in-memory
    ClientRegistry and persistent SQLite storage.

    Usage::

        db = GOOSDatabase()
        db.save_client(client)
        client = db.load_client("client-uuid")
        registry = db.load_all_into_registry()
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        default_path = Path("data") / "goos.db"
        self._db_path = Path(db_path) if db_path else default_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    def _create_tables(self) -> None:
        cur = self._conn.cursor()
        for ddl in _GOOS_TABLES.values():
            cur.execute(ddl)
        self._conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Client CRUD
    # ------------------------------------------------------------------

    def save_client(self, client: GOOSClient) -> None:
        """Insert or update a client record."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO goos_clients
                (client_id, email, display_name, tier, status, onboarding_step,
                 password_hash, encryption_key_hash, created_at, verified_at,
                 onboarded_at, agents_enabled, preferences)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client.client_id,
                client.email,
                client.display_name,
                client.tier.value,
                client.status.value,
                client.onboarding_step.value,
                client.password_hash,
                client.encryption_key_hash,
                client.created_at,
                client.verified_at,
                client.onboarded_at,
                json.dumps(client.agents_enabled),
                json.dumps(client.preferences),
            ),
        )
        # Replace persisted Varys nodes with the client's current node set
        self._conn.execute(
            "DELETE FROM goos_varys_nodes WHERE client_id = ?",
            (client.client_id,),
        )
        for node in client.varys_nodes:
            self._save_varys_node(client.client_id, node)
        self._conn.commit()

    def _save_varys_node(self, client_id: str, node: VarysNode) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO goos_varys_nodes
                (node_id, client_id, hostname, os_type, ip_local,
                 installed_at, last_seen, status, devices_managed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node.node_id, client_id, node.hostname, node.os_type,
                node.ip_local, node.installed_at, node.last_seen,
                node.status, node.devices_managed,
            ),
        )

    def load_client(self, client_id: str) -> GOOSClient | None:
        """Load a client by ID."""
        row = self._conn.execute(
            "SELECT * FROM goos_clients WHERE client_id = ?", (client_id,),
        ).fetchone()
        if not row:
            return None
        return self._row_to_client(row)

    def load_client_by_email(self, email: str) -> GOOSClient | None:
        """Load a client by email."""
        row = self._conn.execute(
            "SELECT * FROM goos_clients WHERE email = ?", (email.lower().strip(),),
        ).fetchone()
        if not row:
            return None
        return self._row_to_client(row)

    def load_all_clients(self) -> list[GOOSClient]:
        """Load all clients from the database."""
        rows = self._conn.execute("SELECT * FROM goos_clients").fetchall()
        return [self._row_to_client(row) for row in rows]

    def delete_client(self, client_id: str) -> bool:
        """Delete a client and their varys nodes."""
        self._conn.execute("DELETE FROM goos_varys_nodes WHERE client_id = ?", (client_id,))
        cur = self._conn.execute("DELETE FROM goos_clients WHERE client_id = ?", (client_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def client_count(self) -> int:
        """Return total number of registered clients."""
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM goos_clients").fetchone()
        return row["cnt"]

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def create_session(
        self, client_id: str, session_token: str, ip_address: str = "",
        ttl_hours: int = 24,
    ) -> None:
        """Store a session token."""
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        expires = (now + timedelta(hours=ttl_hours)).isoformat()
        self._conn.execute(
            """
            INSERT INTO goos_sessions (session_token, client_id, created_at, expires_at, ip_address)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_token, client_id, now.isoformat(), expires, ip_address),
        )
        self._conn.commit()

    def validate_session(self, session_token: str) -> str | None:
        """Return client_id if session is valid and not expired, else None."""
        row = self._conn.execute(
            """
            SELECT client_id, expires_at, active FROM goos_sessions
            WHERE session_token = ?
            """,
            (session_token,),
        ).fetchone()
        if not row or not row["active"]:
            return None
        if row["expires_at"] < self._now():
            return None
        return row["client_id"]

    def invalidate_session(self, session_token: str) -> None:
        """Invalidate a session token."""
        self._conn.execute(
            "UPDATE goos_sessions SET active = 0 WHERE session_token = ?",
            (session_token,),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Registry bridge
    # ------------------------------------------------------------------

    def load_into_registry(self, registry: ClientRegistry) -> int:
        """Load all clients from SQLite into an in-memory ClientRegistry.

        Returns number of clients loaded.
        """
        clients = self.load_all_clients()
        for client in clients:
            registry._clients[client.client_id] = client
            registry._email_index[client.email] = client.client_id
        return len(clients)

    def save_from_registry(self, registry: ClientRegistry) -> int:
        """Persist all clients from an in-memory ClientRegistry to SQLite.

        Returns number of clients saved.
        """
        count = 0
        for client in registry.list_clients():
            self.save_client(client)
            count += 1
        return count

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _row_to_client(self, row: sqlite3.Row) -> GOOSClient:
        """Convert a SQLite row to a GOOSClient."""
        client = GOOSClient(
            client_id=row["client_id"],
            email=row["email"],
            display_name=row["display_name"],
            tier=ClientTier(row["tier"]),
            status=ClientStatus(row["status"]),
            onboarding_step=OnboardingStep(row["onboarding_step"]),
            password_hash=row["password_hash"],
            encryption_key_hash=row["encryption_key_hash"],
            created_at=row["created_at"],
            verified_at=row["verified_at"],
            onboarded_at=row["onboarded_at"],
            agents_enabled=json.loads(row["agents_enabled"]),
            preferences=json.loads(row["preferences"]),
        )
        # Load varys nodes
        nodes = self._conn.execute(
            "SELECT * FROM goos_varys_nodes WHERE client_id = ?",
            (client.client_id,),
        ).fetchall()
        for n in nodes:
            client.varys_nodes.append(VarysNode(
                node_id=n["node_id"],
                hostname=n["hostname"],
                os_type=n["os_type"],
                installed_at=n["installed_at"],
                last_seen=n["last_seen"],
                status=n["status"],
                ip_local=n["ip_local"],
                devices_managed=n["devices_managed"],
            ))
        return client

    def close(self) -> None:
        self._conn.close()
