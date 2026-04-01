"""Tests for the Teleprompter agent — script management, practice tracking, and API."""

import json
import tempfile
from pathlib import Path

import pytest

from guardian_one.core.audit import AuditLog
from guardian_one.core.base_agent import AgentStatus
from guardian_one.core.config import AgentConfig
from guardian_one.agents.teleprompter import (
    SCRIPT_CATEGORIES,
    DEFAULT_SCRIPTS,
    PracticeSession,
    Script,
    Teleprompter,
)


def _make_audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


def _make_agent(data_dir: str | None = None) -> Teleprompter:
    d = data_dir or tempfile.mkdtemp()
    agent = Teleprompter(
        config=AgentConfig(name="teleprompter"),
        audit=_make_audit(),
        data_dir=d,
    )
    return agent


# ---- Initialization ----

class TestInitialization:
    def test_initialize_sets_idle(self):
        agent = _make_agent()
        agent.initialize()
        assert agent.status == AgentStatus.IDLE

    def test_initialize_seeds_defaults(self):
        agent = _make_agent()
        agent.initialize()
        assert len(agent._scripts) == len(DEFAULT_SCRIPTS)

    def test_initialize_creates_db_file(self):
        d = tempfile.mkdtemp()
        agent = _make_agent(data_dir=d)
        agent.initialize()
        assert (Path(d) / "teleprompter_db.json").exists()

    def test_initialize_loads_existing_db(self):
        d = tempfile.mkdtemp()
        # Create initial agent, add data, then reload
        agent1 = _make_agent(data_dir=d)
        agent1.initialize()
        agent1.create_script(
            title="Custom Script",
            category="consult",
            scenario="Test scenario",
            content="Test content",
        )
        # Second agent reads from same dir
        agent2 = _make_agent(data_dir=d)
        agent2.initialize()
        # Should have defaults + 1 custom
        assert len(agent2._scripts) == len(DEFAULT_SCRIPTS) + 1


# ---- Script Management ----

class TestScriptManagement:
    def test_list_scripts(self):
        agent = _make_agent()
        agent.initialize()
        scripts = agent.list_scripts()
        assert len(scripts) == len(DEFAULT_SCRIPTS)
        assert all(isinstance(s, dict) for s in scripts)

    def test_list_scripts_by_category(self):
        agent = _make_agent()
        agent.initialize()
        admission = agent.list_scripts(category="admission")
        assert all(s["category"] == "admission" for s in admission)

    def test_get_script(self):
        agent = _make_agent()
        agent.initialize()
        scripts = agent.list_scripts()
        first_id = scripts[0]["script_id"]
        result = agent.get_script(first_id)
        assert result is not None
        assert result["script_id"] == first_id

    def test_get_script_not_found(self):
        agent = _make_agent()
        agent.initialize()
        assert agent.get_script("nonexistent") is None

    def test_create_script(self):
        agent = _make_agent()
        agent.initialize()
        before = len(agent._scripts)
        result = agent.create_script(
            title="New Script",
            category="discharge",
            scenario="Post-surgery discharge",
            content="Hello, I'm here to go over your discharge plan...",
            tags=["discharge", "surgery"],
            scroll_speed=4,
        )
        assert result["title"] == "New Script"
        assert result["category"] == "discharge"
        assert result["scroll_speed"] == 4
        assert len(agent._scripts) == before + 1

    def test_update_script(self):
        agent = _make_agent()
        agent.initialize()
        scripts = agent.list_scripts()
        first_id = scripts[0]["script_id"]
        result = agent.update_script(first_id, {"title": "Updated Title", "scroll_speed": 5})
        assert result is not None
        assert result["title"] == "Updated Title"
        assert result["scroll_speed"] == 5

    def test_update_script_not_found(self):
        agent = _make_agent()
        agent.initialize()
        assert agent.update_script("nonexistent", {"title": "X"}) is None

    def test_update_script_protected_fields(self):
        agent = _make_agent()
        agent.initialize()
        scripts = agent.list_scripts()
        first_id = scripts[0]["script_id"]
        original_created = scripts[0]["created_at"]
        result = agent.update_script(first_id, {"created_at": "hacked"})
        assert result["created_at"] == original_created

    def test_delete_script(self):
        agent = _make_agent()
        agent.initialize()
        scripts = agent.list_scripts()
        first_id = scripts[0]["script_id"]
        before = len(agent._scripts)
        assert agent.delete_script(first_id) is True
        assert len(agent._scripts) == before - 1

    def test_delete_script_not_found(self):
        agent = _make_agent()
        agent.initialize()
        assert agent.delete_script("nonexistent") is False


