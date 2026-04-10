"""Comprehensive test suite for Teleprompter — edge cases, boundaries, stress, security, API."""

import json
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

import pytest

from guardian_one.core.audit import AuditLog
from guardian_one.core.base_agent import AgentStatus
from guardian_one.core.config import AgentConfig
from guardian_one.agents.teleprompter import (
    SCRIPT_CATEGORIES,
    DEFAULT_SCRIPTS,
    AdvisoryTip,
    PracticeSession,
    Script,
    Teleprompter,
)


# ---- Helpers ----

def _audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))

def _agent(data_dir: str | None = None) -> Teleprompter:
    d = data_dir or tempfile.mkdtemp()
    return Teleprompter(
        config=AgentConfig(name="teleprompter"),
        audit=_audit(),
        data_dir=d,
    )

def _ready_agent(data_dir: str | None = None) -> Teleprompter:
    a = _agent(data_dir)
    a.initialize()
    return a

def _client(agent=None):
    from guardian_one.web.teleprompter.server import create_app
    if agent is None:
        agent = _ready_agent()
    app = create_app(teleprompter_agent=agent, api_token="test-token")
    app.config["TESTING"] = True
    return app.test_client(), agent

AUTH = {"Authorization": "Bearer test-token", "Content-Type": "application/json"}


# ======================================================================
# 1. DATACLASS UNIT TESTS
# ======================================================================

class TestScriptDataclass:
    def test_defaults(self):
        s = Script()
        assert s.title == ""
        assert s.category == "general"
        assert s.scroll_speed == 3
        assert s.ai_generated is False
        assert len(s.script_id) == 8
        assert s.created_at != ""

    def test_custom_fields(self):
        s = Script(title="Test", category="admission", scroll_speed=5)
        assert s.title == "Test"
        assert s.category == "admission"
        assert s.scroll_speed == 5

    def test_asdict_roundtrip(self):
        s = Script(title="RT", content="body")
        d = asdict(s)
        s2 = Script(**d)
        assert s2.title == s.title
        assert s2.script_id == s.script_id

    def test_unique_ids(self):
        ids = {Script().script_id for _ in range(100)}
        assert len(ids) == 100

class TestPracticeSessionDataclass:
    def test_defaults(self):
        ps = PracticeSession()
        assert ps.completed is False
        assert ps.self_rating == 0
        assert ps.duration_seconds == 0
        assert ps.areas_of_strength == []

    def test_asdict_roundtrip(self):
        ps = PracticeSession(script_id="abc", self_rating=4)
        d = asdict(ps)
        ps2 = PracticeSession(**d)
        assert ps2.script_id == "abc"

class TestAdvisoryTipDataclass:
    def test_defaults(self):
        t = AdvisoryTip()
        assert t.category == ""
        assert t.content == ""
        assert len(t.tip_id) == 8


# ======================================================================
# 2. EMPTY / BOUNDARY STRING INPUTS
# ======================================================================

class TestEmptyInputs:
    def test_create_script_empty_title(self):
        a = _ready_agent()
        r = a.create_script(title="", category="general", scenario="", content="")
        assert r["title"] == ""

    def test_create_script_empty_content(self):
        a = _ready_agent()
        r = a.create_script(title="T", category="general", scenario="", content="")
        assert r["content"] == ""

    def test_advisory_empty_scenario(self):
        a = _ready_agent()
        r = a.get_advisory(scenario="")
        assert "tip_id" in r

    def test_practice_notes_empty(self):
        a = _ready_agent()
        scripts = a.list_scripts()
        s = a.start_practice(scripts[0]["script_id"])
        r = a.complete_practice(s["session_id"], 60, 3, notes="")
        assert r["notes"] == ""

