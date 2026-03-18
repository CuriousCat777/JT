"""Tests for WebArchitect agent and n8n integration."""

import tempfile
from pathlib import Path
from typing import Any

from guardian_one.core.audit import AuditLog
from guardian_one.core.base_agent import AgentStatus
from guardian_one.core.config import AgentConfig
from guardian_one.agents.web_architect import (
    DEFAULT_SECURITY_HEADERS,
    REQUIRED_SECURITY_HEADERS,
    SiteSecurityReport,
    UptimeRecord,
    WebArchitect,
)
from guardian_one.integrations.n8n_sync import (
    N8nAPIProvider,
    N8nExecution,
    N8nProvider,
    N8nWorkflow,
    WebsiteDeployment,
    security_scan_workflow_nodes,
    uptime_monitor_workflow_nodes,
    website_build_workflow_nodes,
)


def _make_audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


# ---------------------------------------------------------------------------
# Fake n8n provider for offline testing
# ---------------------------------------------------------------------------

class FakeN8nProvider(N8nProvider):
    """In-memory n8n provider for tests."""

    def __init__(self, connected: bool = True) -> None:
        self._connected = connected
        self._workflows: dict[str, N8nWorkflow] = {}
        self._executions: dict[str, N8nExecution] = {}
        self._next_id = 1
        self.has_credentials = True

    @property
    def is_authenticated(self) -> bool:
        return self._connected

    def authenticate(self) -> bool:
        return self._connected

    def list_workflows(self) -> list[N8nWorkflow]:
        return list(self._workflows.values())

    def get_workflow(self, workflow_id: str) -> N8nWorkflow | None:
        return self._workflows.get(workflow_id)

    def create_workflow(self, name: str, nodes: list[dict[str, Any]]) -> N8nWorkflow | None:
        if not self._connected:
            return None
        wf = N8nWorkflow(
            id=str(self._next_id),
            name=name,
            nodes=nodes,
        )
        self._next_id += 1
        self._workflows[wf.id] = wf
        return wf

    def activate_workflow(self, workflow_id: str) -> bool:
        wf = self._workflows.get(workflow_id)
        if wf:
            wf.active = True
            return True
        return False

    def deactivate_workflow(self, workflow_id: str) -> bool:
        wf = self._workflows.get(workflow_id)
        if wf:
            wf.active = False
            return True
        return False

    def execute_workflow(self, workflow_id: str, data: dict[str, Any] | None = None) -> N8nExecution | None:
        if not self._connected or workflow_id not in self._workflows:
            return None
        ex = N8nExecution(
            id=f"exec-{self._next_id}",
            workflow_id=workflow_id,
            status="success",
        )
        self._next_id += 1
        self._executions[ex.id] = ex
        return ex

    def get_execution(self, execution_id: str) -> N8nExecution | None:
        return self._executions.get(execution_id)


# ---------------------------------------------------------------------------
# WebArchitect — initialization
# ---------------------------------------------------------------------------

def test_web_architect_initialize():
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), FakeN8nProvider())
    agent.initialize()
    assert agent.status == AgentStatus.IDLE


def test_web_architect_initialize_with_domains():
    cfg = AgentConfig(name="web_architect", custom={"domains": ["example.com", "test.io"]})
    agent = WebArchitect(cfg, _make_audit(), FakeN8nProvider())
    agent.initialize()
    assert agent.list_domains() == ["example.com", "test.io"]


def test_web_architect_initialize_disconnected():
    provider = FakeN8nProvider(connected=False)
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), provider)
    agent.initialize()
    assert agent.status == AgentStatus.IDLE
    assert not agent._n8n_connected


# ---------------------------------------------------------------------------
# Site creation (connected)
# ---------------------------------------------------------------------------

def test_create_site_connected():
    provider = FakeN8nProvider(connected=True)
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), provider)
    agent.initialize()

    deployment = agent.create_site("mysite.com")
    assert deployment.domain == "mysite.com"
    assert deployment.status == "deployed"
    assert deployment.ssl_enabled is True
    assert "index.html" in deployment.pages
    assert deployment.workflow_id  # Should have an n8n workflow ID

    # Three workflows created: build, scan, uptime
    assert len(provider._workflows) == 3


def test_create_site_adds_domain():
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), FakeN8nProvider())
    agent.initialize()

    assert "newsite.org" not in agent.list_domains()
    agent.create_site("newsite.org")
    assert "newsite.org" in agent.list_domains()