# ---- AI Script Generation ----

class TestScriptGeneration:
    def test_generate_script_without_ai(self):
        """Without AI engine, generates a placeholder script."""
        agent = _make_agent()
        agent.initialize()
        before = len(agent._scripts)
        result = agent.generate_script(
            scenario="72-year-old with COPD exacerbation",
            category="admission",
        )
        assert result["ai_generated"] is True
        assert result["category"] == "admission"
        assert len(agent._scripts) == before + 1
        # Without AI, content should contain the fallback text
        assert "AI unavailable" in result["content"] or len(result["content"]) > 0


# ---- Practice Sessions ----

class TestPracticeSessions:
    def test_start_practice(self):
        agent = _make_agent()
        agent.initialize()
        scripts = agent.list_scripts()
        first_id = scripts[0]["script_id"]
        session = agent.start_practice(first_id)
        assert session is not None
        assert session["script_id"] == first_id
        assert session["completed"] is False

    def test_start_practice_invalid_script(self):
        agent = _make_agent()
        agent.initialize()
        assert agent.start_practice("nonexistent") is None

    def test_complete_practice(self):
        agent = _make_agent()
        agent.initialize()
        scripts = agent.list_scripts()
        session = agent.start_practice(scripts[0]["script_id"])
        result = agent.complete_practice(
            session_id=session["session_id"],
            duration_seconds=180,
            self_rating=4,
            notes="Good practice session",
        )
        assert result is not None
        assert result["completed"] is True
        assert result["self_rating"] == 4
        assert result["duration_seconds"] == 180

    def test_complete_practice_clamps_rating(self):
        agent = _make_agent()
        agent.initialize()
        scripts = agent.list_scripts()
        session = agent.start_practice(scripts[0]["script_id"])
        result = agent.complete_practice(
            session_id=session["session_id"],
            duration_seconds=60,
            self_rating=10,  # Should be clamped to 5
        )
        assert result["self_rating"] == 5

    def test_complete_practice_not_found(self):
        agent = _make_agent()
        agent.initialize()
        assert agent.complete_practice("nonexistent", 60, 3) is None

    def test_get_sessions(self):
        agent = _make_agent()
        agent.initialize()
        scripts = agent.list_scripts()
        # Create multiple sessions
        for _ in range(3):
            s = agent.start_practice(scripts[0]["script_id"])
            agent.complete_practice(s["session_id"], 60, 3)
        sessions = agent.get_sessions()
        assert len(sessions) == 3

    def test_get_sessions_by_script(self):
        agent = _make_agent()
        agent.initialize()
        scripts = agent.list_scripts()
        s1 = agent.start_practice(scripts[0]["script_id"])
        agent.complete_practice(s1["session_id"], 60, 3)
        s2 = agent.start_practice(scripts[1]["script_id"])
        agent.complete_practice(s2["session_id"], 60, 4)

        filtered = agent.get_sessions(script_id=scripts[0]["script_id"])
        assert len(filtered) == 1

    def test_sessions_ordered_recent_first(self):
        agent = _make_agent()
        agent.initialize()
        scripts = agent.list_scripts()
        for i in range(3):
            s = agent.start_practice(scripts[0]["script_id"])
            agent.complete_practice(s["session_id"], 60, i + 1)
        sessions = agent.get_sessions()
        # Most recent should be first
        assert sessions[0]["self_rating"] == 3


