"""Tests for the Scheduler command handler and core logic."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from guardian_one.core.config import AgentConfig, GuardianConfig
from guardian_one.core.guardian import GuardianOne
from guardian_one.core.scheduler import Scheduler, _print_report_brief, _sd_notify
from guardian_one.core.base_agent import AgentReport, AgentStatus
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
# Scheduler initialization
# ------------------------------------------------------------------


def test_scheduler_init():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    assert sched.guardian is guardian
    assert len(sched._paused) == 0
    assert not sched._stop_event.is_set()


# ------------------------------------------------------------------
# Command handler tests
# ------------------------------------------------------------------


def test_handle_stop():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    assert sched._handle_command("stop") is False


def test_handle_quit():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    assert sched._handle_command("quit") is False


def test_handle_q():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    assert sched._handle_command("q") is False


def test_handle_help():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    result = sched._handle_command("help")
    assert result is True


def test_handle_status():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    result = sched._handle_command("status")
    assert result is True


def test_handle_summary():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    result = sched._handle_command("summary")
    assert result is True


def test_handle_dashboard():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    result = sched._handle_command("dashboard")
    assert result is True


def test_handle_run_single_agent():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    result = sched._handle_command("run chronos")
    assert result is True
    assert "chronos" in sched._last_run


def test_handle_run_all():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    result = sched._handle_command("run all")
    assert result is True
    assert len(sched._last_run) == 3


def test_handle_run_unknown_agent():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    result = sched._handle_command("run nonexistent")
    assert result is True


def test_handle_pause_and_resume():
    guardian = _make_guardian()
    sched = Scheduler(guardian)

    # Pause
    sched._handle_command("pause chronos")
    assert "chronos" in sched._paused

    # Verify audit entry
    entries = guardian.audit.query(agent="scheduler")
    paused_actions = [e for e in entries if "agent_paused" in e.action]
    assert len(paused_actions) >= 1

    # Resume
    sched._handle_command("resume chronos")
    assert "chronos" not in sched._paused

    resumed_actions = [e for e in guardian.audit.query(agent="scheduler") if "agent_resumed" in e.action]
    assert len(resumed_actions) >= 1


def test_handle_resume_not_paused():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    result = sched._handle_command("resume chronos")
    assert result is True  # Should handle gracefully


def test_handle_pause_unknown_agent():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    result = sched._handle_command("pause nonexistent")
    assert result is True


def test_handle_interval_change():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    result = sched._handle_command("interval chronos 30")
    assert result is True
    agent = guardian.get_agent("chronos")
    assert agent is not None
    assert agent.config.schedule_interval_minutes == 30


def test_handle_interval_invalid():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    result = sched._handle_command("interval chronos 0")
    assert result is True  # Should print error but not crash


def test_handle_interval_non_numeric():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    result = sched._handle_command("interval chronos abc")
    assert result is True  # Should print error


def test_handle_unknown_command():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    result = sched._handle_command("foobar")
    assert result is True  # Should print error but not crash


def test_handle_empty_command():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    result = sched._handle_command("")
    assert result is True


def test_handle_whitespace_command():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    result = sched._handle_command("   ")
    assert result is True


# ------------------------------------------------------------------
# Paused agents skip scheduled runs
# ------------------------------------------------------------------


def test_paused_agent_skips_run():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    sched._paused.add("chronos")
    # _run_agent_job should return immediately for paused agents
    sched._run_agent_job("chronos")
    assert "chronos" not in sched._last_run


def test_unpaused_agent_runs():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    sched._run_agent_job("chronos")
    assert "chronos" in sched._last_run


# ------------------------------------------------------------------
# Helper function
# ------------------------------------------------------------------


def test_print_report_brief():
    """Smoke test that the helper doesn't crash."""
    report = AgentReport(
        agent_name="test",
        status="idle",
        summary="test summary",
        alerts=["alert1", "alert2"],
    )
    _print_report_brief("test", report)


def test_print_report_brief_no_alerts():
    report = AgentReport(
        agent_name="test",
        status="idle",
        summary="test summary",
    )
    _print_report_brief("test", report)


# ------------------------------------------------------------------
# Error budget tests
# ------------------------------------------------------------------


def test_error_budget_resets_on_success():
    """Consecutive error count resets after a successful run."""
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    sched._consecutive_errors["chronos"] = 3
    sched._run_agent_job("chronos")
    assert sched._consecutive_errors["chronos"] == 0


def test_error_budget_increments_on_failure():
    """Consecutive error count increments when agent raises."""
    guardian = _make_guardian()
    sched = Scheduler(guardian)

    # Force the agent to fail
    with patch.object(guardian, "run_agent", side_effect=RuntimeError("boom")):
        sched._run_agent_job("chronos")

    assert sched._consecutive_errors["chronos"] == 1


def test_error_budget_auto_pauses():
    """Agent is auto-paused after exhausting error budget."""
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    sched._error_budget = 3  # lower budget for testing

    with patch.object(guardian, "run_agent", side_effect=RuntimeError("boom")):
        sched._run_agent_job("chronos")  # 1
        sched._run_agent_job("chronos")  # 2
        sched._run_agent_job("chronos")  # 3 — should auto-pause

    assert "chronos" in sched._paused
    assert sched._consecutive_errors["chronos"] == 3

    # Verify it was audited
    entries = guardian.audit.query(agent="scheduler")
    auto_paused = [e for e in entries if "auto_paused" in e.action]
    assert len(auto_paused) == 1


def test_error_counts_property():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    sched._consecutive_errors["cfo"] = 2
    assert sched.error_counts == {"cfo": 2}


def test_paused_agents_property():
    guardian = _make_guardian()
    sched = Scheduler(guardian)
    sched._paused.add("chronos")
    assert "chronos" in sched.paused_agents


# ------------------------------------------------------------------
# Daemon mode tests
# ------------------------------------------------------------------


def test_daemon_starts_and_stops():
    """Daemon mode starts, runs agents once, and shuts down on stop_event."""
    guardian = _make_guardian()
    sched = Scheduler(guardian)

    import threading

    # Set stop event after a short delay so daemon exits quickly
    def _stop_after_delay():
        import time
        time.sleep(0.5)
        sched._stop_event.set()

    stop_thread = threading.Thread(target=_stop_after_delay)
    stop_thread.start()

    # Run daemon in the main thread with health disabled (port conflict avoidance)
    sched.start_daemon(enable_health=False)
    stop_thread.join()

    # Should have run all agents at least once
    assert len(sched._last_run) >= 1

    # Should have audit entries for daemon start/stop
    entries = guardian.audit.query(agent="scheduler")
    actions = [e.action for e in entries]
    assert "daemon_started" in actions
    assert "daemon_stopped" in actions


# ------------------------------------------------------------------
# sd_notify tests
# ------------------------------------------------------------------


def test_sd_notify_no_socket():
    """sd_notify does nothing when NOTIFY_SOCKET is not set."""
    with patch.dict("os.environ", {}, clear=True):
        # Should not raise
        _sd_notify("READY=1")


def test_sd_notify_with_socket(tmp_path):
    """sd_notify sends message when NOTIFY_SOCKET is set."""
    import socket as sock_mod
    import os

    sock_path = str(tmp_path / "notify.sock")
    server = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_DGRAM)
    server.bind(sock_path)

    with patch.dict("os.environ", {"NOTIFY_SOCKET": sock_path}):
        _sd_notify("READY=1")

    data = server.recv(1024)
    server.close()
    os.unlink(sock_path)
    assert data == b"READY=1"
