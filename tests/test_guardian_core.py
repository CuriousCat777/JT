"""Unit tests for GuardianOne — the central coordinator.

Focuses on method-level isolation using mocks. Cross-agent integration
tests live in test_integration.py. These tests avoid duplicating the
full-stack flows already covered there and instead target:
  - Constructor validation and error paths
  - Boot audit record
  - Access policy setup (_setup_access_policies)
  - Agent lifecycle: register_agent, run_all, run_agent, shutdown
  - run_all error isolation and audit logging
  - daily_summary content (agents, HomeLink, AI Engine sections)
  - Vault seeding from environment (_seed_vault_from_env)
  - AI engine delegation (ai_status, think)
  - Utility methods (list_agents, get_agent)
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
        g = GuardianOne(config=config)  # no explicit passphrase argument
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

    def test_all_subsystems_created(self, guardian):
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

    def test_system_boot_audit_entry_has_owner_detail(self, guardian):
        entries = guardian.audit.query(agent="guardian_one")
        boot = next(e for e in entries if e.action == "system_boot")
        assert boot.details.get("owner") == "Test Owner"

    def test_agents_dict_starts_empty(self, guardian):
        assert guardian.list_agents() == []

    def test_default_config_used_when_none_provided(self, tmp_path, monkeypatch):
        """GuardianOne falls back to load_config() when config is None."""
        monkeypatch.delenv("GUARDIAN_MASTER_PASSPHRASE", raising=False)
        with patch("guardian_one.core.guardian.load_config") as mock_load:
            mock_load.return_value = _make_config(tmp_path)
            g = GuardianOne(vault_passphrase="test-passphrase-for-ci")
        mock_load.assert_called_once()
        assert g is not None

    def test_config_owner_preserved(self, tmp_path):
        config = GuardianConfig(
            owner="Jeremy Paulo Salvino Tabernero",
            data_dir=str(tmp_path / "data"),
            log_dir=str(tmp_path / "logs"),
        )
        g = GuardianOne(config=config, vault_passphrase="test-passphrase-for-ci")
        assert g.config.owner == "Jeremy Paulo Salvino Tabernero"


# ---------------------------------------------------------------------------
# 2. Access policies (_setup_access_policies)
# ---------------------------------------------------------------------------

class TestAccessPolicies:
    def test_jeremy_registered_as_owner(self, guardian):
        policy = guardian.access.get_policy("jeremy")
        assert policy is not None
        assert policy.level == AccessLevel.OWNER

    def test_jeremy_owner_bypasses_resource_check(self, guardian):
        # OWNER has unrestricted access
        assert guardian.access.check("jeremy", "anything")
        assert guardian.access.check("jeremy", "vault_master")
        assert guardian.access.check("jeremy", "financial_data")

    def test_guardian_one_registered_as_guardian(self, guardian):
        policy = guardian.access.get_policy("guardian_one")
        assert policy is not None
        assert policy.level == AccessLevel.GUARDIAN

    def test_mentor_registered_with_scoped_resources(self, guardian):
        policy = guardian.access.get_policy("mentor")
        assert policy is not None
        assert policy.level == AccessLevel.MENTOR
        # Mentor must have read-only resources set at boot
        assert "audit_log" in policy.allowed_resources
        assert "reports" in policy.allowed_resources
        assert "config_readonly" in policy.allowed_resources

    def test_all_default_identities_present(self, guardian):
        identities = guardian.access.list_identities()
        assert "jeremy" in identities
        assert "guardian_one" in identities
        assert "mentor" in identities

    def test_unknown_identity_is_denied(self, guardian):
        assert not guardian.access.check("intruder", "calendar")
        assert not guardian.access.check("intruder", "any_resource")


# ---------------------------------------------------------------------------
# 3. register_agent
# ---------------------------------------------------------------------------

class TestRegisterAgent:
    def test_register_single_agent(self, guardian):
        agent = _mock_agent("chronos", ["calendar"])
        guardian.register_agent(agent)
        assert "chronos" in guardian.list_agents()

    def test_register_calls_initialize_once(self, guardian):
        agent = _mock_agent("cfo", ["accounts"])
        guardian.register_agent(agent)
        agent.initialize.assert_called_once()

    def test_register_injects_ai_engine(self, guardian):
        agent = _mock_agent("archivist")
        guardian.register_agent(agent)
        agent.set_ai_engine.assert_called_once_with(guardian.ai_engine)

    def test_register_creates_agent_access_policy(self, guardian):
        agent = _mock_agent("doordash", ["meal_orders", "food_budget"])
        guardian.register_agent(agent)
        policy = guardian.access.get_policy("doordash")
        assert policy is not None
        assert policy.level == AccessLevel.AGENT
        assert "meal_orders" in policy.allowed_resources
        assert "food_budget" in policy.allowed_resources

    def test_registered_agent_resource_check_passes(self, guardian):
        agent = _mock_agent("chronos", ["calendar"])
        guardian.register_agent(agent)
        assert guardian.access.check("chronos", "calendar")

    def test_registered_agent_denied_unlisted_resource(self, guardian):
        agent = _mock_agent("chronos", ["calendar"])
        guardian.register_agent(agent)
        assert not guardian.access.check("chronos", "financial_accounts")

    def test_register_duplicate_agent_raises_value_error(self, guardian):
        agent = _mock_agent("chronos")
        guardian.register_agent(agent)
        duplicate = _mock_agent("chronos")
        with pytest.raises(ValueError, match="already registered"):
            guardian.register_agent(duplicate)

    def test_register_logs_registration_and_initialization(self, guardian):
        agent = _mock_agent("archivist")
        guardian.register_agent(agent)
        entries = guardian.audit.query(agent="guardian_one")
        actions = [e.action for e in entries]
        assert any("agent_registered:archivist" in a for a in actions)
        assert any("agent_initialized:archivist" in a for a in actions)

    def test_get_agent_returns_registered_instance(self, guardian):
        agent = _mock_agent("cfo")
        guardian.register_agent(agent)
        assert guardian.get_agent("cfo") is agent

    def test_get_agent_returns_none_for_unknown(self, guardian):
        assert guardian.get_agent("nonexistent") is None

    def test_list_agents_reflects_all_registrations(self, guardian):
        for name in ("chronos", "cfo", "archivist"):
            guardian.register_agent(_mock_agent(name))
        assert set(guardian.list_agents()) == {"chronos", "cfo", "archivist"}


# ---------------------------------------------------------------------------
# 4. run_all / run_agent
# ---------------------------------------------------------------------------

class TestRunAll:
    def test_run_all_returns_one_report_per_agent(self, guardian):
        for name in ("chronos", "cfo"):
            guardian.register_agent(_mock_agent(name))
        reports = guardian.run_all()
        assert len(reports) == 2
        assert {r.agent_name for r in reports} == {"chronos", "cfo"}

    def test_run_all_empty_agents_returns_empty_list(self, guardian):
        assert guardian.run_all() == []

    def test_run_all_agent_exception_becomes_error_report(self, guardian):
        bad = _mock_agent("crasher")
        bad.run.side_effect = RuntimeError("API unreachable")
        guardian.register_agent(_mock_agent("cfo"))
        guardian.register_agent(bad)

        reports = guardian.run_all()
        error_report = next(r for r in reports if r.agent_name == "crasher")
        assert error_report.status == AgentStatus.ERROR.value
        assert "API unreachable" in error_report.summary

    def test_run_all_exception_does_not_halt_remaining_agents(self, guardian):
        bad = _mock_agent("crasher")
        bad.run.side_effect = Exception("boom")
        good = _mock_agent("cfo")
        guardian.register_agent(bad)
        guardian.register_agent(good)

        reports = guardian.run_all()
        cfo_report = next(r for r in reports if r.agent_name == "cfo")
        assert cfo_report.status == AgentStatus.IDLE.value

    def test_run_all_disabled_agent_returns_disabled_status(self, guardian):
        agent = _mock_agent("sleepy")
        agent.config.enabled = False
        guardian.register_agent(agent)
        reports = guardian.run_all()
        assert reports[0].status == AgentStatus.DISABLED.value
        agent.run.assert_not_called()

    def test_run_all_error_logged_as_error_severity(self, guardian):
        bad = _mock_agent("crasher")
        bad.run.side_effect = ValueError("crash!")
        guardian.register_agent(bad)
        guardian.run_all()
        entries = guardian.audit.query(agent="guardian_one", severity=Severity.ERROR)
        assert any("run_error:crasher" in e.action for e in entries)

    def test_run_all_error_entry_requires_review(self, guardian):
        bad = _mock_agent("crasher")
        bad.run.side_effect = RuntimeError("failed")
        guardian.register_agent(bad)
        guardian.run_all()
        entries = guardian.audit.query(agent="guardian_one", severity=Severity.ERROR)
        error_entry = next(e for e in entries if "run_error:crasher" in e.action)
        assert error_entry.requires_review is True

    def test_run_all_calls_mediator_check_conflicts(self, guardian):
        guardian.register_agent(_mock_agent("x"))
        with patch.object(guardian.mediator, "check_conflicts", return_value=[]) as mock_check:
            guardian.run_all()
        mock_check.assert_called_once()

    def test_run_all_clears_mediator_pending_after_run(self, guardian):
        with patch.object(guardian.mediator, "clear_pending") as mock_clear:
            guardian.run_all()
        mock_clear.assert_called_once()

    def test_run_agent_unknown_name_raises_key_error(self, guardian):
        with pytest.raises(KeyError, match="nonexistent"):
            guardian.run_agent("nonexistent")

    def test_run_agent_logs_run_start_and_complete(self, guardian):
        guardian.register_agent(_mock_agent("cfo"))
        guardian.run_agent("cfo")
        entries = guardian.audit.query(agent="guardian_one")
        actions = [e.action for e in entries]
        assert any("run_start:cfo" in a for a in actions)
        assert any("run_complete:cfo" in a for a in actions)


# ---------------------------------------------------------------------------
# 5. daily_summary
# ---------------------------------------------------------------------------

class TestDailySummary:
    def test_summary_is_a_string(self, guardian):
        assert isinstance(guardian.daily_summary(), str)

    def test_summary_contains_header_with_timestamp(self, guardian):
        summary = guardian.daily_summary()
        assert "Guardian One Daily Summary" in summary

    def test_summary_contains_owner_name(self, guardian):
        summary = guardian.daily_summary()
        assert "Test Owner" in summary

    def test_summary_lists_registered_agents(self, guardian):
        guardian.register_agent(_mock_agent("chronos"))
        guardian.register_agent(_mock_agent("cfo"))
        summary = guardian.daily_summary()
        assert "chronos" in summary
        assert "cfo" in summary

    def test_summary_says_none_when_no_agents(self, guardian):
        summary = guardian.daily_summary()
        # "none" appears in "Registered agents: none"
        assert "none" in summary.lower() or "registered agents:" in summary.lower()

    def test_summary_includes_homelink_section(self, guardian):
        summary = guardian.daily_summary()
        assert "H.O.M.E. L.I.N.K." in summary

    def test_summary_includes_vault_credentials_line(self, guardian):
        summary = guardian.daily_summary()
        assert "Vault:" in summary
        assert "credentials" in summary

    def test_summary_includes_ai_engine_section(self, guardian):
        summary = guardian.daily_summary()
        assert "AI Engine" in summary

    def test_summary_includes_active_provider(self, guardian):
        summary = guardian.daily_summary()
        assert "Active provider:" in summary

    def test_summary_includes_audit_section(self, guardian):
        summary = guardian.daily_summary()
        assert "Audit Summary" in summary

    def test_summary_handles_agent_report_exception_inline(self, guardian):
        broken = _mock_agent("broken")
        broken.report.side_effect = RuntimeError("report exploded")
        guardian.register_agent(broken)
        # Must not propagate; error appears inline in the summary
        summary = guardian.daily_summary()
        assert "broken" in summary
        assert "Error generating report" in summary

    def test_summary_shows_alert_lines_from_agent(self, guardian):
        agent = _mock_agent("cfo")
        agent.report.return_value = AgentReport(
            agent_name="cfo",
            status="ok",
            summary="finances ok",
            alerts=["Unusual $5000 charge detected"],
        )
        guardian.register_agent(agent)
        summary = guardian.daily_summary()
        assert "[ALERT]" in summary
        assert "Unusual $5000 charge" in summary

    def test_summary_shows_recommendation_lines_from_agent(self, guardian):
        agent = _mock_agent("archivist")
        agent.report.return_value = AgentReport(
            agent_name="archivist",
            status="ok",
            summary="files ok",
            recommendations=["Enable nightly backup"],
        )
        guardian.register_agent(agent)
        summary = guardian.daily_summary()
        assert "[REC]" in summary
        assert "Enable nightly backup" in summary


# ---------------------------------------------------------------------------
# 6. shutdown
# ---------------------------------------------------------------------------

class TestShutdown:
    def test_shutdown_calls_each_registered_agent_shutdown(self, guardian):
        a1 = _mock_agent("cfo")
        a2 = _mock_agent("chronos")
        guardian.register_agent(a1)
        guardian.register_agent(a2)
        guardian.shutdown()
        a1.shutdown.assert_called_once()
        a2.shutdown.assert_called_once()

    def test_shutdown_logs_system_shutdown_to_audit(self, guardian):
        guardian.shutdown()
        entries = guardian.audit.query(agent="guardian_one")
        assert any(e.action == "system_shutdown" for e in entries)

    def test_shutdown_system_shutdown_is_info_severity(self, guardian):
        guardian.shutdown()
        entries = guardian.audit.query(agent="guardian_one")
        shutdown_entry = next(e for e in entries if e.action == "system_shutdown")
        assert shutdown_entry.severity == Severity.INFO.value

    def test_shutdown_continues_past_agent_error(self, guardian):
        """An exception during one agent's shutdown must not stop others."""
        fragile = _mock_agent("fragile")
        fragile.shutdown.side_effect = RuntimeError("cleanup failed")
        healthy = _mock_agent("healthy")
        guardian.register_agent(fragile)
        guardian.register_agent(healthy)
        # Should complete without raising
        guardian.shutdown()
        healthy.shutdown.assert_called_once()

    def test_shutdown_agent_error_logged_as_error_severity(self, guardian):
        agent = _mock_agent("crasher")
        agent.shutdown.side_effect = RuntimeError("cleanup failed")
        guardian.register_agent(agent)
        guardian.shutdown()
        entries = guardian.audit.query(agent="guardian_one", severity=Severity.ERROR)
        assert any("shutdown_error:crasher" in e.action for e in entries)

    def test_shutdown_with_no_agents_logs_system_shutdown(self, guardian):
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
        assert g.vault.retrieve("NOTION_TOKEN") == "secret-notion-token-xyz"

    def test_notion_token_seed_creates_audit_entry(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOTION_TOKEN", "my-notion-key")
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        g = _make_guardian(tmp_path)
        entries = g.audit.query(agent="guardian_one")
        assert any("vault_seed:NOTION_TOKEN" in e.action for e in entries)

    def test_missing_notion_token_not_seeded(self, tmp_path, monkeypatch):
        monkeypatch.delenv("NOTION_TOKEN", raising=False)
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        g = _make_guardian(tmp_path)
        assert g.vault.retrieve("NOTION_TOKEN") is None

    def test_missing_env_token_does_not_create_audit_entry(self, tmp_path, monkeypatch):
        monkeypatch.delenv("NOTION_TOKEN", raising=False)
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        g = _make_guardian(tmp_path)
        entries = g.audit.query(agent="guardian_one")
        assert not any("vault_seed:NOTION_TOKEN" in e.action for e in entries)

    def test_ollama_api_key_seeded_from_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OLLAMA_API_KEY", "ollama-key-abc")
        monkeypatch.delenv("NOTION_TOKEN", raising=False)
        g = _make_guardian(tmp_path)
        assert g.vault.retrieve("OLLAMA_API_KEY") == "ollama-key-abc"

    def test_already_stored_token_not_overwritten(self, tmp_path, monkeypatch):
        """If the vault already holds the key, a second boot with a new env value
        must leave the original value intact."""
        monkeypatch.setenv("NOTION_TOKEN", "first-token")
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        _make_guardian(tmp_path)  # first boot stores "first-token"

        monkeypatch.setenv("NOTION_TOKEN", "second-token")
        g2 = GuardianOne(
            config=_make_config(tmp_path),
            vault_passphrase="test-passphrase-for-ci",
        )
        assert g2.vault.retrieve("NOTION_TOKEN") == "first-token"


# ---------------------------------------------------------------------------
# 8. AI engine delegation (ai_status, think)
# ---------------------------------------------------------------------------

class TestAIEngineDelegation:
    def test_ai_status_returns_dict(self, guardian):
        status = guardian.ai_status()
        assert isinstance(status, dict)

    def test_ai_status_has_expected_keys(self, guardian):
        status = guardian.ai_status()
        assert "active_provider" in status
        assert "ollama" in status
        assert "anthropic" in status
        assert "total_requests" in status

    def test_ai_status_ollama_block_has_model_and_available(self, guardian):
        ollama = guardian.ai_status()["ollama"]
        assert "available" in ollama
        assert "model" in ollama

    def test_think_delegates_to_ai_engine_reason(self, guardian):
        mock_response = MagicMock()
        mock_response.content = "Strategic insight"
        with patch.object(guardian.ai_engine, "reason", return_value=mock_response):
            result = guardian.think("What should I do today?")
        assert result == "Strategic insight"

    def test_think_passes_guardian_one_as_agent_name(self, guardian):
        mock_response = MagicMock()
        mock_response.content = "ok"
        with patch.object(guardian.ai_engine, "reason", return_value=mock_response) as mock_reason:
            guardian.think("hello")
        call_args = mock_reason.call_args
        agent_name = call_args.kwargs.get("agent_name") or call_args.args[0]
        assert agent_name == "guardian_one"

    def test_think_passes_context_to_engine(self, guardian):
        mock_response = MagicMock()
        mock_response.content = "result"
        ctx = {"budget": 5000, "month": "April"}
        with patch.object(guardian.ai_engine, "reason", return_value=mock_response) as mock_reason:
            guardian.think("summarise finances", context=ctx)
        call_kwargs = mock_reason.call_args.kwargs
        assert call_kwargs.get("context") == ctx
