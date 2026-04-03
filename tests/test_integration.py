"""Cross-agent integration tests — validate multi-component flows."""

from datetime import datetime, timedelta, timezone

import pytest

from guardian_one.core.config import AgentConfig, GuardianConfig, SecurityConfig
from guardian_one.core.guardian import GuardianOne
from guardian_one.core.mediator import Proposal
from guardian_one.agents.chronos import CalendarEvent, Chronos
from guardian_one.agents.archivist import Archivist
from guardian_one.agents.cfo import Bill, CFO


@pytest.fixture
def guardian(tmp_path):
    """Boot a full GuardianOne instance with config."""
    config = GuardianConfig(
        owner="Test Owner",
        security=SecurityConfig(),
        agents={
            "chronos": AgentConfig(
                name="chronos",
                allowed_resources=["calendar", "sleep_data"],
            ),
            "cfo": AgentConfig(
                name="cfo",
                allowed_resources=["accounts", "transactions", "bills"],
            ),
            "archivist": AgentConfig(
                name="archivist",
                allowed_resources=["file_index"],
            ),
        },
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
    )
    return GuardianOne(config=config, vault_passphrase="test-passphrase-for-ci")


class TestGuardianOrchestration:
    """Test the full boot -> register -> run -> summary flow."""

    def test_register_and_run_all(self, guardian):
        chronos = Chronos(guardian.config.agents["chronos"], guardian.audit)
        cfo = CFO(guardian.config.agents["cfo"], guardian.audit,
                  data_dir=guardian.config.data_dir)
        archivist = Archivist(guardian.config.agents["archivist"], guardian.audit)

        guardian.register_agent(chronos)
        guardian.register_agent(cfo)
        guardian.register_agent(archivist)

        assert len(guardian.list_agents()) == 3
        reports = guardian.run_all()
        assert len(reports) == 3
        assert all(r.agent_name in ("chronos", "cfo", "archivist") for r in reports)

    def test_daily_summary_includes_all_agents(self, guardian):
        chronos = Chronos(guardian.config.agents["chronos"], guardian.audit)
        cfo = CFO(guardian.config.agents["cfo"], guardian.audit,
                  data_dir=guardian.config.data_dir)

        guardian.register_agent(chronos)
        guardian.register_agent(cfo)
        guardian.run_all()

        summary = guardian.daily_summary()
        assert "chronos" in summary.lower()
        assert "cfo" in summary.lower()

    def test_shutdown_audits(self, guardian):
        chronos = Chronos(guardian.config.agents["chronos"], guardian.audit)
        guardian.register_agent(chronos)

        guardian.shutdown()
        entries = guardian.audit.query(agent="guardian_one")
        shutdown_entries = [e for e in entries if "shutdown" in e.action]
        assert len(shutdown_entries) >= 1


