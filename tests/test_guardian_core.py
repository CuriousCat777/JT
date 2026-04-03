"""Unit tests for GuardianOne — the central coordinator.

Focuses on isolated unit tests of GuardianOne methods using mocks.
Cross-agent integration scenarios live in test_integration.py.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from guardian_one.core.audit import AuditLog, AuditEntry, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig, GuardianConfig, SecurityConfig
from guardian_one.core.guardian import GuardianOne
from guardian_one.core.security import AccessLevel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(tmp_path: Path) -> GuardianConfig:
    """Return a minimal GuardianConfig backed by temp directories."""
    return GuardianConfig(
        owner="Test Owner",
        security=SecurityConfig(),
        agents={},
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
    )


def _make_guardian(tmp_path: Path, **kwargs) -> GuardianOne:
    """Boot GuardianOne with safe test defaults."""
    config = _make_config(tmp_path)
    return GuardianOne(
        config=config,
        vault_passphrase="test-passphrase-for-ci",
        **kwargs,
    )


def _mock_agent(name: str, resources: list[str] | None = None) -> MagicMock:
    """Return a mock BaseAgent with the minimal interface GuardianOne needs."""
    agent = MagicMock(spec=BaseAgent)
    agent.name = name
    agent.config = AgentConfig(
        name=name,
        allowed_resources=resources or [],
    )
    agent.ai_enabled = False
    report = AgentReport(
        agent_name=name,
        status=AgentStatus.IDLE.value,
        summary=f"{name} ran ok",
    )
    agent.run.return_value = report
    agent.report.return_value = report
    return agent


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def guardian(tmp_path):
    return _make_guardian(tmp_path)


# ---------------------------------------------------------------------------
# 1. Constructor
# ---------------------------------------------------------------------------

class TestConstructor:
    def test_boots_successfully_with_passphrase(self, tmp_path):
        g = _make_guardian(tmp_path)
        assert g is not None

    def test_passphrase_from_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GUARDIAN_MASTER_PASSPHRASE", "env-passphrase")
        config = _make_config(tmp_path)
        g = GuardianOne(config=config)  # no explicit passphrase
        assert g is not None

    def test_missing_passphrase_raises_runtime_error(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GUARDIAN_MASTER_PASSPHRASE", raising=False)
        config = _make_config(tmp_path)
        with pytest.raises(RuntimeError, match="Vault passphrase required"):
            GuardianOne(config=config)

    def test_empty_passphrase_raises_runtime_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GUARDIAN_MASTER_PASSPHRASE", "")
        config = _make_config(tmp_path)
        with pytest.raises(RuntimeError, match="Vault passphrase required"):
            GuardianOne(config=config)

    def test_subsystems_created(self, guardian):
        assert guardian.audit is not None
        assert guardian.mediator is not None
        assert guardian.access is not None
        assert guardian.gateway is not None
        assert guardian.vault is not None
        assert guardian.registry is not None
        assert guardian.monitor is not None
        assert guardian.ai_engine is not None

    def test_system_boot_audit_entry_recorded(self, guardian):
        entries = guardian.audit.query(agent="guardian_one")
        boot_entries = [e for e in entries if e.action == "system_boot"]
        assert len(boot_entries) == 1

    def test_agents_dict_starts_empty(self, guardian):
        assert guardian.list_agents() == []


# ---------------------------------------------------------------------------
# 2. Access policies
# ---------------------------------------------------------------------------

class TestAccessPolicies:
    def test_jeremy_registered_as_owner(self, guardian):
        policy = guardian.access.get_policy("jeremy")
        assert policy is not None
        assert policy.level == AccessLevel.OWNER

    def test_jeremy_owner_accesses_any_resource(self, guardian):
        assert guardian.access.check("jeremy", "anything")
        assert guardian.access.check("jeremy", "vault_master")
        assert guardian.access.check("jeremy", "financial_data")

    def test_guardian_one_registered_as_guardian(self, guardian):
        policy = guardian.access.get_policy("guardian_one")
        assert policy is not None
        assert policy.level == AccessLevel.GUARDIAN

    def test_mentor_registered_with_restricted_resources(self, guardian):
        policy = guardian.access.get_policy("mentor")
        assert policy is not None
        assert policy.level == AccessLevel.MENTOR
        assert "audit_log" in policy.allowed_resources
        assert "reports" in policy.allowed_resources

    def test_unknown_identity_denied(self, guardian):
        assert not guardian.access.check("hacker", "calendar")

    def test_default_identities_registered(self, guardian):
        identities = guardian.access.list_identities()
        assert "jeremy" in identities
        assert "guardian_one" in identities
        assert "mentor" in identities


# ---------------------------------------------------------------------------
# 3. register_agent
# ---------------------------------------------------------------------------

class TestRegisterAgent:
    def test_register_single_agent(self, guardian):
        agent = _mock_agent("chronos", ["calendar"])
        guardian.register_agent(agent)
        assert "chronos" in guardian.list_agents()

    def test_register_calls_initialize(self, guardian):
        agent = _mock_agent("cfo", ["accounts"])
        guardian.register_agent(agent)
        agent.initialize.assert_called_once()

    def test_register_injects_ai_engine(self, guardian):
        agent = _mock_agent("archivist")
        guardian.register_agent(agent)
        agent.set_ai_engine.assert_called_once_with(guardian.ai_engine)

    def test_register_creates_access_policy(self, guardian):
        agent = _mock_agent("doordash", ["meal_orders"])
        guardian.register_agent(agent)
        policy = guardian.access.get_policy("doordash")
        assert policy is not None
        assert policy.level == AccessLevel.AGENT
        assert "meal_orders" in policy.allowed_resources

    def test_register_duplicate_agent_raises_value_error(self, guardian):
        agent = _mock_agent("chronos")
        guardian.register_agent(agent)
        with pytest.raises(ValueError, match="already registered"):
            guardian.register_agent(agent)

    def test_register_logs_registration_and_initialization(self, guardian):
        agent = _mock_agent("archivist")
        guardian.register_agent(agent)
        entries = guardian.audit.query(agent="guardian_one")
        actions = [e.action for e in entries]
        assert any("agent_registered:archivist" in a for a in actions)
        assert any("agent_initialized:archivist" in a for a in actions)

    def test_register_multiple_agents(self, guardian):
        for name in ("chronos", "cfo", "archivist"):
            guardian.register_agent(_mock_agent(name))
        assert set(guardian.list_agents()) == {"chronos", "cfo", "archivist"}

    def test_get_agent_returns_registered(self, guardian):
        agent = _mock_agent("cfo")
        guardian.register_agent(agent)
        assert guardian.get_agent("cfo") is agent

    def test_get_agent_returns_none_for_unknown(self, guardian):
        assert guardian.get_agent("nonexistent") is None


# ---------------------------------------------------------------------------
# 4. run_all / run_agent
# ---------------------------------------------------------------------------

class TestRunAll:
    def test_run_all_returns_report_per_agent(self, guardian):
        for name in ("chronos", "cfo"):
            guardian.register_agent(_mock_agent(name))
        reports = guardian.run_all()
        assert len(reports) == 2
        names = {r.agent_name for r in reports}
        assert names == {"chronos", "cfo"}

    def test_run_all_empty_returns_empty_list(self, guardian):
        reports = guardian.run_all()
        assert reports == []

    def test_run_all_agent_exception_becomes_error_report(self, guardian):
        good = _mock_agent("cfo")
        bad = _mock_agent("crasher")
        bad.run.side_effect = RuntimeError("API unreachable")
        bad.config.enabled = True
        guardian.register_agent(good)
        guardian.register_agent(bad)

        reports = guardian.run_all()
        assert len(reports) == 2
        error_report = next(r for r in reports if r.agent_name == "crasher")
        assert error_report.status == AgentStatus.ERROR.value
        assert "API unreachable" in error_report.summary

    def test_run_all_exception_does_not_stop_other_agents(self, guardian):
        bad = _mock_agent("crasher")
        bad.run.side_effect = Exception("boom")
        bad.config.enabled = True
        good = _mock_agent("cfo")
        guardian.register_agent(bad)
        guardian.register_agent(good)

        reports = guardian.run_all()
        cfo_report = next(r for r in reports if r.agent_name == "cfo")
        assert cfo_report.status == AgentStatus.IDLE.value

    def test_run_all_disabled_agent_skipped(self, guardian):
        agent = _mock_agent("disabled_agent")
        agent.config.enabled = False
        guardian.register_agent(agent)
        reports = guardian.run_all()
        assert len(reports) == 1
        assert reports[0].status == AgentStatus.DISABLED.value
        agent.run.assert_not_called()

    def test_run_all_errors_logged_to_audit(self, guardian):
        bad = _mock_agent("crasher")
        bad.run.side_effect = ValueError("crash!")
        bad.config.enabled = True
        guardian.register_agent(bad)
        guardian.run_all()
        entries = guardian.audit.query(agent="guardian_one", severity=Severity.ERROR)
        assert any("run_error:crasher" in e.action for e in entries)

    def test_run_agent_unknown_name_raises_key_error(self, guardian):
        with pytest.raises(KeyError):
            guardian.run_agent("nonexistent")


# ---------------------------------------------------------------------------
# 5. daily_summary
# ---------------------------------------------------------------------------

class TestDailySummary:
    def test_summary_contains_owner(self, guardian):
        summary = guardian.daily_summary()
        assert "Test Owner" in summary

    def test_summary_contains_header(self, guardian):
        summary = guardian.daily_summary()
        assert "Guardian One Daily Summary" in summary

    def test_summary_lists_registered_agents(self, guardian):
        guardian.register_agent(_mock_agent("chronos"))
        guardian.register_agent(_mock_agent("cfo"))
        summary = guardian.daily_summary()
        assert "chronos" in summary
        assert "cfo" in summary

    def test_summary_no_agents_says_none(self, guardian):
        summary = guardian.daily_summary()
        assert "none" in summary.lower() or "registered agents:" in summary.lower()

    def test_summary_includes_homelink_section(self, guardian):
        summary = guardian.daily_summary()
        assert "H.O.M.E. L.I.N.K." in summary

    def test_summary_includes_ai_engine_section(self, guardian):
        summary = guardian.daily_summary()
        assert "AI Engine" in summary

    def test_summary_includes_vault_credentials(self, guardian):
        summary = guardian.daily_summary()
        assert "Vault:" in summary
        assert "credentials" in summary

    def test_summary_agent_report_error_is_handled(self, guardian):
        agent = _mock_agent("broken")
        agent.report.side_effect = RuntimeError("report exploded")
        guardian.register_agent(agent)
        # Should not raise; error is caught inline
        summary = guardian.daily_summary()
        assert "broken" in summary
        assert "Error generating report" in summary

    def test_summary_includes_audit_tail(self, guardian):
        summary = guardian.daily_summary()
        assert "Audit Summary" in summary or "audit" in summary.lower()

    def test_summary_shows_alerts_from_agents(self, guardian):
        agent = _mock_agent("cfo")
        agent.report.return_value = AgentReport(
            agent_name="cfo",
            status="ok",
            summary="finances ok",
            alerts=["Unusual $5000 charge detected"],
        )
        guardian.register_agent(agent)
        summary = guardian.daily_summary()
        assert "ALERT" in summary
        assert "Unusual $5000 charge" in summary

    def test_summary_shows_recommendations_from_agents(self, guardian):
        agent = _mock_agent("archivist")
        agent.report.return_value = AgentReport(
            agent_name="archivist",
            status="ok",
            summary="files ok",
            recommendations=["Enable nightly backup"],
        )
        guardian.register_agent(agent)
        summary = guardian.daily_summary()
        assert "REC" in summary
        assert "Enable nightly backup" in summary


# ---------------------------------------------------------------------------
# 6. shutdown
# ---------------------------------------------------------------------------

class TestShutdown:
    def test_shutdown_calls_agent_shutdown(self, guardian):
        agent = _mock_agent("cfo")
        guardian.register_agent(agent)
        guardian.shutdown()
        agent.shutdown.assert_called_once()

    def test_shutdown_logs_system_shutdown(self, guardian):
        guardian.shutdown()
        entries = guardian.audit.query(agent="guardian_one")
        assert any(e.action == "system_shutdown" for e in entries)

    def test_shutdown_continues_after_agent_error(self, guardian):
        a1 = _mock_agent("cfo")
        a2 = _mock_agent("chronos")
        a1.shutdown.side_effect = RuntimeError("shutdown failure")
        guardian.register_agent(a1)
        guardian.register_agent(a2)
        # Should not raise
        guardian.shutdown()
        a2.shutdown.assert_called_once()

    def test_shutdown_errors_logged_to_audit(self, guardian):
        agent = _mock_agent("crasher")
        agent.shutdown.side_effect = RuntimeError("cleanup failed")
        guardian.register_agent(agent)
        guardian.shutdown()
        entries = guardian.audit.query(agent="guardian_one", severity=Severity.ERROR)
        assert any("shutdown_error:crasher" in e.action for e in entries)

    def test_shutdown_with_no_agents_still_logs(self, guardian):
        guardian.shutdown()
        entries = guardian.audit.query(agent="guardian_one")
        assert any(e.action == "system_shutdown" for e in entries)


# ---------------------------------------------------------------------------
# 7. _seed_vault_from_env
# ---------------------------------------------------------------------------

class TestSeedVaultFromEnv:
    def test_notion_token_seeded_from_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOTION_TOKEN", "secret-notion-token-xyz")
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        g = _make_guardian(tmp_path)
        stored = g.vault.retrieve("NOTION_TOKEN")
        assert stored == "secret-notion-token-xyz"

    def test_notion_token_seed_recorded_in_audit(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOTION_TOKEN", "my-notion-key")
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        g = _make_guardian(tmp_path)
        entries = g.audit.query(agent="guardian_one")
        assert any("vault_seed:NOTION_TOKEN" in e.action for e in entries)

    def test_missing_env_token_not_seeded(self, tmp_path, monkeypatch):
        monkeypatch.delenv("NOTION_TOKEN", raising=False)
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        g = _make_guardian(tmp_path)
        assert g.vault.retrieve("NOTION_TOKEN") is None

    def test_ollama_key_seeded_from_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OLLAMA_API_KEY", "ollama-key-abc")
        monkeypatch.delenv("NOTION_TOKEN", raising=False)
        g = _make_guardian(tmp_path)
        stored = g.vault.retrieve("OLLAMA_API_KEY")
        assert stored == "ollama-key-abc"

    def test_already_stored_token_not_overwritten(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOTION_TOKEN", "first-token")
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        g = _make_guardian(tmp_path)
        # Re-boot with a different env value — should keep first token
        monkeypatch.setenv("NOTION_TOKEN", "second-token")
        g2 = GuardianOne(
            config=_make_config(tmp_path),
            vault_passphrase="test-passphrase-for-ci",
        )
        assert g2.vault.retrieve("NOTION_TOKEN") == "first-token"


# ---------------------------------------------------------------------------
# 8. list_agents / get_agent / ai_status
# ---------------------------------------------------------------------------

class TestUtilityMethods:
    def test_list_agents_reflects_registrations(self, guardian):
        assert guardian.list_agents() == []
        guardian.register_agent(_mock_agent("chronos"))
        assert guardian.list_agents() == ["chronos"]
        guardian.register_agent(_mock_agent("cfo"))
        assert set(guardian.list_agents()) == {"chronos", "cfo"}

    def test_ai_status_returns_dict_with_expected_keys(self, guardian):
        status = guardian.ai_status()
        assert "active_provider" in status
        assert "ollama" in status
        assert "anthropic" in status
        assert "total_requests" in status

    def test_ai_status_ollama_has_available_key(self, guardian):
        status = guardian.ai_status()
        assert "available" in status["ollama"]
        assert "model" in status["ollama"]

    def test_config_owner_preserved(self, tmp_path):
        config = GuardianConfig(
            owner="Jeremy Paulo Salvino Tabernero",
            data_dir=str(tmp_path / "data"),
            log_dir=str(tmp_path / "logs"),
        )
        g = GuardianOne(config=config, vault_passphrase="test-passphrase-for-ci")
        assert g.config.owner == "Jeremy Paulo Salvino Tabernero"