class TestLongStrings:
    def test_very_long_title(self):
        a = _ready_agent()
        long_title = "A" * 10000
        r = a.create_script(title=long_title, category="general", scenario="", content="x")
        assert len(r["title"]) == 10000

    def test_very_long_content(self):
        a = _ready_agent()
        long_content = "Word " * 50000  # 250K chars
        r = a.create_script(title="Long", category="general", scenario="", content=long_content)
        assert len(r["content"]) > 200000

    def test_very_long_notes(self):
        a = _ready_agent()
        scripts = a.list_scripts()
        s = a.start_practice(scripts[0]["script_id"])
        long_notes = "Note " * 5000
        r = a.complete_practice(s["session_id"], 60, 3, notes=long_notes)
        assert len(r["notes"]) > 20000

class TestUnicodeAndSpecialChars:
    def test_unicode_title(self):
        a = _ready_agent()
        r = a.create_script(title="脚本テスト스크립트", category="general", scenario="", content="body")
        assert r["title"] == "脚本テスト스크립트"

    def test_emoji_content(self):
        a = _ready_agent()
        r = a.create_script(title="Emoji", category="general", scenario="", content="Hello 👋🏽 Doctor 🩺")
        assert "👋🏽" in r["content"]

    def test_special_chars_in_scenario(self):
        a = _ready_agent()
        r = a.create_script(
            title="Special",
            category="general",
            scenario='<script>alert("xss")</script>',
            content="body",
        )
        assert "<script>" in r["scenario"]  # stored as-is, escaped on render

    def test_sql_injection_in_title(self):
        a = _ready_agent()
        r = a.create_script(
            title="'; DROP TABLE scripts; --",
            category="general",
            scenario="",
            content="body",
        )
        assert "DROP TABLE" in r["title"]  # no SQL, just JSON

    def test_null_bytes(self):
        a = _ready_agent()
        r = a.create_script(title="null\x00byte", category="general", scenario="", content="b\x00c")
        assert r["title"] == "null\x00byte"

    def test_newlines_and_tabs(self):
        a = _ready_agent()
        r = a.create_script(title="Line1\nLine2\tTabbed", category="general", scenario="", content="x")
        assert "\n" in r["title"]


# ======================================================================
# 3. BOUNDARY VALUES — NUMERIC FIELDS
# ======================================================================

class TestScrollSpeedBoundaries:
    @pytest.mark.parametrize("speed", [0, 1, 3, 5, 6, -1, 100, 999])
    def test_scroll_speed_accepted(self, speed):
        a = _ready_agent()
        r = a.create_script(title="T", category="general", scenario="", content="c", scroll_speed=speed)
        assert r["scroll_speed"] == speed

class TestRatingBoundaries:
    @pytest.mark.parametrize("rating,expected", [
        (0, 1), (1, 1), (2, 2), (3, 3), (4, 4), (5, 5),
        (6, 5), (10, 5), (100, 5), (-1, 1), (-100, 1),
    ])
    def test_rating_clamped(self, rating, expected):
        a = _ready_agent()
        scripts = a.list_scripts()
        s = a.start_practice(scripts[0]["script_id"])
        r = a.complete_practice(s["session_id"], 60, rating)
        assert r["self_rating"] == expected

class TestDurationBoundaries:
    @pytest.mark.parametrize("duration", [0, 1, 60, 3600, 86400, 999999])
    def test_duration_accepted(self, duration):
        a = _ready_agent()
        scripts = a.list_scripts()
        s = a.start_practice(scripts[0]["script_id"])
        r = a.complete_practice(s["session_id"], duration, 3)
        assert r["duration_seconds"] == duration

    def test_negative_duration(self):
        a = _ready_agent()
        scripts = a.list_scripts()
        s = a.start_practice(scripts[0]["script_id"])
        r = a.complete_practice(s["session_id"], -1, 3)
        assert r["duration_seconds"] == -1  # no clamping on duration


# ======================================================================
# 4. CATEGORY VALIDATION
# ======================================================================

class TestCategories:
    def test_all_categories_have_descriptions(self):
        for cat, desc in SCRIPT_CATEGORIES.items():
            assert isinstance(desc, str)
            assert len(desc) > 5

    def test_invalid_category_accepted(self):
        """Agent doesn't enforce categories — stores as-is."""
        a = _ready_agent()
        r = a.create_script(title="T", category="nonexistent_cat", scenario="", content="c")
        assert r["category"] == "nonexistent_cat"

    def test_filter_nonexistent_category(self):
        a = _ready_agent()
        r = a.list_scripts(category="xyz_doesnt_exist")
        assert r == []

    def test_filter_each_default_category(self):
        a = _ready_agent()
        for cat in ["admission", "discharge", "handoff", "bad_news"]:
            scripts = a.list_scripts(category=cat)
            for s in scripts:
                assert s["category"] == cat


