"""Tests for the Teleprompter SQLite database layer."""

import json
import tempfile
from pathlib import Path

import pytest

from guardian_one.agents.teleprompter_db import TeleprompterDB, SCHEMA_VERSION
from guardian_one.agents.teleprompter import (
    DEFAULT_SCRIPTS,
    Script,
    PracticeSession,
    AdvisoryTip,
    Teleprompter,
)
from guardian_one.core.audit import AuditLog
from guardian_one.core.config import AgentConfig
from dataclasses import asdict
from datetime import datetime, timezone


def _db(path: str | None = None) -> TeleprompterDB:
    p = path or str(Path(tempfile.mkdtemp()) / "test.db")
    db = TeleprompterDB(p)
    db.connect()
    return db

def _audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))

def _agent(data_dir: str | None = None) -> Teleprompter:
    d = data_dir or tempfile.mkdtemp()
    a = Teleprompter(config=AgentConfig(name="teleprompter"), audit=_audit(), data_dir=d)
    a.initialize()
    return a


# ======================================================================
# 1. CONNECTION AND SCHEMA
# ======================================================================

class TestConnection:
    def test_connect_creates_file(self):
        d = tempfile.mkdtemp()
        p = Path(d) / "test.db"
        db = TeleprompterDB(p)
        db.connect()
        assert p.exists()
        db.close()

    def test_schema_version_stored(self):
        db = _db()
        assert db._get_meta("schema_version") == str(SCHEMA_VERSION)
        db.close()

    def test_double_connect_is_safe(self):
        db = _db()
        db.connect()  # second connect
        assert db._get_meta("schema_version") == str(SCHEMA_VERSION)
        db.close()

    def test_close_and_reopen(self):
        d = tempfile.mkdtemp()
        p = str(Path(d) / "test.db")
        db = TeleprompterDB(p)
        db.connect()
        db.insert_script(asdict(Script(title="Test")))
        db.close()

        db2 = TeleprompterDB(p)
        db2.connect()
        assert db2.script_count() == 1
        db2.close()

    def test_creates_parent_dirs(self):
        d = tempfile.mkdtemp()
        p = Path(d) / "deep" / "nested" / "test.db"
        db = TeleprompterDB(p)
        db.connect()
        assert p.exists()
        db.close()


# ======================================================================
# 2. SCRIPTS CRUD
# ======================================================================

class TestScriptsCRUD:
    def test_insert_and_get(self):
        db = _db()
        s = Script(title="Test Script", category="admission", content="Hello")
        db.insert_script(asdict(s))
        result = db.get_script(s.script_id)
        assert result is not None
        assert result["title"] == "Test Script"
        assert result["category"] == "admission"
        db.close()

    def test_list_scripts(self):
        db = _db()
        for i in range(5):
            db.insert_script(asdict(Script(title=f"Script {i}")))
        assert len(db.list_scripts()) == 5
        db.close()

    def test_list_scripts_by_category(self):
        db = _db()
        db.insert_script(asdict(Script(title="A", category="admission")))
        db.insert_script(asdict(Script(title="B", category="discharge")))
        db.insert_script(asdict(Script(title="C", category="admission")))
        result = db.list_scripts(category="admission")
        assert len(result) == 2
        db.close()

    def test_update_script(self):
        db = _db()
        s = Script(title="Original")
        db.insert_script(asdict(s))
        result = db.update_script(s.script_id, {"title": "Updated", "content": "New"})
        assert result["title"] == "Updated"
        assert result["content"] == "New"
        db.close()

    def test_update_protected_fields(self):
        db = _db()
        s = Script(title="Original")
        db.insert_script(asdict(s))
        result = db.update_script(s.script_id, {"script_id": "hacked", "created_at": "hacked"})
        assert result["script_id"] == s.script_id
        assert result["created_at"] == s.created_at
        db.close()

    def test_update_nonexistent(self):
        db = _db()
        assert db.update_script("nonexistent", {"title": "X"}) is None
        db.close()

    def test_delete_script(self):
        db = _db()
        s = Script(title="To Delete")
        db.insert_script(asdict(s))
        assert db.delete_script(s.script_id) is True
        assert db.get_script(s.script_id) is None
        db.close()

    def test_delete_nonexistent(self):
        db = _db()
        assert db.delete_script("nonexistent") is False
        db.close()

    def test_script_count(self):
        db = _db()
        assert db.script_count() == 0
        for i in range(3):
            db.insert_script(asdict(Script(title=f"S{i}")))
        assert db.script_count() == 3
        db.close()

    def test_tags_preserved_as_list(self):
        db = _db()
        s = Script(title="Tagged", tags=["a", "b", "c"])
        db.insert_script(asdict(s))
        result = db.get_script(s.script_id)
        assert result["tags"] == ["a", "b", "c"]
        db.close()

    def test_boolean_preserved(self):
        db = _db()
        s = Script(title="AI", ai_generated=True)
        db.insert_script(asdict(s))
        result = db.get_script(s.script_id)
        assert result["ai_generated"] is True
        db.close()

    def test_upsert_on_insert(self):
        db = _db()
        s = Script(title="V1")
        db.insert_script(asdict(s))
        s.title = "V2"
        db.insert_script(asdict(s))
        assert db.script_count() == 1
        assert db.get_script(s.script_id)["title"] == "V2"
        db.close()


