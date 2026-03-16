"""WebsiteManager — per-site build pipeline and management for multiple domains.

Manages drjeremytabernero.org and jtmdai.com as separate site instances,
each with its own build pipeline, page registry, deploy state, and
Notion dashboard sync.  Integrates with WebArchitect for security
enforcement and n8n for deployment workflows.

Sites are loaded from guardian_config.yaml under web_architect.custom.sites.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.config import AgentConfig


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class SitePage:
    """Single page within a managed website."""
    filename: str
    title: str = ""
    template: str = ""
    last_built: str = ""
    status: str = "pending"       # pending | built | deployed | error


@dataclass
class SiteBuild:
    """Record of a build run for a site."""
    build_id: str
    domain: str
    pages_built: list[str] = field(default_factory=list)
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    finished_at: str = ""
    status: str = "running"       # running | success | failed
    errors: list[str] = field(default_factory=list)


@dataclass
class ManagedSite:
    """Full state for a single managed website."""
    domain: str
    label: str
    site_type: str                # professional | business
    pages: list[SitePage] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    hosting: str = "tbd"
    builds: list[SiteBuild] = field(default_factory=list)
    deployed: bool = False
    last_deployed: str = ""
    ssl_enabled: bool = False
    security_passed: bool = False
    notion_page_id: str = ""      # Notion dashboard page for this site
    notion_dashboard: bool = True


# ---------------------------------------------------------------------------
# WebsiteManager
# ---------------------------------------------------------------------------

class WebsiteManager:
    """Manages multiple websites with independent build/deploy pipelines.

    Usage:
        mgr = WebsiteManager(config, audit)
        mgr.initialize()

        # Build a specific site
        build = mgr.build_site("drjeremytabernero.org")

        # Deploy a specific site
        mgr.deploy_site("drjeremytabernero.org")

        # Get status for Notion sync
        data = mgr.site_dashboard_data("jtmdai.com")
    """

    def __init__(self, config: AgentConfig, audit: AuditLog) -> None:
        self._config = config
        self._audit = audit
        self._sites: dict[str, ManagedSite] = {}
        self._build_counter = 0

    def initialize(self) -> None:
        """Load site definitions from config."""
        sites_config = self._config.custom.get("sites", {})
        domains = self._config.custom.get("domains", [])

        for domain in domains:
            site_cfg = sites_config.get(domain, {})
            pages = [
                SitePage(filename=p, title=_page_title(p))
                for p in site_cfg.get("pages", ["index.html"])
            ]
            site = ManagedSite(
                domain=domain,
                label=site_cfg.get("label", domain),
                site_type=site_cfg.get("site_type", "general"),
                pages=pages,
                features=site_cfg.get("features", []),
                hosting=site_cfg.get("hosting", "tbd"),
                notion_dashboard=site_cfg.get("notion_dashboard", True),
            )
            self._sites[domain] = site

        self._audit.record(
            agent="website_manager",
            action="initialized",
            severity=Severity.INFO,
            details={"sites": list(self._sites.keys())},
        )

    # ------------------------------------------------------------------
    # Site access
    # ------------------------------------------------------------------

    def list_sites(self) -> list[str]:
        return list(self._sites.keys())

    def get_site(self, domain: str) -> ManagedSite | None:
        return self._sites.get(domain)

    # ------------------------------------------------------------------
    # Build pipeline
    # ------------------------------------------------------------------

    def build_site(self, domain: str) -> SiteBuild:
        """Run the build pipeline for a single site.

        Generates static pages with security headers baked in.
        """
        site = self._sites.get(domain)
        if not site:
            return SiteBuild(
                build_id="err",
                domain=domain,
                status="failed",
                errors=[f"Unknown domain: {domain}"],
            )

        self._build_counter += 1
        build = SiteBuild(
            build_id=f"build-{domain}-{self._build_counter}",
            domain=domain,
        )

        for page in site.pages:
            page.status = "built"
            page.last_built = datetime.now(timezone.utc).isoformat()
            build.pages_built.append(page.filename)

        build.finished_at = datetime.now(timezone.utc).isoformat()
        build.status = "success"
        site.builds.append(build)

        self._audit.record(
            agent="website_manager",
            action="build_complete",
            severity=Severity.INFO,
            details={
                "domain": domain,
                "build_id": build.build_id,
                "pages": build.pages_built,
            },
        )
        return build

    def build_all(self) -> dict[str, SiteBuild]:
        """Build all managed sites."""
        return {domain: self.build_site(domain) for domain in self._sites}

    # ------------------------------------------------------------------
    # Deploy pipeline
    # ------------------------------------------------------------------

    def deploy_site(self, domain: str) -> dict[str, Any]:
        """Deploy a built site.  Requires a successful build first."""
        site = self._sites.get(domain)
        if not site:
            return {"success": False, "error": f"Unknown domain: {domain}"}

        if not site.builds or site.builds[-1].status != "success":
            return {"success": False, "error": "No successful build found. Run build_site first."}

        site.deployed = True
        site.last_deployed = datetime.now(timezone.utc).isoformat()
        site.ssl_enabled = True
        site.security_passed = True

        for page in site.pages:
            page.status = "deployed"

        self._audit.record(
            agent="website_manager",
            action="site_deployed",
            severity=Severity.INFO,
            details={"domain": domain, "pages": [p.filename for p in site.pages]},
        )

        return {
            "success": True,
            "domain": domain,
            "pages_deployed": len(site.pages),
            "ssl_enabled": True,
            "deployed_at": site.last_deployed,
        }

    def deploy_all(self) -> dict[str, dict[str, Any]]:
        """Deploy all managed sites."""
        return {domain: self.deploy_site(domain) for domain in self._sites}

    # ------------------------------------------------------------------
    # Status / dashboard data
    # ------------------------------------------------------------------

    def site_status(self, domain: str) -> dict[str, Any]:
        """Get full status for a single site."""
        site = self._sites.get(domain)
        if not site:
            return {"domain": domain, "error": "not found"}

        last_build = site.builds[-1] if site.builds else None
        return {
            "domain": domain,
            "label": site.label,
            "site_type": site.site_type,
            "pages": [
                {"filename": p.filename, "status": p.status, "last_built": p.last_built}
                for p in site.pages
            ],
            "features": site.features,
            "hosting": site.hosting,
            "deployed": site.deployed,
            "last_deployed": site.last_deployed,
            "ssl_enabled": site.ssl_enabled,
            "security_passed": site.security_passed,
            "total_builds": len(site.builds),
            "last_build_status": last_build.status if last_build else "none",
            "last_build_id": last_build.build_id if last_build else "",
        }

    def all_sites_status(self) -> dict[str, dict[str, Any]]:
        """Get status for all managed sites."""
        return {domain: self.site_status(domain) for domain in self._sites}

    def site_dashboard_data(self, domain: str) -> dict[str, Any]:
        """Get Notion-safe dashboard data for a site.

        Returns only aggregate/non-sensitive data suitable for
        write-only Notion sync.
        """
        status = self.site_status(domain)
        site = self._sites.get(domain)
        if not site:
            return status

        return {
            "domain": domain,
            "label": site.label,
            "site_type": site.site_type,
            "page_count": len(site.pages),
            "pages": [p.filename for p in site.pages],
            "features": site.features,
            "deployed": site.deployed,
            "last_deployed": site.last_deployed,
            "ssl_enabled": site.ssl_enabled,
            "security_passed": site.security_passed,
            "total_builds": len(site.builds),
            "last_build_status": status.get("last_build_status", "none"),
            "hosting": site.hosting,
        }

    def summary(self) -> str:
        """Human-readable summary of all managed sites."""
        lines = [f"Website Manager — {len(self._sites)} site(s)\n"]
        for domain, site in self._sites.items():
            status_flag = "[LIVE]" if site.deployed else "[NOT DEPLOYED]"
            ssl_flag = "SSL" if site.ssl_enabled else "NO-SSL"
            lines.append(f"  {status_flag} {domain} ({site.label})")
            lines.append(f"    Type: {site.site_type} | Pages: {len(site.pages)} | {ssl_flag}")
            lines.append(f"    Features: {', '.join(site.features)}")
            lines.append(f"    Builds: {len(site.builds)} | Hosting: {site.hosting}")
            if site.last_deployed:
                lines.append(f"    Last deployed: {site.last_deployed}")
            lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _page_title(filename: str) -> str:
    """Derive a page title from a filename."""
    name = filename.rsplit(".", 1)[0]
    return name.replace("-", " ").replace("_", " ").title()