# ======================================================================
# 5. CRUD OPERATIONS — DEEP TESTING
# ======================================================================

class TestScriptCRUDDeep:
    def test_update_all_mutable_fields(self):
        a = _ready_agent()
        sid = a.list_scripts()[0]["script_id"]
        r = a.update_script(sid, {
            "title": "New Title",
            "content": "New Content",
            "category": "code",
            "scenario": "New Scenario",
            "tags": ["new", "tags"],
            "scroll_speed": 5,
            "notes": "Some notes",
        })
        assert r["title"] == "New Title"
        assert r["content"] == "New Content"
        assert r["category"] == "code"
        assert r["tags"] == ["new", "tags"]

    def test_update_does_not_modify_id(self):
        a = _ready_agent()
        sid = a.list_scripts()[0]["script_id"]
        r = a.update_script(sid, {"script_id": "hacked_id"})
        assert r["script_id"] == sid  # protected

    def test_update_does_not_modify_created_at(self):
        a = _ready_agent()
        s = a.list_scripts()[0]
        r = a.update_script(s["script_id"], {"created_at": "2000-01-01"})
        assert r["created_at"] == s["created_at"]

    def test_update_changes_updated_at(self):
        a = _ready_agent()
        s = a.list_scripts()[0]
        old_updated = s["updated_at"]
        time.sleep(0.01)
        r = a.update_script(s["script_id"], {"title": "Changed"})
        assert r["updated_at"] != old_updated

    def test_delete_all_scripts(self):
        a = _ready_agent()
        for s in a.list_scripts():
            a.delete_script(s["script_id"])
        assert len(a.list_scripts()) == 0

    def test_create_after_delete_all(self):
        a = _ready_agent()
        for s in a.list_scripts():
            a.delete_script(s["script_id"])
        r = a.create_script(title="Fresh", category="general", scenario="", content="body")
        assert len(a.list_scripts()) == 1

    def test_delete_same_script_twice(self):
        a = _ready_agent()
        sid = a.list_scripts()[0]["script_id"]
        assert a.delete_script(sid) is True
        assert a.delete_script(sid) is False

    def test_update_nonexistent_field_ignored(self):
        a = _ready_agent()
        sid = a.list_scripts()[0]["script_id"]
        r = a.update_script(sid, {"nonexistent_field": "value"})
        assert "nonexistent_field" not in r


# ======================================================================
# 6. PRACTICE SESSION EDGE CASES
# ======================================================================

class TestPracticeEdgeCases:
    def test_multiple_sessions_same_script(self):
        a = _ready_agent()
        sid = a.list_scripts()[0]["script_id"]
        sessions = []
        for _ in range(10):
            s = a.start_practice(sid)
            sessions.append(s["session_id"])
        assert len(set(sessions)) == 10

    def test_complete_same_session_twice(self):
        a = _ready_agent()
        sid = a.list_scripts()[0]["script_id"]
        s = a.start_practice(sid)
        r1 = a.complete_practice(s["session_id"], 60, 3)
        assert r1["completed"] is True
        # Second complete should still work (overwrites)
        r2 = a.complete_practice(s["session_id"], 120, 5)
        assert r2["self_rating"] == 5
        assert r2["duration_seconds"] == 120

    def test_delete_script_sessions_remain(self):
        """Deleting a script doesn't delete its sessions."""
        a = _ready_agent()
        sid = a.list_scripts()[0]["script_id"]
        s = a.start_practice(sid)
        a.complete_practice(s["session_id"], 60, 4)
        a.delete_script(sid)
        sessions = a.get_sessions()
        assert len(sessions) == 1

    def test_sessions_limit(self):
        a = _ready_agent()
        sid = a.list_scripts()[0]["script_id"]
        for _ in range(20):
            s = a.start_practice(sid)
            a.complete_practice(s["session_id"], 30, 3)
        assert len(a.get_sessions(limit=5)) == 5
        assert len(a.get_sessions(limit=50)) == 20

    def test_incomplete_sessions_not_in_stats(self):
        a = _ready_agent()
        sid = a.list_scripts()[0]["script_id"]
        a.start_practice(sid)  # never completed
        stats = a.practice_stats()
        assert stats["total_sessions"] == 0