class TestCFOChronosIntegration:
    """Test CFO data flowing into Chronos."""

    def test_cfo_bills_and_chronos_events_coexist(self, guardian):
        """Both agents can run independently in the same system."""
        chronos = Chronos(guardian.config.agents["chronos"], guardian.audit)
        cfo = CFO(guardian.config.agents["cfo"], guardian.audit,
                  data_dir=guardian.config.data_dir)

        # register_agent calls initialize(), so no extra init needed
        guardian.register_agent(chronos)
        guardian.register_agent(cfo)

        # Add data to both agents
        cfo.add_bill(Bill(
            name="Electric",
            amount=120.0,
            due_date=(datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%d"),
            recurring=True,
            frequency="monthly",
        ))

        now = datetime.now(timezone.utc)
        chronos.add_event(CalendarEvent(
            title="Bill review",
            start=now + timedelta(days=1),
            end=now + timedelta(days=1, hours=1),
        ))

        # Both agents produce valid reports
        reports = guardian.run_all()
        assert len(reports) == 2
        cfo_report = next(r for r in reports if r.agent_name == "cfo")
        assert cfo_report.status in ("ok", "idle", "running")


class TestMediatorConflictResolution:
    """Test mediator resolving real agent proposals."""

    def test_time_overlap_between_agents(self, guardian):
        now = datetime.now(timezone.utc)

        guardian.mediator.submit_proposal(Proposal(
            agent="chronos",
            action="schedule_meeting",
            resource="calendar",
            time_start=now.isoformat(),
            time_end=(now + timedelta(hours=1)).isoformat(),
            details={"title": "Team standup"},
        ))
        guardian.mediator.submit_proposal(Proposal(
            agent="cfo",
            action="financial_review",
            resource="calendar",
            time_start=(now + timedelta(minutes=30)).isoformat(),
            time_end=(now + timedelta(hours=1, minutes=30)).isoformat(),
            details={"title": "Monthly review"},
        ))

        conflicts = guardian.mediator.check_conflicts()
        assert len(conflicts) >= 1
        assert conflicts[0].conflict_type.value == "time_overlap"

    def test_no_conflict_non_overlapping_times(self, guardian):
        """Different time windows should not conflict."""
        now = datetime.now(timezone.utc)

        guardian.mediator.submit_proposal(Proposal(
            agent="chronos",
            action="morning_routine",
            resource="calendar",
            time_start=now.isoformat(),
            time_end=(now + timedelta(hours=1)).isoformat(),
        ))
        guardian.mediator.submit_proposal(Proposal(
            agent="cfo",
            action="evening_review",
            resource="accounts",
            time_start=(now + timedelta(hours=2)).isoformat(),
            time_end=(now + timedelta(hours=3)).isoformat(),
        ))

        conflicts = guardian.mediator.check_conflicts()
        assert len(conflicts) == 0


class TestAuditTrailIntegrity:
    """Verify audit trail captures actions from multiple agents."""

    def test_multi_agent_audit_trail(self, guardian):
        chronos = Chronos(guardian.config.agents["chronos"], guardian.audit)
        cfo = CFO(guardian.config.agents["cfo"], guardian.audit,
                  data_dir=guardian.config.data_dir)

        guardian.register_agent(chronos)
        guardian.register_agent(cfo)
        guardian.run_all()

        all_entries = guardian.audit.query(limit=100)
        agents_logged = {e.agent for e in all_entries}
        assert "chronos" in agents_logged
        assert "cfo" in agents_logged

    def test_audit_entries_have_timestamps(self, guardian):
        chronos = Chronos(guardian.config.agents["chronos"], guardian.audit)
        guardian.register_agent(chronos)
        guardian.run_all()

        entries = guardian.audit.query(agent="chronos", limit=5)
        for entry in entries:
            assert entry.timestamp  # non-empty ISO timestamp


class TestAccessControlBoundaries:
    """Verify agents can only access their allowed resources."""

    def _register_agents(self, guardian):
        """Register agents so their access policies are created."""
        chronos = Chronos(guardian.config.agents["chronos"], guardian.audit)
        cfo = CFO(guardian.config.agents["cfo"], guardian.audit, data_dir=guardian.config.data_dir)
        guardian.register_agent(chronos)
        guardian.register_agent(cfo)

    def test_chronos_can_access_calendar(self, guardian):
        self._register_agents(guardian)
        assert guardian.access.check("chronos", "calendar")

    def test_chronos_cannot_access_accounts(self, guardian):
        self._register_agents(guardian)
        assert not guardian.access.check("chronos", "accounts")

    def test_cfo_can_access_accounts(self, guardian):
        self._register_agents(guardian)
        assert guardian.access.check("cfo", "accounts")

    def test_cfo_cannot_access_calendar(self, guardian):
        self._register_agents(guardian)
        assert not guardian.access.check("cfo", "calendar")

    def test_owner_has_full_access(self, guardian):
        # Owner is registered as "jeremy" in _setup_access_policies
        assert guardian.access.check("jeremy", "anything")