def test_create_site_uptime_monitor_activated():
    provider = FakeN8nProvider(connected=True)
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), provider)
    agent.initialize()

    agent.create_site("monitored.io")
    # The uptime monitor workflow (the third one created, id="3") should be active
    uptime_wf = provider._workflows.get("3")
    assert uptime_wf is not None
    assert uptime_wf.active is True


# ---------------------------------------------------------------------------
# Site creation (disconnected / offline)
# ---------------------------------------------------------------------------

def test_create_site_offline():
    provider = FakeN8nProvider(connected=False)
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), provider)
    agent.initialize()

    deployment = agent.create_site("offline-site.com")
    assert deployment.domain == "offline-site.com"
    assert deployment.status == "deployed"
    assert deployment.workflow_id.startswith("local-build-")

    # Local workflows stored
    wfs = agent.list_workflows()
    assert len(wfs) == 3
    assert any("build" in wid for wid in wfs)
    assert any("scan" in wid for wid in wfs)
    assert any("uptime" in wid for wid in wfs)


# ---------------------------------------------------------------------------
# Deploy site
# ---------------------------------------------------------------------------

def test_deploy_site_connected():
    provider = FakeN8nProvider(connected=True)
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), provider)
    agent.initialize()

    agent.create_site("deploy-test.com")
    execution = agent.deploy_site("deploy-test.com")
    assert execution is not None
    assert execution.status == "success"


def test_deploy_site_no_deployment():
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), FakeN8nProvider())
    agent.initialize()

    result = agent.deploy_site("nonexistent.com")
    assert result is None


def test_deploy_site_offline():
    provider = FakeN8nProvider(connected=False)
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), provider)
    agent.initialize()

    agent.create_site("offline-deploy.net")
    execution = agent.deploy_site("offline-deploy.net")
    assert execution is not None
    assert execution.status == "success"
    assert execution.data.get("offline") is True


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

def test_security_policy():
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), FakeN8nProvider())
    agent.initialize()

    policy = agent.security_policy()
    assert policy["ssl_required"] is True
    assert "Content-Security-Policy" in policy["required_headers"]
    assert "X-Frame-Options" in policy["required_headers"]


def test_security_report_deployed_site():
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), FakeN8nProvider())
    agent.initialize()
    agent.create_site("secure.com")

    report = agent.get_security_report("secure.com")
    # No report yet until run() is called
    assert report is None

    # Run triggers security check
    agent.run()
    report = agent.get_security_report("secure.com")
    assert report is not None
    assert report.passed is True
    assert len(report.headers_missing) == 0


def test_security_report_undeployed_domain():
    cfg = AgentConfig(name="web_architect", custom={"domains": ["bare.com"]})
    agent = WebArchitect(cfg, _make_audit(), FakeN8nProvider())
    agent.initialize()

    # Run will flag bare.com as having no deployment
    run_report = agent.run()
    assert any("bare.com" in r and "no deployment" in r for r in run_report.recommendations)


# ---------------------------------------------------------------------------
# Uptime monitoring
# ---------------------------------------------------------------------------

def test_record_uptime():
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), FakeN8nProvider())
    agent.initialize()

    agent.record_uptime("test.com", up=True, status_code=200, response_time_ms=45.2)
    agent.record_uptime("test.com", up=True, status_code=200, response_time_ms=52.1)
    agent.record_uptime("test.com", up=False, status_code=503, response_time_ms=0)

    summary = agent.uptime_summary("test.com")
    assert summary["checks"] == 3
    assert summary["up"] == 2
    assert summary["down"] == 1
    assert summary["uptime_pct"] == 66.7


def test_uptime_summary_no_records():
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), FakeN8nProvider())
    agent.initialize()

    summary = agent.uptime_summary("unknown.com")
    assert summary["checks"] == 0


def test_uptime_alert_in_run():
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), FakeN8nProvider())
    agent.initialize()
    agent.create_site("flaky.net")

    # Record some downtime
    for _ in range(5):
        agent.record_uptime("flaky.net", up=True)
    for _ in range(5):
        agent.record_uptime("flaky.net", up=False)

    report = agent.run()
    assert any("flaky.net" in a and "uptime" in a for a in report.alerts)


# ---------------------------------------------------------------------------
# Domain status
# ---------------------------------------------------------------------------

def test_domain_status_deployed():
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), FakeN8nProvider())
    agent.initialize()
    agent.create_site("status-test.com")

    status = agent.domain_status("status-test.com")
    assert status["deployed"] is True
    assert status["ssl_enabled"] is True
    assert status["deployment_status"] == "deployed"
    assert "index.html" in status["pages"]