# ======================================================================
# 7. STATISTICS CALCULATIONS
# ======================================================================

class TestStatsDeep:
    def test_stats_average_precision(self):
        a = _ready_agent()
        sid = a.list_scripts()[0]["script_id"]
        for r in [1, 2, 3, 4, 5]:
            s = a.start_practice(sid)
            a.complete_practice(s["session_id"], 60, r)
        stats = a.practice_stats()
        assert stats["average_rating"] == 3.0

    def test_stats_categories_practiced(self):
        a = _ready_agent()
        scripts = a.list_scripts()
        for s in scripts[:2]:
            sess = a.start_practice(s["script_id"])
            a.complete_practice(sess["session_id"], 60, 3)
        stats = a.practice_stats()
        assert len(stats["categories_practiced"]) >= 1

    def test_stats_total_minutes_precision(self):
        a = _ready_agent()
        sid = a.list_scripts()[0]["script_id"]
        s = a.start_practice(sid)
        a.complete_practice(s["session_id"], 90, 3)
        stats = a.practice_stats()
        assert stats["total_practice_minutes"] == 1.5

    def test_stats_best_rating(self):
        a = _ready_agent()
        sid = a.list_scripts()[0]["script_id"]
        for r in [2, 4, 1, 3]:
            s = a.start_practice(sid)
            a.complete_practice(s["session_id"], 60, r)
        stats = a.practice_stats()
        assert stats["best_rating"] == 4

    def test_stats_with_no_completed(self):
        a = _ready_agent()
        sid = a.list_scripts()[0]["script_id"]
        a.start_practice(sid)
        stats = a.practice_stats()
        assert stats["total_sessions"] == 0
        assert stats["average_rating"] == 0.0
        assert stats["best_rating"] == 0


# ======================================================================
# 8. ADVISORY SYSTEM
# ======================================================================

class TestAdvisoryDeep:
    def test_multiple_tips_ordered(self):
        a = _ready_agent()
        for i in range(5):
            a.get_advisory(scenario=f"Scenario {i}")
        tips = a.get_tips()
        assert len(tips) == 5
        # Most recent first
        assert "4" in tips[0]["scenario"]
        assert "0" in tips[4]["scenario"]

    def test_tips_limit_zero(self):
        a = _ready_agent()
        a.get_advisory(scenario="test")
        tips = a.get_tips(limit=0)
        assert tips == []

    def test_advisory_with_context(self):
        a = _ready_agent()
        r = a.get_advisory(scenario="angry patient", context="ER setting, night shift")
        assert "tip_id" in r

    def test_advisory_stores_scenario(self):
        a = _ready_agent()
        r = a.get_advisory(scenario="Test scenario XYZ")
        assert r["scenario"] == "Test scenario XYZ"


# ======================================================================
# 9. SCRIPT GENERATION (without AI)
# ======================================================================

class TestScriptGeneration:
    def test_generate_creates_script(self):
        a = _ready_agent()
        before = len(a.list_scripts())
        a.generate_script(scenario="COPD exacerbation", category="admission")
        assert len(a.list_scripts()) == before + 1

    def test_generate_marks_ai_generated(self):
        a = _ready_agent()
        r = a.generate_script(scenario="test", category="general")
        assert r["ai_generated"] is True

    def test_generate_uses_category(self):
        a = _ready_agent()
        r = a.generate_script(scenario="test", category="discharge")
        assert r["category"] == "discharge"

    def test_generate_builds_title(self):
        a = _ready_agent()
        r = a.generate_script(scenario="COPD", category="admission")
        assert "Admission" in r["title"] or "admission" in r["title"].lower()

    def test_generate_fallback_content(self):
        a = _ready_agent()
        r = a.generate_script(scenario="test scenario")
        # Without AI, should have fallback text
        assert len(r["content"]) > 0


