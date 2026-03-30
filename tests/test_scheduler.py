"""Tests for the Scheduler command handler and core logic."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from guardian_one.core.config import AgentConfig, GuardianConfig
from guardian_one.core.guardian import GuardianOne
from guardian_one.core.scheduler import Scheduler, _print_report_brief
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
    guardian = GuardianOne(config, vault_passphrase="test-pass")
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