def test_domain_status_not_deployed():
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), FakeN8nProvider())
    agent.initialize()

    status = agent.domain_status("nowhere.com")
    assert status["deployed"] is False
    assert status["deployment_status"] == "none"


# ---------------------------------------------------------------------------
# Run cycle
# ---------------------------------------------------------------------------

def test_run_connected_no_domains():
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), FakeN8nProvider())
    agent.initialize()

    report = agent.run()
    assert report.status == AgentStatus.IDLE.value
    assert "0 domains" in report.summary


def test_run_connected_with_site():
    provider = FakeN8nProvider(connected=True)
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), provider)
    agent.initialize()
    agent.create_site("fullrun.com")

    report = agent.run()
    assert report.status == AgentStatus.IDLE.value
    assert "1 domains" in report.summary
    assert report.data["n8n_connected"] is True
    # Synced 3 workflows from fake provider
    assert any("Synced" in a for a in report.actions_taken)


def test_run_disconnected():
    provider = FakeN8nProvider(connected=False)
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), provider)
    agent.initialize()

    report = agent.run()
    assert any("n8n not connected" in a for a in report.alerts)


def test_report_no_side_effects():
    agent = WebArchitect(AgentConfig(name="web_architect"), _make_audit(), FakeN8nProvider())
    agent.initialize()
    agent.create_site("report-test.io")

    report = agent.report()
    assert report.agent_name == "web_architect"
    assert "report-test.io" in str(report.data["deployments"])


# ---------------------------------------------------------------------------
# n8n workflow template generation
# ---------------------------------------------------------------------------

def test_website_build_workflow_nodes():
    nodes = website_build_workflow_nodes("example.com")
    assert len(nodes) == 5
    assert nodes[0]["name"] == "Trigger"
    assert any("Security Headers" in n["name"] for n in nodes)
    assert any("SSL Check" in n["name"] for n in nodes)
    assert any("Deploy" in n["name"] for n in nodes)


def test_security_scan_workflow_nodes():
    nodes = security_scan_workflow_nodes("example.com")
    assert len(nodes) == 3
    assert any("Header Scan" in n["name"] for n in nodes)
    assert any("Analyze" in n["name"] for n in nodes)


def test_uptime_monitor_workflow_nodes():
    nodes = uptime_monitor_workflow_nodes("example.com")
    assert len(nodes) == 3
    assert nodes[0]["name"] == "Schedule"
    assert any("Health Check" in n["name"] for n in nodes)


# ---------------------------------------------------------------------------
# N8nAPIProvider (unit tests — no network)
# ---------------------------------------------------------------------------

def test_n8n_api_provider_no_credentials():
    provider = N8nAPIProvider(base_url="", api_key="")
    assert not provider.has_credentials
    assert not provider.authenticate()
    assert not provider.is_authenticated


def test_n8n_api_provider_has_credentials():
    provider = N8nAPIProvider(base_url="http://localhost:5678", api_key="test-key")
    assert provider.has_credentials


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

def test_n8n_in_registry():
    from guardian_one.homelink.registry import IntegrationRegistry
    reg = IntegrationRegistry()
    reg.load_defaults()
    assert "n8n_workflows" in reg.list_all()

    n8n = reg.get("n8n_workflows")
    assert n8n is not None
    assert n8n.owner_agent == "web_architect"
    assert n8n.auth_method == "api_key"
    assert len(n8n.threat_model) == 5
    assert any("critical" == t.severity for t in n8n.threat_model)


def test_n8n_registry_by_agent():
    from guardian_one.homelink.registry import IntegrationRegistry
    reg = IntegrationRegistry()
    reg.load_defaults()
    wa_integrations = reg.by_agent("web_architect")
    assert len(wa_integrations) >= 1
    wa_names = [i.name for i in wa_integrations]
    assert "n8n_workflows" in wa_names
    assert "cloudflare" in wa_names


# ---------------------------------------------------------------------------
# Full integration: WebArchitect via GuardianOne
# ---------------------------------------------------------------------------

def test_web_architect_in_guardian():
    """WebArchitect registers and runs through the full Guardian One system."""
    from guardian_one.core.config import load_config
    from guardian_one.core.guardian import GuardianOne

    config = load_config()
    guardian = GuardianOne(config=config)

    cfg = config.agents.get("web_architect", AgentConfig(name="web_architect"))
    agent = WebArchitect(cfg, guardian.audit, FakeN8nProvider())
    guardian.register_agent(agent)

    report = guardian.run_agent("web_architect")
    assert report.status == AgentStatus.IDLE.value
    assert report.agent_name == "web_architect"

    guardian.shutdown()