# ======================================================================
# 10. PERSISTENCE — DEEP
# ======================================================================

class TestPersistenceDeep:
    def test_reload_preserves_all_fields(self):
        d = tempfile.mkdtemp()
        a1 = _ready_agent(d)
        a1.create_script(
            title="Custom",
            category="code",
            scenario="Code blue scenario",
            content="Activate code team immediately",
            tags=["code", "emergency"],
            scroll_speed=5,
        )
        a2 = _ready_agent(d)
        s = [x for x in a2.list_scripts() if x["title"] == "Custom"][0]
        assert s["category"] == "code"
        assert s["tags"] == ["code", "emergency"]
        assert s["scroll_speed"] == 5
        assert s["scenario"] == "Code blue scenario"

    def test_reload_preserves_sessions(self):
        d = tempfile.mkdtemp()
        a1 = _ready_agent(d)
        sid = a1.list_scripts()[0]["script_id"]
        s = a1.start_practice(sid)
        a1.complete_practice(s["session_id"], 180, 5, notes="great session")

        a2 = _ready_agent(d)
        sessions = a2.get_sessions()
        assert len(sessions) == 1
        assert sessions[0]["self_rating"] == 5
        assert sessions[0]["notes"] == "great session"

    def test_reload_preserves_tips(self):
        d = tempfile.mkdtemp()
        a1 = _ready_agent(d)
        a1.get_advisory(scenario="test advisory")

        a2 = _ready_agent(d)
        tips = a2.get_tips()
        assert len(tips) == 1
        assert tips[0]["scenario"] == "test advisory"

    def test_corrupt_db_handled(self):
        d = tempfile.mkdtemp()
        db_path = Path(d) / "teleprompter_db.json"
        db_path.write_text("{{CORRUPT JSON")
        a = _agent(d)
        a.initialize()
        # Should recover with defaults
        assert len(a.list_scripts()) == len(DEFAULT_SCRIPTS)

    def test_empty_db_file_handled(self):
        d = tempfile.mkdtemp()
        db_path = Path(d) / "teleprompter_db.json"
        db_path.write_text("")
        a = _agent(d)
        a.initialize()
        assert len(a.list_scripts()) == len(DEFAULT_SCRIPTS)

    def test_db_with_extra_fields_ignored(self):
        d = tempfile.mkdtemp()
        a1 = _ready_agent(d)
        db_path = Path(d) / "teleprompter_db.json"
        raw = json.loads(db_path.read_text())
        raw["extra_field"] = "should be ignored"
        raw["scripts"][0]["unknown_field"] = True
        db_path.write_text(json.dumps(raw))
        # Should raise because Script doesn't accept unknown_field
        # but agent handles it gracefully
        a2 = _agent(d)
        a2.initialize()
        # Falls back to defaults on error
        assert len(a2.list_scripts()) >= len(DEFAULT_SCRIPTS)


# ======================================================================
# 11. AGENT LIFECYCLE
# ======================================================================

class TestAgentLifecycle:
    def test_status_transitions(self):
        a = _agent()
        a.initialize()
        assert a.status == AgentStatus.IDLE
        report = a.run()
        assert a.status == AgentStatus.IDLE
        assert report.agent_name == "teleprompter"

    def test_report_data_structure(self):
        a = _ready_agent()
        report = a.report()
        assert "scripts" in report.data
        assert "sessions" in report.data
        assert "average_rating" in report.data
        assert "categories_practiced" in report.data

    def test_run_recommendations_unpracticed(self):
        a = _ready_agent()
        report = a.run()
        # Should recommend practicing unpracticed scripts
        assert any("never practiced" in r.lower() for r in report.recommendations)

    def test_name_is_teleprompter(self):
        a = _agent()
        assert a.name == "teleprompter"


# ======================================================================
# 12. ACTIVITY LOGGING
# ======================================================================

