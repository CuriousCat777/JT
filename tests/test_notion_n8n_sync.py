"""Tests for NotionN8nSync — n8n workflow status pushed to Notion."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from guardian_one.core.audit import AuditLog
from guardian_one.homelink.vault import Vault
from guardian_one.homelink.gateway import Gateway, ServiceConfig, RateLimitConfig
from guardian_one.integrations.notion_sync import NotionSync
from guardian_one.integrations.notion_n8n_sync import NotionN8nSync
from guardian_one.integrations.n8n_sync import (
    N8nWorkflow,
    N8nExecution,
    GatewayN8nProvider,
)


def _make_audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


def _make_sync(tmpdir: str) -> tuple[NotionSync, Gateway, Vault]:
    audit = _make_audit()
    vault = Vault(Path(tmpdir) / "vault.enc", passphrase="test-pass")
    vault.store("NOTION_TOKEN", "ntn_test_token", service="notion", scope="write")
    gateway = Gateway(audit=audit)
    gateway.register_service(ServiceConfig(
        name="notion",
        base_url="https://api.notion.com",
        rate_limit=RateLimitConfig(max_requests=60, window_seconds=60),
    ))
    sync = NotionSync(
        gateway=gateway,
        vault=vault,
        audit=audit,
        root_page_id="root-page-123",
    )
    return sync, gateway, vault


def _mock_gateway_success(gateway: Gateway) -> None:
    """Patch gateway.request to return success with a fake page ID."""
    counter = {"n": 0}
    def fake_request(**kwargs):
        counter["n"] += 1
        return {
            "success": True,
            "data": {"id": f"page-{counter['n']}"},
        }
    gateway.request = MagicMock(side_effect=fake_request)


def _sample_workflows() -> list[N8nWorkflow]:
    return [
        N8nWorkflow(
            id="wf-1",
            name="Website Build -- jtmdai.com",
            active=True,
            tags=["website", "build"],
            updated_at="2026-03-20T10:00:00Z",
        ),
        N8nWorkflow(
            id="wf-2",
            name="Security Scan -- jtmdai.com",
            active=True,
            tags=["security"],
            updated_at="2026-03-20T10:00:00Z",
        ),
        N8nWorkflow(
            id="wf-3",
            name="Uptime Monitor -- jtmdai.com",
            active=False,
            tags=["monitoring"],
        ),
    ]


def _sample_executions() -> list[N8nExecution]:
    return [
        N8nExecution(
            id="exec-1",
            workflow_id="wf-1",
            status="success",
            started_at="2026-03-20T10:05:00Z",
            finished_at="2026-03-20T10:05:30Z",
            mode="manual",
        ),
        N8nExecution(
            id="exec-2",
            workflow_id="wf-2",
            status="error",
            started_at="2026-03-20T11:00:00Z",
            finished_at="2026-03-20T11:00:10Z",
            mode="trigger",
        ),
        N8nExecution(
            id="exec-3",
            workflow_id="wf-1",
            status="success",
            started_at="2026-03-20T12:00:00Z",
            mode="manual",
        ),
    ]


# ---------------------------------------------------------------------------
# NotionN8nSync dashboard tests
# ---------------------------------------------------------------------------


class TestPushWorkflowDashboard:
    def test_creates_parent_and_dashboard_page(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync, gateway, _ = _make_sync(tmpdir)
            _mock_gateway_success(gateway)
            n8n_sync = NotionN8nSync(sync, _make_audit())
            result = n8n_sync.push_workflow_dashboard(
                workflows=_sample_workflows(),
                n8n_connected=True,
            )
            assert result.success is True
            assert result.pages_created == 1
            assert result.blocks_written > 0

    def test_includes_execution_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync, gateway, _ = _make_sync(tmpdir)
            _mock_gateway_success(gateway)
            n8n_sync = NotionN8nSync(sync, _make_audit())
            result = n8n_sync.push_workflow_dashboard(
                workflows=_sample_workflows(),
                executions=_sample_executions(),
                n8n_connected=True,
            )
            assert result.success is True
            assert result.blocks_written > 10  # Should have many blocks with executions

    def test_handles_empty_workflows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync, gateway, _ = _make_sync(tmpdir)
            _mock_gateway_success(gateway)
            n8n_sync = NotionN8nSync(sync, _make_audit())
            result = n8n_sync.push_workflow_dashboard(
                workflows=[],
                n8n_connected=False,
            )
            assert result.success is True

    def test_updates_existing_page_on_second_sync(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync, gateway, _ = _make_sync(tmpdir)
            _mock_gateway_success(gateway)
            n8n_sync = NotionN8nSync(sync, _make_audit())

            # First sync creates pages
            r1 = n8n_sync.push_workflow_dashboard(
                workflows=_sample_workflows(),
                n8n_connected=True,
            )
            assert r1.pages_created == 1

            # Second sync updates (no new pages)
            r2 = n8n_sync.push_workflow_dashboard(
                workflows=_sample_workflows(),
                n8n_connected=True,
            )
            assert r2.pages_updated == 1
            assert r2.pages_created == 0

    def test_disconnected_status_shown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync, gateway, _ = _make_sync(tmpdir)
            _mock_gateway_success(gateway)
            n8n_sync = NotionN8nSync(sync, _make_audit())
            result = n8n_sync.push_workflow_dashboard(
                workflows=_sample_workflows(),
                n8n_connected=False,
            )
            assert result.success is True

    def test_gateway_failure_returns_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync, gateway, _ = _make_sync(tmpdir)
            gateway.request = MagicMock(return_value={
                "success": False,
                "error": "Gateway error",
            })
            n8n_sync = NotionN8nSync(sync, _make_audit())
            result = n8n_sync.push_workflow_dashboard(
                workflows=_sample_workflows(),
                n8n_connected=True,
            )
            assert result.success is False
            assert len(result.errors) > 0


# ---------------------------------------------------------------------------
# GatewayN8nProvider tests
# ---------------------------------------------------------------------------


class TestGatewayN8nProvider:
    def test_has_credentials_when_service_registered(self):
        audit = _make_audit()
        gateway = Gateway(audit=audit)
        gateway.register_service(ServiceConfig(
            name="n8n_workflows",
            base_url="http://localhost:5678",
            require_tls=False,
            rate_limit=RateLimitConfig(max_requests=30, window_seconds=60),
        ))
        provider = GatewayN8nProvider(gateway=gateway)
        assert provider.has_credentials is True

    def test_no_credentials_without_service(self):
        audit = _make_audit()
        gateway = Gateway(audit=audit)
        provider = GatewayN8nProvider(gateway=gateway)
        assert provider.has_credentials is False

    def test_authenticate_fails_without_service(self):
        audit = _make_audit()
        gateway = Gateway(audit=audit)
        provider = GatewayN8nProvider(gateway=gateway)
        assert provider.authenticate() is False
        assert provider.is_authenticated is False

    def test_authenticate_success_with_mock(self):
        audit = _make_audit()
        gateway = Gateway(audit=audit)
        gateway.register_service(ServiceConfig(
            name="n8n_workflows",
            base_url="http://localhost:5678",
            require_tls=False,
        ))
        gateway.request = MagicMock(return_value={
            "success": True,
            "data": {"data": []},
        })
        provider = GatewayN8nProvider(gateway=gateway)
        assert provider.authenticate() is True
        assert provider.is_authenticated is True

    def test_list_workflows_returns_parsed(self):
        audit = _make_audit()
        gateway = Gateway(audit=audit)
        gateway.register_service(ServiceConfig(
            name="n8n_workflows",
            base_url="http://localhost:5678",
            require_tls=False,
        ))
        gateway.request = MagicMock(return_value={
            "success": True,
            "data": {
                "data": [
                    {"id": "1", "name": "Test WF", "active": True, "tags": [],
                     "createdAt": "2026-01-01", "updatedAt": "2026-01-02"},
                ]
            },
        })
        provider = GatewayN8nProvider(gateway=gateway)
        provider._authenticated = True
        wfs = provider.list_workflows()
        assert len(wfs) == 1
        assert wfs[0].name == "Test WF"
        assert wfs[0].active is True

    def test_create_workflow(self):
        audit = _make_audit()
        gateway = Gateway(audit=audit)
        gateway.register_service(ServiceConfig(
            name="n8n_workflows",
            base_url="http://localhost:5678",
            require_tls=False,
        ))
        gateway.request = MagicMock(return_value={
            "success": True,
            "data": {"id": "new-1", "name": "New WF", "active": False, "nodes": []},
        })
        provider = GatewayN8nProvider(gateway=gateway)
        provider._authenticated = True
        wf = provider.create_workflow("New WF", [])
        assert wf is not None
        assert wf.id == "new-1"
        assert wf.name == "New WF"

    def test_execute_workflow(self):
        audit = _make_audit()
        gateway = Gateway(audit=audit)
        gateway.register_service(ServiceConfig(
            name="n8n_workflows",
            base_url="http://localhost:5678",
            require_tls=False,
        ))
        gateway.request = MagicMock(return_value={
            "success": True,
            "data": {"id": "exec-1", "status": "running", "mode": "manual"},
        })
        provider = GatewayN8nProvider(gateway=gateway)
        provider._authenticated = True
        exe = provider.execute_workflow("wf-1", {"key": "value"})
        assert exe is not None
        assert exe.id == "exec-1"
        assert exe.status == "running"

    def test_gateway_failure_returns_none(self):
        audit = _make_audit()
        gateway = Gateway(audit=audit)
        gateway.register_service(ServiceConfig(
            name="n8n_workflows",
            base_url="http://localhost:5678",
            require_tls=False,
        ))
        gateway.request = MagicMock(return_value={
            "success": False,
            "error": "Connection refused",
        })
        provider = GatewayN8nProvider(gateway=gateway)
        provider._authenticated = True
        assert provider.get_workflow("wf-1") is None
        assert provider.list_workflows() == []
