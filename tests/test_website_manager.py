"""Tests for WebsiteManager — per-site build/deploy pipelines."""

import tempfile
from pathlib import Path

from guardian_one.core.audit import AuditLog
from guardian_one.core.config import AgentConfig
from guardian_one.agents.website_manager import (
    ManagedSite,
    SiteBuild,
    SitePage,
    WebsiteManager,
    _page_title,
)


def _make_audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


def _make_config() -> AgentConfig:
    return AgentConfig(
        name="web_architect",
        enabled=True,
        schedule_interval_minutes=30,
        allowed_resources=["n8n_workflows", "deployments"],
        custom={
            "domains": ["drjeremytabernero.org", "jtmdai.com"],
            "sites": {
                "drjeremytabernero.org": {
                    "label": "Dr. Jeremy Tabernero — Personal & Professional",
                    "site_type": "professional",
                    "pages": ["index.html", "about.html", "contact.html", "cv.html"],
                    "features": ["contact_form", "cv_download"],
                    "hosting": "tbd",
                    "notion_dashboard": True,
                },
                "jtmdai.com": {
                    "label": "JTMD AI — AI Solutions & Technology",
                    "site_type": "business",
                    "pages": ["index.html", "about.html", "services.html", "contact.html"],
                    "features": ["service_catalog", "contact_form", "ai_demos"],
                    "hosting": "tbd",
                    "notion_dashboard": True,
                },
            },
        },
    )


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestInitialization:
    def test_loads_both_sites(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        assert set(mgr.list_sites()) == {"drjeremytabernero.org", "jtmdai.com"}

    def test_site_labels(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        dr = mgr.get_site("drjeremytabernero.org")
        jt = mgr.get_site("jtmdai.com")
        assert dr is not None
        assert jt is not None
        assert "Jeremy" in dr.label
        assert "JTMD" in jt.label

    def test_site_pages_loaded(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        dr = mgr.get_site("drjeremytabernero.org")
        assert len(dr.pages) == 4
        assert dr.pages[0].filename == "index.html"

    def test_site_features_loaded(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        jt = mgr.get_site("jtmdai.com")
        assert "ai_demos" in jt.features

    def test_unknown_site_returns_none(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        assert mgr.get_site("notexist.com") is None

    def test_empty_config(self):
        cfg = AgentConfig(name="web_architect", custom={"domains": [], "sites": {}})
        mgr = WebsiteManager(cfg, _make_audit())
        mgr.initialize()
        assert mgr.list_sites() == []


# ---------------------------------------------------------------------------
# Build pipeline
# ---------------------------------------------------------------------------

class TestBuild:
    def test_build_single_site(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        build = mgr.build_site("drjeremytabernero.org")
        assert build.status == "success"
        assert len(build.pages_built) == 4
        assert "index.html" in build.pages_built

    def test_build_sets_page_status(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        mgr.build_site("jtmdai.com")
        site = mgr.get_site("jtmdai.com")
        for page in site.pages:
            assert page.status == "built"
            assert page.last_built != ""

    def test_build_unknown_domain(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        build = mgr.build_site("nonexistent.com")
        assert build.status == "failed"
        assert len(build.errors) > 0

    def test_build_all(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        results = mgr.build_all()
        assert len(results) == 2
        for build in results.values():
            assert build.status == "success"

    def test_build_increments_counter(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        b1 = mgr.build_site("jtmdai.com")
        b2 = mgr.build_site("jtmdai.com")
        assert b1.build_id != b2.build_id

    def test_build_history_tracked(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        mgr.build_site("drjeremytabernero.org")
        mgr.build_site("drjeremytabernero.org")
        site = mgr.get_site("drjeremytabernero.org")
        assert len(site.builds) == 2


# ---------------------------------------------------------------------------
# Deploy pipeline
# ---------------------------------------------------------------------------

class TestDeploy:
    def test_deploy_after_build(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        mgr.build_site("jtmdai.com")
        result = mgr.deploy_site("jtmdai.com")
        assert result["success"] is True
        assert result["ssl_enabled"] is True
        assert result["pages_deployed"] == 4

    def test_deploy_without_build_fails(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        result = mgr.deploy_site("jtmdai.com")
        assert result["success"] is False
        assert "build" in result["error"].lower()

    def test_deploy_unknown_domain(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        result = mgr.deploy_site("nope.com")
        assert result["success"] is False

    def test_deploy_sets_site_state(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        mgr.build_site("drjeremytabernero.org")
        mgr.deploy_site("drjeremytabernero.org")
        site = mgr.get_site("drjeremytabernero.org")
        assert site.deployed is True
        assert site.ssl_enabled is True
        assert site.security_passed is True
        assert site.last_deployed != ""

    def test_deploy_all(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        mgr.build_all()
        results = mgr.deploy_all()
        for result in results.values():
            assert result["success"] is True

    def test_page_status_after_deploy(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        mgr.build_site("jtmdai.com")
        mgr.deploy_site("jtmdai.com")
        site = mgr.get_site("jtmdai.com")
        for page in site.pages:
            assert page.status == "deployed"


# ---------------------------------------------------------------------------
# Status / dashboard data
# ---------------------------------------------------------------------------

class TestStatus:
    def test_site_status(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        mgr.build_site("jtmdai.com")
        mgr.deploy_site("jtmdai.com")
        status = mgr.site_status("jtmdai.com")
        assert status["deployed"] is True
        assert status["ssl_enabled"] is True
        assert status["total_builds"] == 1

    def test_all_sites_status(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        status = mgr.all_sites_status()
        assert len(status) == 2
        assert "drjeremytabernero.org" in status

    def test_dashboard_data_notion_safe(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        mgr.build_site("drjeremytabernero.org")
        data = mgr.site_dashboard_data("drjeremytabernero.org")
        assert data["domain"] == "drjeremytabernero.org"
        assert data["page_count"] == 4
        assert isinstance(data["pages"], list)
        assert isinstance(data["features"], list)

    def test_dashboard_data_unknown(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        data = mgr.site_dashboard_data("nope.com")
        assert "error" in data

    def test_summary_text(self):
        mgr = WebsiteManager(_make_config(), _make_audit())
        mgr.initialize()
        text = mgr.summary()
        assert "drjeremytabernero.org" in text
        assert "jtmdai.com" in text
        assert "2 site(s)" in text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_page_title_simple(self):
        assert _page_title("index.html") == "Index"

    def test_page_title_hyphenated(self):
        assert _page_title("case-studies.html") == "Case Studies"

    def test_page_title_underscored(self):
        assert _page_title("my_page.html") == "My Page"