# ---- Practice Statistics ----

class TestPracticeStats:
    def test_empty_stats(self):
        agent = _make_agent()
        agent.initialize()
        stats = agent.practice_stats()
        assert stats["total_sessions"] == 0
        assert stats["average_rating"] == 0.0
        assert stats["total_practice_minutes"] == 0

    def test_stats_with_sessions(self):
        agent = _make_agent()
        agent.initialize()
        scripts = agent.list_scripts()
        for rating in [3, 4, 5]:
            s = agent.start_practice(scripts[0]["script_id"])
            agent.complete_practice(s["session_id"], 120, rating)
        stats = agent.practice_stats()
        assert stats["total_sessions"] == 3
        assert stats["average_rating"] == 4.0
        assert stats["best_rating"] == 5
        assert stats["total_practice_minutes"] == 6.0  # 3 * 120s = 360s = 6min

    def test_sessions_this_week(self):
        agent = _make_agent()
        agent.initialize()
        scripts = agent.list_scripts()
        s = agent.start_practice(scripts[0]["script_id"])
        agent.complete_practice(s["session_id"], 60, 4)
        stats = agent.practice_stats()
        assert stats["sessions_this_week"] >= 1


# ---- Advisory ----

class TestAdvisory:
    def test_get_advisory_without_ai(self):
        agent = _make_agent()
        agent.initialize()
        result = agent.get_advisory(
            scenario="Patient is anxious about new cancer diagnosis",
        )
        assert "tip_id" in result
        assert "advice" in result
        assert len(agent._tips) > 0

    def test_get_tips(self):
        agent = _make_agent()
        agent.initialize()
        agent.get_advisory(scenario="Scenario 1")
        agent.get_advisory(scenario="Scenario 2")
        tips = agent.get_tips()
        assert len(tips) == 2

    def test_get_tips_limit(self):
        agent = _make_agent()
        agent.initialize()
        for i in range(5):
            agent.get_advisory(scenario=f"Scenario {i}")
        tips = agent.get_tips(limit=3)
        assert len(tips) == 3


# ---- Agent Report ----

class TestAgentReport:
    def test_run_report(self):
        agent = _make_agent()
        agent.initialize()
        report = agent.run()
        assert report.agent_name == "teleprompter"
        assert "scripts" in report.summary.lower() or "teleprompter" in report.summary.lower()

    def test_report_snapshot(self):
        agent = _make_agent()
        agent.initialize()
        report = agent.report()
        assert report.agent_name == "teleprompter"
        assert report.data["scripts"] == len(DEFAULT_SCRIPTS)


# ---- Persistence ----

class TestPersistence:
    def test_data_survives_reload(self):
        d = tempfile.mkdtemp()
        # Session 1: create data
        a1 = _make_agent(data_dir=d)
        a1.initialize()
        a1.create_script(
            title="Persisted Script",
            category="code",
            scenario="Code blue",
            content="Activate code team...",
        )
        scripts = a1.list_scripts()
        s = a1.start_practice(scripts[0]["script_id"])
        a1.complete_practice(s["session_id"], 90, 5)

        # Session 2: reload and verify
        a2 = _make_agent(data_dir=d)
        a2.initialize()
        assert len(a2._scripts) == len(DEFAULT_SCRIPTS) + 1
        assert len(a2._sessions) == 1
        assert a2._sessions[0].self_rating == 5

    def test_db_json_structure(self):
        d = tempfile.mkdtemp()
        agent = _make_agent(data_dir=d)
        agent.initialize()
        db_path = Path(d) / "teleprompter_db.json"
        raw = json.loads(db_path.read_text())
        assert "saved_at" in raw
        assert "scripts" in raw
        assert "sessions" in raw
        assert "tips" in raw


# ---- Script Categories ----