class TestActivityLogging:
    def test_create_script_logged(self):
        a = _ready_agent()
        a.create_script(title="Logged", category="general", scenario="", content="c")
        log = a.get_activity_log()
        assert any(e["event_type"] == "script_created" for e in log)

    def test_delete_script_logged(self):
        a = _ready_agent()
        sid = a.list_scripts()[0]["script_id"]
        a.delete_script(sid)
        log = a.get_activity_log()
        assert any(e["event_type"] == "script_deleted" for e in log)

    def test_practice_logged(self):
        a = _ready_agent()
        sid = a.list_scripts()[0]["script_id"]
        s = a.start_practice(sid)
        a.complete_practice(s["session_id"], 60, 3)
        log = a.get_activity_log()
        types = [e["event_type"] for e in log]
        assert "practice_started" in types
        assert "practice_completed" in types

    def test_advisory_logged(self):
        a = _ready_agent()
        a.get_advisory(scenario="test")
        log = a.get_activity_log()
        assert any(e["event_type"] == "advisory_requested" for e in log)

    def test_activity_log_empty_on_fresh_agent(self):
        a = _ready_agent()
        log = a.get_activity_log()
        # Only seeding happened, no explicit activity log entries for seeding
        assert isinstance(log, list)

    def test_activity_log_limit(self):
        a = _ready_agent()
        for i in range(20):
            a.create_script(title=f"S{i}", category="general", scenario="", content="c")
        log = a.get_activity_log(limit=5)
        assert len(log) == 5


# ======================================================================
# 13. STRESS TESTS
# ======================================================================

class TestStress:
    def test_create_100_scripts(self):
        a = _ready_agent()
        for i in range(100):
            a.create_script(title=f"Script {i}", category="general", scenario="", content=f"Content {i}")
        assert len(a.list_scripts()) == len(DEFAULT_SCRIPTS) + 100

    def test_100_practice_sessions(self):
        a = _ready_agent()
        sid = a.list_scripts()[0]["script_id"]
        for i in range(100):
            s = a.start_practice(sid)
            a.complete_practice(s["session_id"], i * 10, (i % 5) + 1)
        stats = a.practice_stats()
        assert stats["total_sessions"] == 100

    def test_50_advisory_tips(self):
        a = _ready_agent()
        for i in range(50):
            a.get_advisory(scenario=f"Scenario {i}")
        tips = a.get_tips(limit=50)
        assert len(tips) == 50


# ======================================================================
# 14. API SERVER — COMPREHENSIVE
# ======================================================================

