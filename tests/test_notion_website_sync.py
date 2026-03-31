"""Tests for NotionWebsiteDashboard — per-site Notion sync."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from guardian_one.core.audit import AuditLog
from guardian_one.homelink.vault import Vault
from guardian_one.homelink.gateway import Gateway, ServiceConfig, RateLimitConfig
from guardian_one.integrations.notion_sync import NotionSync, SyncResult
from guardian_one.integrations.notion_website_sync import NotionWebsiteDashboard


def _make_audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


def _make_sync(tmpdir: str) -> tuple[NotionSync, Gateway, Vault]:
    audit = _make_audit()
    vault = Vault(Path(tmpdir) / "vault.enc", passphrase="test-passphrase!!")
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


def _sample_site_data(domain: str = "jtmdai.com") -> dict:
    return {
        "domain": domain,
        "label": "JTMD AI — AI Solutions & Technology",
        "site_type": "business",
        "page_count": 4,
        "pages": ["index.html", "about.html", "services.html", "contact.html"],
        "features": ["service_catalog", "contact_form", "ai_demos"],
        "deployed": True,
        "last_deployed": "2026-03-16T00:00:00+00:00",
        "ssl_enabled": True,
        "security_passed": True,
        "total_builds": 3,
        "last_build_status": "success",
        "hosting": "tbd",
    }


# ---------------------------------------------------------------------------
# Per-site dashboard push
# ---------------------------------------------------------------------------

class TestPushSiteDashboard:
    def test_creates_parent_and_site_page(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync, gateway, _ = _make_sync(tmpdir)
            _mock_gateway_success(gateway)
            dashboard = NotionWebsiteDashboard(sync, _make_audit())
            result = dashboard.push_site_dashboard(_sample_site_data())
            assert result.success is True
            assert result.pages_created == 1
            assert result.blocks_written > 0

    def test_caches_parent_page(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync, gateway, _ = _make_sync(tmpdir)
            _mock_gateway_success(gateway)
            dashboard = NotionWebsiteDashboard(sync, _make_audit())
            dashboard.push_site_dashboard(_sample_site_data("drjeremytabernero.org"))
            # Second push should reuse the parent
            dashboard.push_site_dashboard(_sample_site_data("jtmdai.com"))
            assert dashboard._parent_page_id != ""

    def test_updates_cached_site_page(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync, gateway, _ = _make_sync(tmpdir)
            _mock_gateway_success(gateway)
            dashboard = NotionWebsiteDashboard(sync, _make_audit())
            r1 = dashboard.push_site_dashboard(_sample_site_data())
            r2 = dashboard.push_site_dashboard(_sample_site_data())
            assert r1.pages_created == 1
            assert r2.pages_updated == 1

    def test_content_gate_blocks_phi(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync, gateway, _ = _make_sync(tmpdir)
            _mock_gateway_success(gateway)
            dashboard = NotionWebsiteDashboard(sync, _make_audit())
            data = _sample_site_data()
            # Inject a SSN pattern
            data["label"] = "Site 123-45-6789"
            result = dashboard.push_site_dashboard(data)
            assert result.success is False
            assert "classification" in result.errors[0].lower()

    def test_handles_gateway_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync, gateway, _ = _make_sync(tmpdir)
            gateway.request = MagicMock(return_value={
                "success": False,
                "error": "connection refused",
            })
            dashboard = NotionWebsiteDashboard(sync, _make_audit())
            result = dashboard.push_site_dashboard(_sample_site_data())
            assert result.success is False


# ---------------------------------------------------------------------------
# Overview page push
# ---------------------------------------------------------------------------

class TestPushOverview:
    def test_creates_overview(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync, gateway, _ = _make_sync(tmpdir)
            _mock_gateway_success(gateway)
            dashboard = NotionWebsiteDashboard(sync, _make_audit())
            sites = {
                "drjeremytabernero.org": _sample_site_data("drjeremytabernero.org"),
                "jtmdai.com": _sample_site_data("jtmdai.com"),
            }
            result = dashboard.push_sites_overview(sites)
            assert result.success is True
            assert result.blocks_written > 0

    def test_overview_updates_on_second_push(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync, gateway, _ = _make_sync(tmpdir)
            _mock_gateway_success(gateway)
            dashboard = NotionWebsiteDashboard(sync, _make_audit())
            sites = {"jtmdai.com": _sample_site_data()}
            r1 = dashboard.push_sites_overview(sites)
            r2 = dashboard.push_sites_overview(sites)
            assert r1.pages_created == 1
            assert r2.pages_updated == 1


# ---------------------------------------------------------------------------
# Full sync
# ---------------------------------------------------------------------------

class TestSyncAll:
    def test_syncs_all_sites_plus_overview(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync, gateway, _ = _make_sync(tmpdir)
            _mock_gateway_success(gateway)
            dashboard = NotionWebsiteDashboard(sync, _make_audit())
            sites = {
                "drjeremytabernero.org": _sample_site_data("drjeremytabernero.org"),
                "jtmdai.com": _sample_site_data("jtmdai.com"),
            }
            results = dashboard.sync_all(sites)
            assert len(results) == 3  # 2 sites + overview
            assert results["overview"].success is True
            assert results["drjeremytabernero.org"].success is True
            assert results["jtmdai.com"].success is True

    def test_partial_failure_still_returns_all(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync, gateway, _ = _make_sync(tmpdir)
            call_count = {"n": 0}
            def flaky_request(**kwargs):
                call_count["n"] += 1
                if call_count["n"] == 3:
                    return {"success": False, "error": "timeout"}
                return {"success": True, "data": {"id": f"p-{call_count['n']}"}}
            gateway.request = MagicMock(side_effect=flaky_request)

            dashboard = NotionWebsiteDashboard(sync, _make_audit())
            sites = {
                "drjeremytabernero.org": _sample_site_data("drjeremytabernero.org"),
                "jtmdai.com": _sample_site_data("jtmdai.com"),
            }
            results = dashboard.sync_all(sites)
            assert len(results) == 3