# ======================================================================
# 3. PRACTICE SESSIONS
# ======================================================================

class TestSessionsCRUD:
    def test_insert_and_get(self):
        db = _db()
        ps = PracticeSession(script_id="abc", script_title="Test")
        db.insert_session(asdict(ps))
        result = db.get_session(ps.session_id)
        assert result is not None
        assert result["script_id"] == "abc"
        db.close()

    def test_list_sessions(self):
        db = _db()
        for i in range(10):
            db.insert_session(asdict(PracticeSession(script_id="abc")))
        assert len(db.list_sessions()) == 10
        db.close()

    def test_list_sessions_by_script(self):
        db = _db()
        for _ in range(3):
            db.insert_session(asdict(PracticeSession(script_id="a")))
        for _ in range(2):
            db.insert_session(asdict(PracticeSession(script_id="b")))
        assert len(db.list_sessions(script_id="a")) == 3
        assert len(db.list_sessions(script_id="b")) == 2
        db.close()

    def test_list_sessions_limit(self):
        db = _db()
        for _ in range(20):
            db.insert_session(asdict(PracticeSession(script_id="a")))
        assert len(db.list_sessions(limit=5)) == 5
        db.close()

    def test_completed_sessions(self):
        db = _db()
        ps1 = PracticeSession(script_id="a", completed=True, self_rating=3)
        ps2 = PracticeSession(script_id="a", completed=False)
        db.insert_session(asdict(ps1))
        db.insert_session(asdict(ps2))
        completed = db.completed_sessions()
        assert len(completed) == 1
        assert completed[0]["completed"] is True
        db.close()

    def test_areas_preserved_as_lists(self):
        db = _db()
        ps = PracticeSession(
            script_id="a",
            areas_of_strength=["empathy", "clarity"],
            areas_to_improve=["pacing"],
        )
        db.insert_session(asdict(ps))
        result = db.get_session(ps.session_id)
        assert result["areas_of_strength"] == ["empathy", "clarity"]
        assert result["areas_to_improve"] == ["pacing"]
        db.close()


# ======================================================================
# 4. ADVISORY TIPS
# ======================================================================

class TestTipsCRUD:
    def test_insert_and_list(self):
        db = _db()
        t = AdvisoryTip(category="empathy", content="Be kind", scenario="test")
        db.insert_tip(asdict(t))
        tips = db.list_tips()
        assert len(tips) == 1
        assert tips[0]["content"] == "Be kind"
        db.close()

    def test_tips_ordered_by_created(self):
        db = _db()
        for i in range(5):
            t = AdvisoryTip(category="c", content=f"Tip {i}", scenario=f"S{i}")
            db.insert_tip(asdict(t))
        tips = db.list_tips()
        assert len(tips) == 5
        db.close()

    def test_tips_limit(self):
        db = _db()
        for i in range(10):
            db.insert_tip(asdict(AdvisoryTip(content=f"T{i}")))
        assert len(db.list_tips(limit=3)) == 3
        db.close()


# ======================================================================
# 5. ACTIVITY LOG
# ======================================================================

class TestActivityLog:
    def test_log_and_retrieve(self):
        db = _db()
        db.log_activity("test_event", {"key": "value"})
        log = db.get_activity_log()
        assert len(log) == 1
        assert log[0]["event_type"] == "test_event"
        assert log[0]["event_data"]["key"] == "value"
        db.close()

    def test_log_ordering(self):
        db = _db()
        for i in range(5):
            db.log_activity(f"event_{i}", {"i": i})
        log = db.get_activity_log()
        # Most recent first
        assert log[0]["event_data"]["i"] == 4
        assert log[4]["event_data"]["i"] == 0
        db.close()

    def test_log_limit(self):
        db = _db()
        for i in range(20):
            db.log_activity("event", {"i": i})
        assert len(db.get_activity_log(limit=5)) == 5
        db.close()

    def test_log_with_session_context(self):
        db = _db()
        db.log_activity("practice", {"script": "a"}, {"session_id": "s123"})
        log = db.get_activity_log()
        assert log[0]["session_context"]["session_id"] == "s123"
        db.close()