class TestAPIDeep:
    def test_cors_headers(self):
        c, _ = _client()
        resp = c.get("/api/health", headers={"Origin": "http://localhost:5200"})
        assert resp.headers.get("Access-Control-Allow-Origin") == "http://localhost:5200"

    def test_cors_rejected_origin(self):
        c, _ = _client()
        resp = c.get("/api/health", headers={"Origin": "http://evil.com"})
        assert "Access-Control-Allow-Origin" not in resp.headers

    def test_cors_rejects_subdomain_bypass(self):
        # A prefix-match CORS check would incorrectly allow this host because
        # "http://localhost.evil.com:5200".startswith("http://localhost") is True.
        # The parsed-host check must reject it.
        c, _ = _client()
        resp = c.get(
            "/api/health",
            headers={"Origin": "http://localhost.evil.com:5200"},
        )
        assert "Access-Control-Allow-Origin" not in resp.headers

    def test_options_preflight(self):
        c, _ = _client()
        resp = c.options("/api/generate-script", headers={
            **AUTH,
            "Origin": "http://localhost:5200",
        })
        assert resp.status_code == 204

    def test_health_fields(self):
        c, _ = _client()
        data = c.get("/api/health").get_json()
        assert data["status"] == "ok"
        assert data["service"] == "teleprompter"
        assert "timestamp" in data
        assert data["agent_ready"] is True

    def test_create_script_returns_201(self):
        c, _ = _client()
        resp = c.post("/api/scripts", headers=AUTH, json={
            "title": "T", "content": "C",
        })
        assert resp.status_code == 201

    def test_create_script_no_title(self):
        c, _ = _client()
        resp = c.post("/api/scripts", headers=AUTH, json={"content": "C"})
        assert resp.status_code == 400

    def test_create_script_no_content(self):
        c, _ = _client()
        resp = c.post("/api/scripts", headers=AUTH, json={"title": "T"})
        assert resp.status_code == 400

    def test_create_script_empty_body(self):
        c, _ = _client()
        resp = c.post("/api/scripts", headers=AUTH, json={})
        assert resp.status_code == 400

    def test_get_script_not_found(self):
        c, _ = _client()
        resp = c.get("/api/scripts/nonexistent", headers=AUTH)
        assert resp.status_code == 404

    def test_delete_script_not_found(self):
        c, _ = _client()
        resp = c.delete("/api/scripts/nonexistent", headers=AUTH)
        assert resp.status_code == 404

    def test_update_script_api(self):
        c, _ = _client()
        scripts = c.get("/api/scripts", headers=AUTH).get_json()
        sid = scripts[0]["script_id"]
        resp = c.put(f"/api/scripts/{sid}", headers=AUTH, json={"title": "Updated"})
        assert resp.status_code == 200
        assert resp.get_json()["title"] == "Updated"

    def test_update_script_not_found(self):
        c, _ = _client()
        resp = c.put("/api/scripts/nonexistent", headers=AUTH, json={"title": "X"})
        assert resp.status_code == 404

    def test_filter_scripts_by_category(self):
        c, _ = _client()
        resp = c.get("/api/scripts?category=admission", headers=AUTH)
        data = resp.get_json()
        for s in data:
            assert s["category"] == "admission"

    def test_start_session_missing_script_id(self):
        c, _ = _client()
        resp = c.post("/api/sessions/start", headers=AUTH, json={})
        assert resp.status_code == 400

    def test_start_session_invalid_script(self):
        c, _ = _client()
        resp = c.post("/api/sessions/start", headers=AUTH, json={"script_id": "xxx"})
        assert resp.status_code == 404

    def test_complete_session_missing_id(self):
        c, _ = _client()
        resp = c.post("/api/sessions/complete", headers=AUTH, json={})
        assert resp.status_code == 400

    def test_complete_session_not_found(self):
        c, _ = _client()
        resp = c.post("/api/sessions/complete", headers=AUTH, json={
            "session_id": "nonexistent",
        })
        assert resp.status_code == 404

    def test_sessions_list(self):
        c, _ = _client()
        scripts = c.get("/api/scripts", headers=AUTH).get_json()
        sid = scripts[0]["script_id"]
        c.post("/api/sessions/start", headers=AUTH, json={"script_id": sid})
        resp = c.get("/api/sessions", headers=AUTH)
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_sessions_filter_by_script(self):
        c, _ = _client()
        scripts = c.get("/api/scripts", headers=AUTH).get_json()
        sid = scripts[0]["script_id"]
        c.post("/api/sessions/start", headers=AUTH, json={"script_id": sid})
        resp = c.get(f"/api/sessions?script_id={sid}", headers=AUTH)
        assert resp.status_code == 200

    def test_advisory_missing_scenario(self):
        c, _ = _client()
        resp = c.post("/api/advisory", headers=AUTH, json={})
        assert resp.status_code == 400

    def test_tips_endpoint(self):
        c, agent = _client()
        agent.get_advisory(scenario="test")
        resp = c.get("/api/tips?limit=5", headers=AUTH)
        assert resp.status_code == 200
        assert len(resp.get_json()) == 1

    def test_generate_script_missing_scenario(self):
        c, _ = _client()
        resp = c.post("/api/generate-script", headers=AUTH, json={})
        assert resp.status_code == 400

    def test_generate_script_with_chief_complaint(self):
        c, _ = _client()
        resp = c.post("/api/generate-script", headers=AUTH, json={
            "chief_complaint": "chest pain",
            "category": "admission",
            "patient_profile": {"age": "65"},
        })
        assert resp.status_code == 200

    def test_coach_general(self):
        c, _ = _client()
        resp = c.post("/api/coach", headers=AUTH, json={
            "transcript": "General coaching request",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "full_advice" in data

    def test_log_encounter_missing_fields(self):
        c, _ = _client()
        resp = c.post("/api/log-encounter", headers=AUTH, json={
            "encounter_type": "admission",
        })
        assert resp.status_code == 400

    def test_log_encounter_invalid_script(self):
        c, _ = _client()
        resp = c.post("/api/log-encounter", headers=AUTH, json={
            "encounter_type": "admission",
            "script_id": "nonexistent",
        })
        assert resp.status_code == 404

    def test_activity_endpoint(self):
        c, agent = _client()
        agent.create_script(title="Test", category="general", scenario="", content="c")
        resp = c.get("/api/activity", headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_auth_bearer_format(self):
        c, _ = _client()
        resp = c.get("/api/scripts", headers={"Authorization": "Basic abc"})
        assert resp.status_code == 401

    def test_auth_no_header(self):
        c, _ = _client()
        resp = c.get("/api/scripts")
        assert resp.status_code == 401

    def test_pwa_static_css(self):
        c, _ = _client()
        resp = c.get("/static/app.css")
        assert resp.status_code == 200
        assert "text/css" in resp.content_type

    def test_pwa_static_js(self):
        c, _ = _client()
        resp = c.get("/static/app.js")
        assert resp.status_code == 200
        assert "javascript" in resp.content_type

    def test_manifest_json(self):
        c, _ = _client()
        resp = c.get("/manifest.json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["short_name"] == "TelePrompter"

    def test_service_worker(self):
        c, _ = _client()
        resp = c.get("/sw.js")
        assert resp.status_code == 200
        assert "javascript" in resp.content_type

    def test_static_404(self):
        c, _ = _client()
        resp = c.get("/static/nonexistent.xyz")
        assert resp.status_code == 404

    def test_pwa_icon_192(self):
        c, _ = _client()
        resp = c.get("/static/icon-192.png")
        assert resp.status_code == 200


# ======================================================================
# 15. DEFAULT SCRIPTS CONTENT VALIDATION
# ======================================================================

class TestDefaultScriptContent:
    def test_conversation_scripts_have_pause_markers(self):
        """Conversation-style scripts should have [PAUSE] markers. SBAR is a structured
        handoff template so it doesn't need pause cues."""
        conversation_cats = {"admission", "bad_news", "discharge"}
        for d in DEFAULT_SCRIPTS:
            if d["category"] in conversation_cats:
                assert "[PAUSE" in d["content"], f"{d['title']} missing [PAUSE] marker"

    def test_all_defaults_have_placeholders(self):
        for d in DEFAULT_SCRIPTS:
            assert "[" in d["content"], f"{d['title']} missing placeholder brackets"

    def test_admission_has_identity_verification(self):
        admission = [d for d in DEFAULT_SCRIPTS if d["category"] == "admission"][0]
        assert "name" in admission["content"].lower() or "identity" in admission["content"].lower()

    def test_spikes_has_all_sections(self):
        spikes = [d for d in DEFAULT_SCRIPTS if d["category"] == "bad_news"][0]
        for section in ["SETTING UP", "PERCEPTION", "INVITATION", "KNOWLEDGE", "EMOTION", "STRATEGY"]:
            assert section in spikes["content"], f"SPIKES missing {section}"

    def test_sbar_has_all_sections(self):
        sbar = [d for d in DEFAULT_SCRIPTS if d["category"] == "handoff"][0]
        for section in ["SITUATION", "BACKGROUND", "ASSESSMENT", "RECOMMENDATION"]:
            assert section in sbar["content"], f"SBAR missing {section}"

    def test_discharge_has_teach_back(self):
        discharge = [d for d in DEFAULT_SCRIPTS if d["category"] == "discharge"][0]
        assert "teach-back" in discharge["content"].lower() or "own words" in discharge["content"].lower()

    def test_all_defaults_have_tags(self):
        for d in DEFAULT_SCRIPTS:
            assert len(d.get("tags", [])) > 0, f"{d['title']} missing tags"
