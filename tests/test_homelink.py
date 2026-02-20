"""Tests for H.O.M.E. L.I.N.K. — vault, gateway, registry, monitor."""

import tempfile
from pathlib import Path

from guardian_one.core.audit import AuditLog
from guardian_one.homelink.vault import Vault, VaultError
from guardian_one.homelink.gateway import (
    Gateway,
    ServiceConfig,
    RateLimitConfig,
    CircuitState,
)
from guardian_one.homelink.registry import (
    IntegrationRegistry,
    IntegrationRecord,
    ThreatEntry,
    DOORDASH_INTEGRATION,
)
from guardian_one.homelink.monitor import Monitor


def _make_audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


# ========================================================================
# Vault tests
# ========================================================================

def test_vault_store_and_retrieve():
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Vault(Path(tmpdir) / "vault.enc", passphrase="test-pass")
        vault.store("API_KEY", "sk-12345", service="doordash")
        assert vault.retrieve("API_KEY") == "sk-12345"
        assert vault.retrieve("nonexistent") is None


def test_vault_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "vault.enc"
        vault1 = Vault(path, passphrase="test-pass")
        vault1.store("KEY", "value", service="test")

        vault2 = Vault(path, passphrase="test-pass")
        assert vault2.retrieve("KEY") == "value"


def test_vault_rotation():
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Vault(Path(tmpdir) / "vault.enc", passphrase="test-pass")
        vault.store("KEY", "old_value", service="test")
        assert vault.rotate("KEY", "new_value") is True
        assert vault.retrieve("KEY") == "new_value"
        assert vault.rotate("nonexistent", "x") is False


def test_vault_delete():
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Vault(Path(tmpdir) / "vault.enc", passphrase="test-pass")
        vault.store("KEY", "value")
        assert vault.delete("KEY") is True
        assert vault.retrieve("KEY") is None
        assert vault.delete("KEY") is False


def test_vault_list_keys():
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Vault(Path(tmpdir) / "vault.enc", passphrase="test-pass")
        vault.store("A", "1")
        vault.store("B", "2")
        assert sorted(vault.list_keys()) == ["A", "B"]


def test_vault_health_report():
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Vault(Path(tmpdir) / "vault.enc", passphrase="test-pass")
        vault.store("KEY1", "v1", service="doordash")
        vault.store("KEY2", "v2", service="google")

        report = vault.health_report()
        assert report["total_credentials"] == 2
        assert "doordash" in report["services"]
        assert "google" in report["services"]


def test_vault_wrong_passphrase():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "vault.enc"
        vault1 = Vault(path, passphrase="correct")
        vault1.store("KEY", "secret")

        try:
            Vault(path, passphrase="wrong")
            assert False, "Should have raised VaultError"
        except VaultError:
            pass


# ========================================================================
# Gateway tests
# ========================================================================

def test_gateway_register_service():
    gw = Gateway(audit=_make_audit())
    gw.register_service(ServiceConfig(name="test_api", base_url="https://api.example.com"))
    assert "test_api" in gw.list_services()


def test_gateway_unregistered_service():
    gw = Gateway(audit=_make_audit())
    result = gw.request("unknown", "GET", "/test", agent="test")
    assert result["success"] is False
    assert "not registered" in result["error"]


def test_gateway_tls_enforcement():
    gw = Gateway(audit=_make_audit())
    gw.register_service(ServiceConfig(
        name="insecure",
        base_url="http://api.example.com",
        require_tls=True,
    ))
    result = gw.request("insecure", "GET", "/test", agent="test")
    assert result["success"] is False
    assert "TLS required" in result["error"]


def test_gateway_access_control():
    gw = Gateway(audit=_make_audit())
    gw.register_service(ServiceConfig(
        name="restricted",
        base_url="https://api.example.com",
        allowed_agents=["cfo"],
    ))
    result = gw.request("restricted", "GET", "/test", agent="chronos")
    assert result["success"] is False
    assert result["status_code"] == 403


def test_gateway_rate_limiting():
    gw = Gateway(audit=_make_audit())
    gw.register_service(ServiceConfig(
        name="limited",
        base_url="https://api.example.com",
        rate_limit=RateLimitConfig(max_requests=2, window_seconds=60),
        max_retries=0,
    ))
    # First two should pass rate limit (will fail on network, but that's fine)
    gw.request("limited", "GET", "/test", agent="test")
    gw.request("limited", "GET", "/test", agent="test")
    result = gw.request("limited", "GET", "/test", agent="test")
    assert result["status_code"] == 429
    assert "Rate limit" in result["error"]


def test_gateway_service_status():
    gw = Gateway(audit=_make_audit())
    gw.register_service(ServiceConfig(name="svc", base_url="https://api.example.com"))
    status = gw.service_status("svc")
    assert status["service"] == "svc"
    assert status["circuit_state"] == "closed"


def test_gateway_unknown_service_status():
    gw = Gateway(audit=_make_audit())
    status = gw.service_status("nope")
    assert "error" in status