# ======================================================================
# 6. STATISTICS
# ======================================================================

class TestStats:
    def test_stats_empty(self):
        db = _db()
        stats = db.stats_summary()
        assert stats["total_sessions"] == 0
        assert stats["average_rating"] == 0.0
        db.close()

    def test_stats_with_data(self):
        db = _db()
        s = Script(title="Test", category="admission")
        db.insert_script(asdict(s))
        for r in [3, 4, 5]:
            ps = PracticeSession(
                script_id=s.script_id, completed=True,
                completed_at=datetime.now(timezone.utc).isoformat(),
                self_rating=r, duration_seconds=120,
            )
            db.insert_session(asdict(ps))
        stats = db.stats_summary()
        assert stats["total_sessions"] == 3
        assert stats["average_rating"] == 4.0
        assert stats["best_rating"] == 5
        assert stats["total_practice_minutes"] == 6.0
        db.close()

    def test_stats_sessions_this_week(self):
        db = _db()
        s = Script(title="T")
        db.insert_script(asdict(s))
        ps = PracticeSession(
            script_id=s.script_id, completed=True,
            completed_at=datetime.now(timezone.utc).isoformat(),
            self_rating=4, duration_seconds=60,
        )
        db.insert_session(asdict(ps))
        stats = db.stats_summary()
        assert stats["sessions_this_week"] >= 1
        db.close()

    def test_stats_category_breakdown(self):
        db = _db()
        s1 = Script(title="A", category="admission")
        s2 = Script(title="B", category="discharge")
        db.insert_script(asdict(s1))
        db.insert_script(asdict(s2))
        for sid in [s1.script_id, s1.script_id, s2.script_id]:
            ps = PracticeSession(
                script_id=sid, completed=True,
                completed_at=datetime.now(timezone.utc).isoformat(),
                self_rating=3, duration_seconds=60,
            )
            db.insert_session(asdict(ps))
        stats = db.stats_summary()
        assert stats["categories_practiced"]["admission"] == 2
        assert stats["categories_practiced"]["discharge"] == 1
        db.close()


# ======================================================================
# 7. JSON MIGRATION
# ======================================================================

class TestJSONMigration:
    def test_migrate_from_json(self):
        d = tempfile.mkdtemp()
        json_path = Path(d) / "teleprompter_db.json"

        # Create legacy JSON data
        json_data = {
            "saved_at": "2026-01-01T00:00:00",
            "scripts": [asdict(Script(title="Legacy Script", category="admission"))],
            "sessions": [asdict(PracticeSession(script_id="abc", completed=True, self_rating=4))],
            "tips": [asdict(AdvisoryTip(content="Legacy tip"))],
        }
        json_path.write_text(json.dumps(json_data))

        db_path = Path(d) / "test.db"
        db = TeleprompterDB(db_path)
        db.connect()
        count = db.migrate_from_json(json_path)
        assert count == 3  # 1 script + 1 session + 1 tip
        assert db.script_count() == 1
        assert db.get_activity_log() == []  # activity not migrated
        db.close()

    def test_migrate_idempotent(self):
        d = tempfile.mkdtemp()
        json_path = Path(d) / "teleprompter_db.json"
        json_data = {
            "scripts": [asdict(Script(title="S"))],
            "sessions": [],
            "tips": [],
        }
        json_path.write_text(json.dumps(json_data))

        db = TeleprompterDB(Path(d) / "test.db")
        db.connect()
        count1 = db.migrate_from_json(json_path)
        count2 = db.migrate_from_json(json_path)
        assert count1 == 1
        assert count2 == 0  # Already migrated
        db.close()

    def test_migrate_nonexistent_json(self):
        db = _db()
        count = db.migrate_from_json("/nonexistent/path.json")
        assert count == 0
        db.close()

    def test_migrate_corrupt_json(self):
        d = tempfile.mkdtemp()
        json_path = Path(d) / "bad.json"
        json_path.write_text("{{NOT VALID JSON")
        db = _db()
        count = db.migrate_from_json(json_path)
        assert count == 0
        db.close()