class TestScriptCategories:
    def test_all_categories_defined(self):
        expected = {
            "admission", "discharge", "consult", "code", "handoff",
            "family", "bad_news", "informed_consent", "cross_cover", "general",
        }
        assert set(SCRIPT_CATEGORIES.keys()) == expected

    def test_default_scripts_have_valid_categories(self):
        for script_data in DEFAULT_SCRIPTS:
            assert script_data["category"] in SCRIPT_CATEGORIES


# ---- API Server ----

class TestAPIServer:
    """Test the Flask API server."""

    @pytest.fixture
    def client(self):
        d = tempfile.mkdtemp()
        agent = _make_agent(data_dir=d)
        agent.initialize()

        from guardian_one.web.teleprompter.server import create_app
        app = create_app(teleprompter_agent=agent, api_token="test-token")
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def _auth(self):
        return {"Authorization": "Bearer test-token", "Content-Type": "application/json"}

    def test_health_no_auth(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"

    def test_list_scripts(self, client):
        resp = client.get("/api/scripts", headers=self._auth())
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == len(DEFAULT_SCRIPTS)

    def test_get_script(self, client):
        resp = client.get("/api/scripts", headers=self._auth())
        scripts = resp.get_json()
        first_id = scripts[0]["script_id"]
        resp2 = client.get(f"/api/scripts/{first_id}", headers=self._auth())
        assert resp2.status_code == 200
        assert resp2.get_json()["script_id"] == first_id

    def test_create_script(self, client):
        resp = client.post("/api/scripts", headers=self._auth(), json={
            "title": "API Test Script",
            "content": "Test content",
            "category": "general",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["title"] == "API Test Script"

    def test_create_script_missing_fields(self, client):
        resp = client.post("/api/scripts", headers=self._auth(), json={
            "title": "No content",
        })
        assert resp.status_code == 400

    def test_delete_script(self, client):
        resp = client.get("/api/scripts", headers=self._auth())
        first_id = resp.get_json()[0]["script_id"]
        resp2 = client.delete(f"/api/scripts/{first_id}", headers=self._auth())
        assert resp2.status_code == 200

    def test_start_and_complete_session(self, client):
        resp = client.get("/api/scripts", headers=self._auth())
        first_id = resp.get_json()[0]["script_id"]

        # Start
        resp2 = client.post("/api/sessions/start", headers=self._auth(),
                            json={"script_id": first_id})
        assert resp2.status_code == 201
        session_id = resp2.get_json()["session_id"]

        # Complete
        resp3 = client.post("/api/sessions/complete", headers=self._auth(), json={
            "session_id": session_id,
            "duration_seconds": 120,
            "self_rating": 4,
        })
        assert resp3.status_code == 200
        assert resp3.get_json()["completed"] is True

    def test_stats(self, client):
        resp = client.get("/api/stats", headers=self._auth())
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_sessions" in data

    def test_advisory(self, client):
        resp = client.post("/api/advisory", headers=self._auth(), json={
            "scenario": "Anxious patient with new diagnosis",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "tip_id" in data

    def test_unauthorized(self, client):
        resp = client.get("/api/scripts")
        assert resp.status_code == 401

    def test_wrong_token(self, client):
        resp = client.get("/api/scripts", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 403

    def test_log_encounter(self, client):
        resp = client.get("/api/scripts", headers=self._auth())
        first_id = resp.get_json()[0]["script_id"]
        resp2 = client.post("/api/log-encounter", headers=self._auth(), json={
            "encounter_type": "admission",
            "script_id": first_id,
            "duration_seconds": 300,
            "outcome_score": 4,
        })
        assert resp2.status_code == 200
        assert resp2.get_json()["success"] is True

    def test_coach_endpoint(self, client):
        resp = client.post("/api/coach", headers=self._auth(), json={
            "current_section": "OPENING",
            "patient_tone": "anxious",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "full_advice" in data

    def test_pwa_index(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