# ========================================================================
# Registry tests
# ========================================================================

def test_registry_register_and_get():
    reg = IntegrationRegistry()
    record = IntegrationRecord(
        name="test_svc",
        description="Test service",
        base_url="https://test.com",
        auth_method="api_key",
        data_flow="test data flow",
        owner_agent="chronos",
    )
    reg.register(record)
    assert reg.get("test_svc") is not None
    assert reg.get("test_svc").owner_agent == "chronos"


def test_registry_load_defaults():
    reg = IntegrationRegistry()
    reg.load_defaults()
    assert "doordash_drive" in reg.list_all()
    assert "rocket_money" in reg.list_all()
    assert "google_calendar" in reg.list_all()
    assert "nordvpn" in reg.list_all()


def test_registry_by_agent():
    reg = IntegrationRegistry()
    reg.load_defaults()
    doordash_integrations = reg.by_agent("doordash")
    assert len(doordash_integrations) == 1
    assert doordash_integrations[0].name == "doordash_drive"


def test_registry_threat_summary():
    reg = IntegrationRegistry()
    reg.load_defaults()
    threats = reg.threat_summary()
    assert len(threats) > 0
    # Should be sorted by severity (critical first)
    severities = [t["severity"] for t in threats]
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    for i in range(len(severities) - 1):
        assert severity_order.get(severities[i], 4) <= severity_order.get(severities[i + 1], 4)


def test_doordash_integration_has_threat_model():
    assert len(DOORDASH_INTEGRATION.threat_model) == 5
    assert DOORDASH_INTEGRATION.rollback_procedure != ""
    assert DOORDASH_INTEGRATION.failure_impact != ""


# ========================================================================
# Monitor tests
# ========================================================================

def test_monitor_assess_service():
    gw = Gateway(audit=_make_audit())
    gw.register_service(ServiceConfig(name="svc", base_url="https://api.example.com"))

    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Vault(Path(tmpdir) / "vault.enc", passphrase="test")
        reg = IntegrationRegistry()
        monitor = Monitor(gateway=gw, vault=vault, registry=reg)

        health = monitor.assess_service("svc")
        assert health.service == "svc"
        assert 1 <= health.risk_score <= 5


def test_monitor_unknown_service():
    gw = Gateway(audit=_make_audit())
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Vault(Path(tmpdir) / "vault.enc", passphrase="test")
        reg = IntegrationRegistry()
        monitor = Monitor(gateway=gw, vault=vault, registry=reg)

        health = monitor.assess_service("nonexistent")
        assert health.risk_score == 5  # Unknown = max risk


def test_monitor_weekly_brief():
    gw = Gateway(audit=_make_audit())
    gw.register_service(ServiceConfig(name="svc", base_url="https://api.example.com"))

    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Vault(Path(tmpdir) / "vault.enc", passphrase="test")
        vault.store("TEST_KEY", "value", service="test")
        reg = IntegrationRegistry()
        reg.load_defaults()
        monitor = Monitor(gateway=gw, vault=vault, registry=reg)

        brief = monitor.weekly_brief()
        assert "overall_risk_score" in brief
        assert "active_integrations" in brief
        assert "vault" in brief
        assert brief["vault"]["total_credentials"] == 1


def test_monitor_weekly_brief_text():
    gw = Gateway(audit=_make_audit())
    gw.register_service(ServiceConfig(name="svc", base_url="https://api.example.com"))

    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Vault(Path(tmpdir) / "vault.enc", passphrase="test")
        reg = IntegrationRegistry()
        monitor = Monitor(gateway=gw, vault=vault, registry=reg)

        text = monitor.weekly_brief_text()
        assert "H.O.M.E. L.I.N.K." in text
        assert "Weekly Security" in text
        assert "VAULT STATUS" in text


# ========================================================================
# Integration with Guardian One
# ========================================================================

def test_guardian_has_homelink():
    from guardian_one.core.config import GuardianConfig, AgentConfig

    config = GuardianConfig(
        log_dir=tempfile.mkdtemp(),
        data_dir=tempfile.mkdtemp(),
        agents={
            "chronos": AgentConfig(name="chronos"),
        },
    )
    from guardian_one.core.guardian import GuardianOne
    from guardian_one.agents.chronos import Chronos

    guardian = GuardianOne(config, vault_passphrase="test-pass")
    guardian.register_agent(Chronos(config.agents["chronos"], guardian.audit))

    # Gateway should have services from registry
    assert len(guardian.gateway.list_services()) > 0
    # Vault should be accessible
    assert guardian.vault.health_report()["total_credentials"] == 0
    # Registry should have defaults
    assert "doordash_drive" in guardian.registry.list_all()
    # Daily summary should include H.O.M.E. L.I.N.K. section
    summary = guardian.daily_summary()
    assert "H.O.M.E. L.I.N.K." in summary
    guardian.shutdown()