# ======================================================================
# 8. AGENT INTEGRATION WITH SQLITE
# ======================================================================

class TestAgentSQLiteIntegration:
    def test_agent_creates_sqlite_db(self):
        d = tempfile.mkdtemp()
        a = _agent(d)
        assert (Path(d) / "teleprompter.db").exists()

    def test_agent_data_in_sqlite(self):
        d = tempfile.mkdtemp()
        a = _agent(d)
        # Default scripts should be in SQLite
        assert a._db.script_count() == len(DEFAULT_SCRIPTS)

    def test_agent_create_persists_to_sqlite(self):
        d = tempfile.mkdtemp()
        a = _agent(d)
        a.create_script(title="SQLite Test", category="general", scenario="", content="body")
        # Check SQLite directly
        result = a._db.list_scripts()
        titles = [s["title"] for s in result]
        assert "SQLite Test" in titles

    def test_agent_practice_persists_to_sqlite(self):
        d = tempfile.mkdtemp()
        a = _agent(d)
        sid = a.list_scripts()[0]["script_id"]
        s = a.start_practice(sid)
        a.complete_practice(s["session_id"], 120, 4)
        # Check SQLite directly
        sessions = a._db.completed_sessions()
        assert len(sessions) == 1
        assert sessions[0]["self_rating"] == 4

    def test_agent_activity_in_sqlite(self):
        d = tempfile.mkdtemp()
        a = _agent(d)
        a.create_script(title="Logged", category="general", scenario="", content="c")
        log = a._db.get_activity_log()
        assert any(e["event_type"] == "script_created" for e in log)

    def test_agent_stats_from_sqlite(self):
        d = tempfile.mkdtemp()
        a = _agent(d)
        sid = a.list_scripts()[0]["script_id"]
        for r in [3, 4, 5]:
            s = a.start_practice(sid)
            a.complete_practice(s["session_id"], 60, r)
        stats = a.practice_stats()
        assert stats["total_sessions"] == 3
        assert stats["average_rating"] == 4.0

    def test_agent_reload_from_sqlite(self):
        """Data survives agent restart via SQLite."""
        d = tempfile.mkdtemp()
        a1 = _agent(d)
        a1.create_script(title="Persistent", category="code", scenario="", content="body")

        # New agent instance, same dir
        a2 = _agent(d)
        titles = [s["title"] for s in a2.list_scripts()]
        assert "Persistent" in titles

    def test_json_backup_still_written(self):
        d = tempfile.mkdtemp()
        a = _agent(d)
        a.create_script(title="Backup Test", category="general", scenario="", content="c")
        json_path = Path(d) / "teleprompter_db.json"
        assert json_path.exists()
        raw = json.loads(json_path.read_text())
        titles = [s["title"] for s in raw["scripts"]]
        assert "Backup Test" in titles

    def test_summary_file_written(self):
        d = tempfile.mkdtemp()
        a = _agent(d)
        summary_path = Path(d) / "teleprompter_summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text())
        assert "total_scripts" in summary

    def test_legacy_json_migrated_on_init(self):
        """If JSON exists but no SQLite, data migrates automatically."""
        d = tempfile.mkdtemp()
        json_path = Path(d) / "teleprompter_db.json"
        s = Script(title="Legacy", category="handoff", content="handoff text")
        json_data = {
            "saved_at": "2026-01-01",
            "scripts": [asdict(s)],
            "sessions": [],
            "tips": [],
        }
        json_path.write_text(json.dumps(json_data))

        a = _agent(d)
        # Should have legacy script + defaults
        titles = [x["title"] for x in a.list_scripts()]
        assert "Legacy" in titles


# ======================================================================
# 9. EXPORT SUMMARY
# ======================================================================

class TestExportSummary:
    def test_export_summary_structure(self):
        db = _db()
        summary = db.export_summary()
        assert "total_scripts" in summary
        assert "total_sessions" in summary
        assert "total_practice_minutes" in summary
        assert "average_rating" in summary
        assert "last_activity" in summary
        assert "categories_breakdown" in summary
        db.close()

    def test_export_summary_with_data(self):
        db = _db()
        for i in range(3):
            db.insert_script(asdict(Script(title=f"S{i}")))
        db.log_activity("test", {})
        summary = db.export_summary()
        assert summary["total_scripts"] == 3
        assert summary["last_activity"] is not None
        db.close()
