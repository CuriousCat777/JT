"""Tests for the Guardian One coordinator."""

import tempfile
from pathlib import Path

from guardian_one.core.audit import AuditLog
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig, GuardianConfig, SecurityConfig
from guardian_one.core.guardian import GuardianOne
from guardian_one.core.mediator import Mediator, Proposal
from guardian_one.agents.chronos import Chronos
from guardian_one.agents.archivist import Archivist
from guardian_one.agents.cfo import CFO


def _make_config() -> GuardianConfig:
    return GuardianConfig(
        log_dir=tempfile.mkdtemp(),
        data_dir=tempfile.mkdtemp(),
        agents={
            "chronos": AgentConfig(name="chronos", allowed_resources=["calendar"]),
            "archivist": AgentConfig(name="archivist", allowed_resources=["files"]),
            "cfo": AgentConfig(name="cfo", allowed_resources=["accounts"]),
        },
    )


def test_guardian_boot():
    guardian = GuardianOne(_make_config(), vault_passphrase="test-pass")
    assert guardian.list_agents() == []
    assert guardian.access.check("jeremy", "anything") is True


def test_register_and_run_agents():
    config = _make_config()
    guardian = GuardianOne(config, vault_passphrase="test-pass")

    guardian.register_agent(Chronos(config.agents["chronos"], guardian.audit))
    guardian.register_agent(Archivist(config.agents["archivist"], guardian.audit))
    guardian.register_agent(CFO(config.agents["cfo"], guardian.audit, data_dir=config.data_dir))

    assert set(guardian.list_agents()) == {"chronos", "archivist", "cfo"}

    reports = guardian.run_all()
    assert len(reports) == 3
    for report in reports:
        assert report.status != AgentStatus.ERROR.value


def test_run_single_agent():
    config = _make_config()
    guardian = GuardianOne(config, vault_passphrase="test-pass")
    guardian.register_agent(Chronos(config.agents["chronos"], guardian.audit))

    report = guardian.run_agent("chronos")
    assert report.agent_name == "chronos"


def test_daily_summary():
    config = _make_config()
    guardian = GuardianOne(config, vault_passphrase="test-pass")
    guardian.register_agent(Chronos(config.agents["chronos"], guardian.audit))

    summary = guardian.daily_summary()
    assert "Guardian One Daily Summary" in summary
    assert "chronos" in summary


def test_disabled_agent():
    config = _make_config()
    config.agents["chronos"].enabled = False
    guardian = GuardianOne(config, vault_passphrase="test-pass")
    guardian.register_agent(Chronos(config.agents["chronos"], guardian.audit))

    report = guardian.run_agent("chronos")
    assert report.status == AgentStatus.DISABLED.value


def test_access_control_for_agents():
    config = _make_config()
    guardian = GuardianOne(config, vault_passphrase="test-pass")
    guardian.register_agent(Chronos(config.agents["chronos"], guardian.audit))

    assert guardian.access.check("chronos", "calendar") is True
    assert guardian.access.check("chronos", "accounts") is False


def test_mediator_time_conflict():
    audit = AuditLog(log_dir=Path(tempfile.mkdtemp()))
    mediator = Mediator(audit=audit)

    mediator.submit_proposal(Proposal(
        agent="chronos", action="schedule_meeting",
        resource="calendar", time_start="2026-02-19T14:00", time_end="2026-02-19T15:00",
    ))
    mediator.submit_proposal(Proposal(
        agent="archivist", action="backup_run",
        resource="system", time_start="2026-02-19T14:30", time_end="2026-02-19T15:30",
    ))

    conflicts = mediator.check_conflicts()
    assert len(conflicts) >= 1
    # Chronos should win (higher scheduling priority)
    time_conflict = [c for c in conflicts if c.conflict_type.value == "time_overlap"]
    assert len(time_conflict) == 1
    assert time_conflict[0].resolution.value == "approve_first"


def test_guardian_shutdown():
    config = _make_config()
    guardian = GuardianOne(config, vault_passphrase="test-pass")
    guardian.register_agent(Chronos(config.agents["chronos"], guardian.audit))
    guardian.shutdown()

    entries = guardian.audit.query(agent="guardian_one")
    actions = [e.action for e in entries]
    assert "system_shutdown" in actions
