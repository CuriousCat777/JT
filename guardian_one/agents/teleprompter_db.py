"""SQLite database layer for the Teleprompter agent.

Provides persistent, queryable storage for scripts, practice sessions,
advisory tips, and activity logs — integrated into Guardian One's data directory.

Features:
- Auto-migration from legacy JSON (teleprompter_db.json)
- Thread-safe with WAL journal mode
- Schema versioning for future migrations
- Encrypted-ready (drop-in SQLCipher if needed)
- Indexes on frequently queried columns

Tables:
    scripts          — Clinical teleprompter scripts
    practice_sessions — Practice session recordings
    advisory_tips    — AI-generated communication tips
    activity_log     — All agent events (append-only)
    meta             — Schema version and migration tracking
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scripts (
    script_id    TEXT PRIMARY KEY,
    title        TEXT NOT NULL DEFAULT '',
    category     TEXT NOT NULL DEFAULT 'general',
    scenario     TEXT NOT NULL DEFAULT '',
    content      TEXT NOT NULL DEFAULT '',
    tags         TEXT NOT NULL DEFAULT '[]',          -- JSON array
    scroll_speed INTEGER NOT NULL DEFAULT 3,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    ai_generated INTEGER NOT NULL DEFAULT 0,          -- boolean
    notes        TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_scripts_category ON scripts(category);
CREATE INDEX IF NOT EXISTS idx_scripts_created  ON scripts(created_at);

CREATE TABLE IF NOT EXISTS practice_sessions (
    session_id         TEXT PRIMARY KEY,
    script_id          TEXT NOT NULL,
    script_title       TEXT NOT NULL DEFAULT '',
    started_at         TEXT NOT NULL,
    completed_at       TEXT NOT NULL DEFAULT '',
    duration_seconds   INTEGER NOT NULL DEFAULT 0,
    self_rating        INTEGER NOT NULL DEFAULT 0,
    ai_feedback        TEXT NOT NULL DEFAULT '',
    areas_of_strength  TEXT NOT NULL DEFAULT '[]',    -- JSON array
    areas_to_improve   TEXT NOT NULL DEFAULT '[]',    -- JSON array
    notes              TEXT NOT NULL DEFAULT '',
    completed          INTEGER NOT NULL DEFAULT 0     -- boolean
);

CREATE INDEX IF NOT EXISTS idx_sessions_script    ON practice_sessions(script_id);
CREATE INDEX IF NOT EXISTS idx_sessions_started   ON practice_sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_sessions_completed ON practice_sessions(completed);

CREATE TABLE IF NOT EXISTS advisory_tips (
    tip_id     TEXT PRIMARY KEY,
    category   TEXT NOT NULL DEFAULT '',
    content    TEXT NOT NULL DEFAULT '',
    scenario   TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tips_created ON advisory_tips(created_at);

CREATE TABLE IF NOT EXISTS activity_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    event_data      TEXT NOT NULL DEFAULT '{}',       -- JSON object
    session_context TEXT NOT NULL DEFAULT '{}'         -- JSON object
);

CREATE INDEX IF NOT EXISTS idx_activity_type ON activity_log(event_type);
CREATE INDEX IF NOT EXISTS idx_activity_ts   ON activity_log(timestamp);
"""


