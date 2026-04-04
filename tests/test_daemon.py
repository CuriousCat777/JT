"""Tests for the DaemonRunner and health API."""

import json
import tempfile
import threading
import time
import urllib.error
import urllib.request

from guardian_one.core.config import AgentConfig, GuardianConfig
from guardian_one.core.guardian import GuardianOne
from guardian_one.core.daemon import DaemonRunner
from guardian_one.agents.chronos import Chronos
from guardian_one.agents.archivist import Archivist
from guardian_one.agents.cfo import CFO


def _make_guardian() -> GuardianOne:
    config = GuardianConfig(
        log_dir=tempfile.mkdtemp(),
        data_dir=tempfile.mkdtemp(),
        agents={
            "chronos": AgentConfig(name="chronos", schedule_interval_minutes=15, allowed_resources=["calendar"]),
            "archivist": AgentConfig(name="archivist", schedule_interval_minutes=60, allowed_resources=["files"]),
            "cfo": AgentConfig(name="cfo", schedule_interval_minutes=60, allowed_resources=["accounts"]),
        },
    )
    guardian = GuardianOne(config, vault_passphrase="test-passphrase")
    guardian.register_agent(Chronos(config.agents["chronos"], guardian.audit))
    guardian.register_agent(Archivist(config.agents["archivist"], guardian.audit))
    guardian.register_agent(CFO(config.agents["cfo"], guardian.audit, data_dir=config.data_dir))
    return guardian


# ------------------------------------------------------------------
# DaemonRunner initialization
# ------------------------------------------------------------------

def test_daemon_init():
    guardian = _make_guardian()
    runner = DaemonRunner(guardian)
    assert runner.guardian is guardian
    assert runner._health_port == 8080
    assert runner._enable_health is True
    assert not runner._stop_event.is_set()
    assert len(runner._paused) == 0


def test_daemon_init_custom_port():
    guardian = _make_guardian()
    runner = DaemonRunner(guardian, health_port=9090)
    assert runner._health_port == 9090


def test_daemon_init_no_health():
    guardian = _make_guardian()
    runner = DaemonRunner(guardian, enable_health=False)
    assert runner._enable_health is False


def test_daemon_uptime_zero_before_start():
    guardian = _make_guardian()
    runner = DaemonRunner(guardian)
    assert runner.uptime_seconds() == 0.0


# ------------------------------------------------------------------
# Health API
# ------------------------------------------------------------------

def _start_daemon_in_thread(runner: DaemonRunner) -> threading.Thread:
    """Start the daemon in a background thread and wait for it to be ready."""
    t = threading.Thread(target=runner.start, daemon=True)
    t.start()
    # Wait for health server to come up
    for _ in range(50):
        if runner._health_server is not None:
            break
        time.sleep(0.1)
    return t


def test_health_endpoint():
    guardian = _make_guardian()
    runner = DaemonRunner(guardian, health_port=0, enable_health=True)
    # Use port 0 for OS-assigned port
    t = _start_daemon_in_thread(runner)
    try:
        port = runner._health_server.server_address[1]
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5)
        data = json.loads(resp.read())
        assert data["status"] == "ok"
        assert "uptime_seconds" in data
        assert data["agents"] == 3
    finally:
        runner._stop_event.set()
        t.join(timeout=5)


def test_status_endpoint():
    guardian = _make_guardian()
    runner = DaemonRunner(guardian, health_port=0, enable_health=True)
    t = _start_daemon_in_thread(runner)
    try:
        port = runner._health_server.server_address[1]
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=5)
        data = json.loads(resp.read())
        assert data["status"] == "ok"
        assert "agents" in data
        assert "chronos" in data["agents"]
        assert "archivist" in data["agents"]
        assert "cfo" in data["agents"]
        assert "started_at" in data
        # Check agent detail fields
        chronos_info = data["agents"]["chronos"]
        assert "enabled" in chronos_info
        assert "paused" in chronos_info
        assert "interval_minutes" in chronos_info
    finally:
        runner._stop_event.set()
        t.join(timeout=5)


def test_health_404_on_unknown_path():
    guardian = _make_guardian()
    runner = DaemonRunner(guardian, health_port=0, enable_health=True)
    t = _start_daemon_in_thread(runner)
    try:
        port = runner._health_server.server_address[1]
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/unknown", timeout=5)
            assert False, "Expected 404"
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        runner._stop_event.set()
        t.join(timeout=5)


def test_daemon_no_health_server():
    guardian = _make_guardian()
    runner = DaemonRunner(guardian, enable_health=False)
    # Start and immediately stop — no health server should be created
    runner._stop_event.set()
    t = threading.Thread(target=runner.start, daemon=True)
    t.start()
    t.join(timeout=10)
    assert runner._health_server is None


# ------------------------------------------------------------------
# Job registration
# ------------------------------------------------------------------

def test_register_jobs():
    guardian = _make_guardian()
    runner = DaemonRunner(guardian)
    import schedule as sched_mod
    sched_mod.clear()
    runner._register_jobs()
    # Should have jobs for enabled agents + 2 daily CFO syncs
    assert len(sched_mod.get_jobs()) >= 3
    sched_mod.clear()
