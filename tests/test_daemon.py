"""Tests for GuardianDaemon — headless scheduler + health API."""

import json
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from guardian_one.core.config import AgentConfig, GuardianConfig
from guardian_one.core.guardian import GuardianOne
from guardian_one.core.daemon import GuardianDaemon
from guardian_one.core.base_agent import AgentReport, AgentStatus
from guardian_one.agents.chronos import Chronos
from guardian_one.agents.archivist import Archivist
from guardian_one.agents.cfo import CFO


def _make_guardian() -> GuardianOne:
    config = GuardianConfig(
        log_dir=tempfile.mkdtemp(),
        data_dir=tempfile.mkdtemp(),
        agents={
            "chronos": AgentConfig(name="chronos", schedule_interval_minutes=15),
            "archivist": AgentConfig(name="archivist", schedule_interval_minutes=60),
            "cfo": AgentConfig(name="cfo", schedule_interval_minutes=60),
        },
    )
    guardian = GuardianOne(config)
    guardian.register_agent(Chronos(config.agents["chronos"], guardian.audit))
    guardian.register_agent(Archivist(config.agents["archivist"], guardian.audit))
    guardian.register_agent(CFO(config.agents["cfo"], guardian.audit, data_dir=config.data_dir))
    return guardian


@pytest.fixture
def guardian():
    return _make_guardian()


@pytest.fixture
def daemon(guardian):
    return GuardianDaemon(guardian, port=0)  # port 0 won't bind in tests


# ------------------------------------------------------------------
# Initialization
# ------------------------------------------------------------------

def test_daemon_init_creates_agent_state(daemon):
    assert "chronos" in daemon._agent_state
    assert "archivist" in daemon._agent_state
    assert "cfo" in daemon._agent_state


def test_daemon_init_state_structure(daemon):
    for name, state in daemon._agent_state.items():
        assert "last_run" in state
        assert "errors" in state
        assert "runs" in state
        assert "paused" in state
        assert state["errors"] == 0
        assert state["runs"] == 0
        assert state["paused"] is False


# ------------------------------------------------------------------
# State persistence
# ------------------------------------------------------------------

def test_save_and_load_state(guardian):
    d = GuardianDaemon(guardian, port=0)
    d._agent_state["chronos"]["runs"] = 5
    d._agent_state["chronos"]["last_run"] = "2026-03-23T00:00:00+00:00"
    d._save_state()

    # Create a new daemon that should load the saved state.
    d2 = GuardianDaemon(guardian, port=0)
    assert d2._agent_state["chronos"]["runs"] == 5
    assert d2._agent_state["chronos"]["last_run"] == "2026-03-23T00:00:00+00:00"


def test_load_state_handles_corrupt_file(guardian):
    state_path = Path(guardian.config.data_dir) / "daemon_state.json"
    state_path.write_text("NOT JSON")
    d = GuardianDaemon(guardian, port=0)
    # Should initialize cleanly despite corrupt file.
    assert "chronos" in d._agent_state


# ------------------------------------------------------------------
# Agent execution
# ------------------------------------------------------------------

def test_run_agent_increments_runs(daemon):
    daemon._run_agent("chronos")
    assert daemon._agent_state["chronos"]["runs"] == 1
    assert daemon._agent_state["chronos"]["last_run"] is not None


def test_run_agent_resets_errors_on_success(daemon):
    daemon._agent_state["chronos"]["errors"] = 3
    daemon._run_agent("chronos")
    assert daemon._agent_state["chronos"]["errors"] == 0


def test_run_paused_agent_is_skipped(daemon):
    daemon._agent_state["chronos"]["paused"] = True
    daemon._run_agent("chronos")
    assert daemon._agent_state["chronos"]["runs"] == 0


def test_run_agent_handles_exception(daemon):
    daemon._guardian.run_agent = MagicMock(side_effect=RuntimeError("boom"))
    daemon._run_agent("chronos")
    assert daemon._agent_state["chronos"]["errors"] == 1
    assert daemon._agent_state["chronos"]["runs"] == 1


def test_auto_pause_after_max_failures(daemon):
    daemon._guardian.run_agent = MagicMock(side_effect=RuntimeError("fail"))
    for _ in range(5):
        daemon._run_agent("chronos")
    assert daemon._agent_state["chronos"]["paused"] is True
    assert daemon._agent_state["chronos"]["errors"] == 5


def test_no_auto_pause_below_threshold(daemon):
    daemon._guardian.run_agent = MagicMock(side_effect=RuntimeError("fail"))
    for _ in range(4):
        daemon._run_agent("chronos")
    assert daemon._agent_state["chronos"]["paused"] is False


# ------------------------------------------------------------------
# Health API
# ------------------------------------------------------------------

@pytest.fixture
def health_client(daemon):
    daemon._running = True
    daemon._start_time = time.monotonic()
    return daemon._app.test_client()


def test_health_endpoint_healthy(health_client):
    resp = health_client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "healthy"
    assert "uptime_seconds" in data
    assert "timestamp" in data


def test_health_endpoint_unhealthy(daemon):
    daemon._running = False
    daemon._start_time = time.monotonic()
    client = daemon._app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 503
    data = resp.get_json()
    assert data["status"] == "unhealthy"


def test_status_endpoint(health_client, daemon):
    daemon._agent_state["chronos"]["runs"] = 3
    resp = health_client.get("/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "agents" in data
    assert data["agents"]["chronos"]["runs"] == 3


def test_metrics_endpoint(health_client, daemon):
    daemon._agent_state["chronos"]["runs"] = 10
    daemon._agent_state["archivist"]["runs"] = 5
    daemon._agent_state["chronos"]["errors"] = 2
    resp = health_client.get("/metrics")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["agent_count"] == 3
    assert data["total_runs"] == 15
    assert data["total_errors"] == 2
    assert "uptime_seconds" in data


# ------------------------------------------------------------------
# Lifecycle
# ------------------------------------------------------------------

def test_stop_sets_running_false(daemon):
    daemon._running = True
    daemon.stop()
    assert daemon._running is False


def test_handle_signal_stops_daemon(daemon):
    daemon._running = True
    daemon._handle_signal(15, None)  # SIGTERM
    assert daemon._running is False


def test_schedule_agents_registers_jobs(daemon):
    import schedule as sched
    sched.clear()
    daemon._schedule_agents()
    assert len(sched.get_jobs()) == 3  # chronos, archivist, cfo
    sched.clear()