class TeleprompterDB:
    """Thread-safe SQLite database for the Teleprompter agent."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the database and apply schema."""
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._set_meta("schema_version", str(SCHEMA_VERSION))
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _ensure_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        return self._conn  # type: ignore[return-value]

    def _set_meta(self, key: str, value: str) -> None:
        conn = self._ensure_conn()
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (key, value),
        )

    def _get_meta(self, key: str) -> str | None:
        conn = self._ensure_conn()
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    # ------------------------------------------------------------------
    # Migration from JSON
    # ------------------------------------------------------------------

    def migrate_from_json(self, json_path: str | Path) -> int:
        """Import data from the legacy teleprompter_db.json file.

        Returns the number of records imported. Skips records that already exist.
        """
        json_path = Path(json_path)
        if not json_path.exists():
            return 0

        if self._get_meta("json_migrated") == "true":
            return 0

        try:
            raw = json.loads(json_path.read_text())
        except (json.JSONDecodeError, OSError):
            return 0

        count = 0
        conn = self._ensure_conn()

        with self._lock:
            # Migrate scripts
            for s in raw.get("scripts", []):
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO scripts
                           (script_id, title, category, scenario, content, tags,
                            scroll_speed, created_at, updated_at, ai_generated, notes)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            s["script_id"], s.get("title", ""), s.get("category", "general"),
                            s.get("scenario", ""), s.get("content", ""),
                            json.dumps(s.get("tags", [])),
                            s.get("scroll_speed", 3),
                            s.get("created_at", ""), s.get("updated_at", ""),
                            1 if s.get("ai_generated") else 0,
                            s.get("notes", ""),
                        ),
                    )
                    count += 1
                except (KeyError, sqlite3.Error):
                    continue

            # Migrate sessions
            for sess in raw.get("sessions", []):
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO practice_sessions
                           (session_id, script_id, script_title, started_at,
                            completed_at, duration_seconds, self_rating, ai_feedback,
                            areas_of_strength, areas_to_improve, notes, completed)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            sess["session_id"], sess.get("script_id", ""),
                            sess.get("script_title", ""), sess.get("started_at", ""),
                            sess.get("completed_at", ""), sess.get("duration_seconds", 0),
                            sess.get("self_rating", 0), sess.get("ai_feedback", ""),
                            json.dumps(sess.get("areas_of_strength", [])),
                            json.dumps(sess.get("areas_to_improve", [])),
                            sess.get("notes", ""),
                            1 if sess.get("completed") else 0,
                        ),
                    )
                    count += 1
                except (KeyError, sqlite3.Error):
                    continue

            # Migrate tips
            for tip in raw.get("tips", []):
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO advisory_tips
                           (tip_id, category, content, scenario, created_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (
                            tip["tip_id"], tip.get("category", ""),
                            tip.get("content", ""), tip.get("scenario", ""),
                            tip.get("created_at", ""),
                        ),
                    )
                    count += 1
                except (KeyError, sqlite3.Error):
                    continue

            self._set_meta("json_migrated", "true")
            self._set_meta("json_migrated_at", datetime.now(timezone.utc).isoformat())
            self._set_meta("json_migrated_count", str(count))
            conn.commit()

        return count

    # ------------------------------------------------------------------
    # Scripts CRUD
    # ------------------------------------------------------------------

    def insert_script(self, script_dict: dict[str, Any]) -> None:
        conn = self._ensure_conn()
        with self._lock:
            conn.execute(
                """INSERT OR REPLACE INTO scripts
                   (script_id, title, category, scenario, content, tags,
                    scroll_speed, created_at, updated_at, ai_generated, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    script_dict["script_id"], script_dict["title"],
                    script_dict["category"], script_dict["scenario"],
                    script_dict["content"],
                    json.dumps(script_dict.get("tags", [])),
                    script_dict.get("scroll_speed", 3),
                    script_dict["created_at"], script_dict["updated_at"],
                    1 if script_dict.get("ai_generated") else 0,
                    script_dict.get("notes", ""),
                ),
            )
            conn.commit()

    def get_script(self, script_id: str) -> dict[str, Any] | None:
        conn = self._ensure_conn()
        row = conn.execute(
            "SELECT * FROM scripts WHERE script_id = ?", (script_id,)
        ).fetchone()
        return self._row_to_script(row) if row else None

    def list_scripts(self, category: str | None = None) -> list[dict[str, Any]]:
        conn = self._ensure_conn()
        if category:
            rows = conn.execute(
                "SELECT * FROM scripts WHERE category = ? ORDER BY created_at DESC",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM scripts ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_script(r) for r in rows]

    def update_script(self, script_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.get_script(script_id)
        if not existing:
            return None

        protected = {"script_id", "created_at"}
        for key, val in updates.items():
            if key in existing and key not in protected:
                if key == "tags" and isinstance(val, list):
                    existing[key] = val
                else:
                    existing[key] = val

        existing["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.insert_script(existing)
        return existing

    def delete_script(self, script_id: str) -> bool:
        conn = self._ensure_conn()
        with self._lock:
            cursor = conn.execute(
                "DELETE FROM scripts WHERE script_id = ?", (script_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def script_count(self) -> int:
        conn = self._ensure_conn()
        row = conn.execute("SELECT COUNT(*) as cnt FROM scripts").fetchone()
        return row["cnt"]

    @staticmethod
    def _row_to_script(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "script_id": row["script_id"],
            "title": row["title"],
            "category": row["category"],
            "scenario": row["scenario"],
            "content": row["content"],
            "tags": json.loads(row["tags"]),
            "scroll_speed": row["scroll_speed"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "ai_generated": bool(row["ai_generated"]),
            "notes": row["notes"],
        }

    # ------------------------------------------------------------------
    # Practice sessions
    # ------------------------------------------------------------------

    def insert_session(self, session_dict: dict[str, Any]) -> None:
        conn = self._ensure_conn()
        with self._lock:
            conn.execute(
                """INSERT OR REPLACE INTO practice_sessions
                   (session_id, script_id, script_title, started_at,
                    completed_at, duration_seconds, self_rating, ai_feedback,
                    areas_of_strength, areas_to_improve, notes, completed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_dict["session_id"], session_dict["script_id"],
                    session_dict.get("script_title", ""),
                    session_dict["started_at"],
                    session_dict.get("completed_at", ""),
                    session_dict.get("duration_seconds", 0),
                    session_dict.get("self_rating", 0),
                    session_dict.get("ai_feedback", ""),
                    json.dumps(session_dict.get("areas_of_strength", [])),
                    json.dumps(session_dict.get("areas_to_improve", [])),
                    session_dict.get("notes", ""),
                    1 if session_dict.get("completed") else 0,
                ),
            )
            conn.commit()

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        conn = self._ensure_conn()
        row = conn.execute(
            "SELECT * FROM practice_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        return self._row_to_session(row) if row else None

    def list_sessions(
        self,
        script_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        conn = self._ensure_conn()
        if script_id:
            rows = conn.execute(
                "SELECT * FROM practice_sessions WHERE script_id = ? "
                "ORDER BY started_at DESC LIMIT ?",
                (script_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM practice_sessions ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def completed_sessions(self) -> list[dict[str, Any]]:
        """Return all completed sessions (for stats computation)."""
        conn = self._ensure_conn()
        rows = conn.execute(
            "SELECT * FROM practice_sessions WHERE completed = 1 "
            "ORDER BY started_at DESC"
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def sessions_since(self, since_iso: str) -> list[dict[str, Any]]:
        """Return completed sessions after a given ISO timestamp."""
        conn = self._ensure_conn()
        rows = conn.execute(
            "SELECT * FROM practice_sessions "
            "WHERE completed = 1 AND completed_at > ? "
            "ORDER BY started_at DESC",
            (since_iso,),
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "session_id": row["session_id"],
            "script_id": row["script_id"],
            "script_title": row["script_title"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "duration_seconds": row["duration_seconds"],
            "self_rating": row["self_rating"],
            "ai_feedback": row["ai_feedback"],
            "areas_of_strength": json.loads(row["areas_of_strength"]),
            "areas_to_improve": json.loads(row["areas_to_improve"]),
            "notes": row["notes"],
            "completed": bool(row["completed"]),
        }

    # ------------------------------------------------------------------
    # Advisory tips
    # ------------------------------------------------------------------

    def insert_tip(self, tip_dict: dict[str, Any]) -> None:
        conn = self._ensure_conn()
        with self._lock:
            conn.execute(
                """INSERT OR REPLACE INTO advisory_tips
                   (tip_id, category, content, scenario, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    tip_dict["tip_id"], tip_dict.get("category", ""),
                    tip_dict.get("content", ""), tip_dict.get("scenario", ""),
                    tip_dict["created_at"],
                ),
            )
            conn.commit()

    def list_tips(self, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._ensure_conn()
        rows = conn.execute(
            "SELECT * FROM advisory_tips ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Activity log
    # ------------------------------------------------------------------

    def log_activity(
        self,
        event_type: str,
        event_data: dict[str, Any] | None = None,
        session_context: dict[str, Any] | None = None,
    ) -> None:
        conn = self._ensure_conn()
        with self._lock:
            conn.execute(
                """INSERT INTO activity_log (timestamp, event_type, event_data, session_context)
                   VALUES (?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    event_type,
                    json.dumps(event_data or {}),
                    json.dumps(session_context or {}),
                ),
            )
            conn.commit()

    def get_activity_log(self, limit: int = 100) -> list[dict[str, Any]]:
        conn = self._ensure_conn()
        rows = conn.execute(
            "SELECT * FROM activity_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "timestamp": r["timestamp"],
                "event_type": r["event_type"],
                "event_data": json.loads(r["event_data"]),
                "session_context": json.loads(r["session_context"]),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Aggregation queries (used by practice_stats)
    # ------------------------------------------------------------------

    def stats_summary(self) -> dict[str, Any]:
        """Compute practice statistics directly in SQL."""
        conn = self._ensure_conn()

        row = conn.execute("""
            SELECT
                COUNT(*)                              AS total_sessions,
                COALESCE(AVG(self_rating), 0.0)       AS average_rating,
                COALESCE(MAX(self_rating), 0)         AS best_rating,
                COALESCE(SUM(duration_seconds), 0) / 60.0  AS total_practice_minutes
            FROM practice_sessions
            WHERE completed = 1 AND self_rating > 0
        """).fetchone()

        # Sessions this week
        from datetime import timedelta
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        week_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM practice_sessions "
            "WHERE completed = 1 AND completed_at > ?",
            (week_ago,),
        ).fetchone()

        # Category breakdown
        cat_rows = conn.execute("""
            SELECT s.category, COUNT(*) AS cnt
            FROM practice_sessions ps
            JOIN scripts s ON ps.script_id = s.script_id
            WHERE ps.completed = 1
            GROUP BY s.category
        """).fetchall()

        return {
            "total_sessions": row["total_sessions"],
            "average_rating": round(row["average_rating"], 2),
            "best_rating": row["best_rating"],
            "total_practice_minutes": round(row["total_practice_minutes"], 2),
            "sessions_this_week": week_row["cnt"],
            "categories_practiced": {r["category"]: r["cnt"] for r in cat_rows},
        }

    # ------------------------------------------------------------------
    # Summary export (for other Guardian One agents)
    # ------------------------------------------------------------------

    def export_summary(self) -> dict[str, Any]:
        """Export a summary dict readable by other Guardian One agents."""
        stats = self.stats_summary()
        conn = self._ensure_conn()
        script_count = conn.execute("SELECT COUNT(*) AS cnt FROM scripts").fetchone()["cnt"]

        last_activity = conn.execute(
            "SELECT timestamp FROM activity_log ORDER BY id DESC LIMIT 1"
        ).fetchone()

        return {
            "total_scripts": script_count,
            "total_sessions": stats["total_sessions"],
            "total_practice_minutes": stats["total_practice_minutes"],
            "average_rating": stats["average_rating"],
            "last_activity": last_activity["timestamp"] if last_activity else None,
            "categories_breakdown": stats["categories_practiced"],
        }
