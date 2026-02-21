"""
Device Tracker - Database Models

SQLite-backed storage for all device inventory data.
"""

import sqlite3
import os
from datetime import datetime, timezone
from pathlib import Path

DB_DIR = Path.home() / ".device_tracker"
DB_PATH = DB_DIR / "devices.db"


def get_db() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS devices (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            device_type     TEXT NOT NULL DEFAULT 'unknown',
            manufacturer    TEXT DEFAULT '',
            model           TEXT DEFAULT '',
            serial_number   TEXT DEFAULT '',
            mac_address     TEXT DEFAULT '',
            ip_address      TEXT DEFAULT '',
            connection_type TEXT DEFAULT '',
            condition       TEXT NOT NULL DEFAULT 'good',
            location        TEXT DEFAULT '',
            assigned_to     TEXT DEFAULT '',
            current_use     TEXT DEFAULT '',
            notes           TEXT DEFAULT '',
            is_connected    INTEGER DEFAULT 0,
            first_seen      TEXT NOT NULL,
            last_seen       TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS usage_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id   INTEGER NOT NULL,
            event       TEXT NOT NULL,
            details     TEXT DEFAULT '',
            timestamp   TEXT NOT NULL,
            FOREIGN KEY (device_id) REFERENCES devices(id)
        );

        CREATE TABLE IF NOT EXISTS scan_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_type   TEXT NOT NULL,
            devices_found INTEGER DEFAULT 0,
            new_devices INTEGER DEFAULT 0,
            timestamp   TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Device CRUD ---

def add_device(name: str, device_type: str = "unknown", **kwargs) -> int:
    conn = get_db()
    ts = now_iso()
    fields = {
        "name": name, "device_type": device_type,
        "first_seen": ts, "last_seen": ts,
        "created_at": ts, "updated_at": ts,
    }
    fields.update({k: v for k, v in kwargs.items() if v})
    cols = ", ".join(fields.keys())
    placeholders = ", ".join(["?"] * len(fields))
    cur = conn.execute(
        f"INSERT INTO devices ({cols}) VALUES ({placeholders})",
        list(fields.values())
    )
    conn.commit()
    device_id = cur.lastrowid
    log_event(device_id, "added", f"Device '{name}' added to inventory", conn=conn)
    conn.close()
    return device_id


def update_device(device_id: int, **kwargs):
    conn = get_db()
    kwargs["updated_at"] = now_iso()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    conn.execute(
        f"UPDATE devices SET {sets} WHERE id = ?",
        list(kwargs.values()) + [device_id]
    )
    conn.commit()
    conn.close()


def get_device(device_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def find_device(mac_address: str = "", serial_number: str = "", name: str = "") -> dict | None:
    conn = get_db()
    if mac_address:
        row = conn.execute("SELECT * FROM devices WHERE mac_address = ?", (mac_address,)).fetchone()
    elif serial_number:
        row = conn.execute("SELECT * FROM devices WHERE serial_number = ?", (serial_number,)).fetchone()
    elif name:
        row = conn.execute("SELECT * FROM devices WHERE name = ?", (name,)).fetchone()
    else:
        row = None
    conn.close()
    return dict(row) if row else None


def list_devices(filter_type: str = "", connected_only: bool = False) -> list[dict]:
    conn = get_db()
    query = "SELECT * FROM devices WHERE 1=1"
    params = []
    if filter_type:
        query += " AND device_type = ?"
        params.append(filter_type)
    if connected_only:
        query += " AND is_connected = 1"
    query += " ORDER BY last_seen DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_device(device_id: int):
    conn = get_db()
    conn.execute("DELETE FROM usage_log WHERE device_id = ?", (device_id,))
    conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    conn.commit()
    conn.close()


# --- Usage Logging ---

def log_event(device_id: int, event: str, details: str = "", conn: sqlite3.Connection | None = None):
    close = False
    if conn is None:
        conn = get_db()
        close = True
    conn.execute(
        "INSERT INTO usage_log (device_id, event, details, timestamp) VALUES (?, ?, ?, ?)",
        (device_id, event, details, now_iso())
    )
    conn.commit()
    if close:
        conn.close()


def get_device_history(device_id: int, limit: int = 50) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM usage_log WHERE device_id = ? ORDER BY timestamp DESC LIMIT ?",
        (device_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Scan History ---

def log_scan(scan_type: str, devices_found: int, new_devices: int):
    conn = get_db()
    conn.execute(
        "INSERT INTO scan_history (scan_type, devices_found, new_devices, timestamp) VALUES (?, ?, ?, ?)",
        (scan_type, devices_found, new_devices, now_iso())
    )
    conn.commit()
    conn.close()


# --- Analytics ---

def get_underused_devices(days_threshold: int = 30) -> list[dict]:
    conn = get_db()
    cutoff = datetime.now(timezone.utc).isoformat()
    rows = conn.execute("""
        SELECT * FROM devices
        WHERE julianday(?) - julianday(last_seen) > ?
        ORDER BY last_seen ASC
    """, (cutoff, days_threshold)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_device_stats() -> dict:
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    connected = conn.execute("SELECT COUNT(*) FROM devices WHERE is_connected = 1").fetchone()[0]
    types = conn.execute(
        "SELECT device_type, COUNT(*) as cnt FROM devices GROUP BY device_type ORDER BY cnt DESC"
    ).fetchall()
    conditions = conn.execute(
        "SELECT condition, COUNT(*) as cnt FROM devices GROUP BY condition ORDER BY cnt DESC"
    ).fetchall()
    conn.close()
    return {
        "total_devices": total,
        "connected_now": connected,
        "disconnected": total - connected,
        "by_type": {r["device_type"]: r["cnt"] for r in types},
        "by_condition": {r["condition"]: r["cnt"] for r in conditions},
    }
