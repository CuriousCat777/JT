"""Notion website dashboard sync — per-site dashboards pushed to Notion.

Creates and maintains separate Notion pages for each managed website
(drjeremytabernero.org, jtmdai.com), providing visibility into build
status, deployment state, page inventory, and security posture.

Follows the same write-only, content-gated architecture as the main
NotionSync engine.  All data passes through classify_content() before
leaving the system.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.integrations.notion_sync import (
    NotionSync,
    NotionPage,
    SyncResult,
    classify_content,
)


class NotionWebsiteDashboard:
    """Push per-site website dashboards to Notion.

    Creates a "Website Management" parent page under the Notion root,
    then a sub-page for each managed domain.  Each sub-page contains:
        - Site overview (type, label, hosting)
        - Page inventory table
        - Build history
        - Security & SSL status
        - Feature list

    Usage:
        dashboard = NotionWebsiteDashboard(notion_sync, audit)
        result = dashboard.push_site_dashboard(site_data)
        result = dashboard.push_sites_overview(all_sites_data)
    """

    def __init__(self, notion_sync: NotionSync, audit: AuditLog) -> None:
        self._sync = notion_sync
        self._audit = audit
        self._parent_page_id: str = ""  # "Website Management" parent page

    # ------------------------------------------------------------------
    # Parent page management
    # ------------------------------------------------------------------

    def _ensure_parent_page(self) -> str | None:
        """Create or return the 'Website Management' parent page."""
        if self._parent_page_id:
            return self._parent_page_id

        cache_key = "website_management"
        cached = self._sync._page_cache.get(cache_key)
        if cached:
            self._parent_page_id = cached.page_id
            return self._parent_page_id

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        children = [
            self._sync._callout(
                f"Website Management Hub | Last sync: {now}",
                "#",
            ),
            self._sync._paragraph(
                "Dashboards for all managed web properties. "
                "Each site has its own sub-page with build status, "
                "security posture, and deployment history."
            ),
            self._sync._divider(),
        ]

        resp = self._sync._create_page(
            self._sync._root_page_id,
            "Website Management",
            icon_emoji="🌐",
            children=children,
        )

        if resp.get("success") and resp.get("data"):
            page_id = resp["data"].get("id", "")
            self._parent_page_id = page_id
            self._sync._page_cache[cache_key] = NotionPage(
                page_id=page_id,
                title="Website Management",
                parent_id=self._sync._root_page_id,
                page_type="dashboard",
                last_synced=now,
                guardian_key=cache_key,
            )
            return page_id

        return None

    # ------------------------------------------------------------------
    # Per-site dashboard
    # ------------------------------------------------------------------

    def push_site_dashboard(self, site_data: dict[str, Any]) -> SyncResult:
        """Push or update a dashboard page for a single website.

        Args:
            site_data: Dict from WebsiteManager.site_dashboard_data() with keys:
                domain, label, site_type, page_count, pages, features,
                deployed, last_deployed, ssl_enabled, security_passed,
                total_builds, last_build_status, hosting.
        """
        start = time.monotonic()
        result = SyncResult(success=False)

        # Content gate
        text = json.dumps(site_data, default=str)
        if not classify_content(text, "agent_status"):
            result.errors.append("Content blocked by classification gate")
            return result

        parent_id = self._ensure_parent_page()
        if not parent_id:
            result.errors.append("Failed to create Website Management parent page")
            result.duration_ms = (time.monotonic() - start) * 1000
            return result

        domain = str(site_data.get("domain", "unknown"))
        label = str(site_data.get("label", domain))
        site_type = str(site_data.get("site_type", "general"))
        deployed = site_data.get("deployed", False)
        ssl = site_data.get("ssl_enabled", False)
        security = site_data.get("security_passed", False)
        hosting = str(site_data.get("hosting", "tbd"))
        builds = site_data.get("total_builds", 0)
        last_build = str(site_data.get("last_build_status", "none"))
        last_deployed = str(site_data.get("last_deployed", "never"))
        pages = site_data.get("pages", [])
        features = site_data.get("features", [])

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        # Status indicators
        deploy_status = "LIVE" if deployed else "NOT DEPLOYED"
        ssl_status = "Valid" if ssl else "Not configured"
        sec_status = "Passed" if security else "Needs scan"

        children = [
            self._sync._callout(
                f"{deploy_status} | SSL: {ssl_status} | Security: {sec_status}",
                "#" if deployed else "!",
            ),
            self._sync._heading("Site Overview", 2),
            self._sync._bulleted(f"Domain: {domain}"),
            self._sync._bulleted(f"Type: {site_type}"),
            self._sync._bulleted(f"Hosting: {hosting}"),
            self._sync._bulleted(f"Last deployed: {last_deployed}"),
            self._sync._divider(),

            self._sync._heading("Pages", 2),
        ]

        for page_name in pages:
            children.append(self._sync._bulleted(page_name))

        children.extend([
            self._sync._divider(),
            self._sync._heading("Features", 2),
        ])

        for feat in features:
            children.append(self._sync._bulleted(feat))

        children.extend([
            self._sync._divider(),
            self._sync._heading("Build & Deploy", 2),
            self._sync._bulleted(f"Total builds: {builds}"),
            self._sync._bulleted(f"Last build status: {last_build}"),
            self._sync._bulleted(f"SSL enabled: {ssl_status}"),
            self._sync._bulleted(f"Security scan: {sec_status}"),
            self._sync._divider(),
            self._sync._paragraph(f"Last synced: {now}"),
        ])

        cache_key = f"site_dashboard_{domain}"
        cached = self._sync._page_cache.get(cache_key)

        if cached:
            resp = self._sync._append_blocks(cached.page_id, children)
        else:
            resp = self._sync._create_page(
                parent_id,
                f"{label} ({domain})",
                icon_emoji="🌐",
                children=children,
            )

        if resp.get("success") and resp.get("data"):
            page_id = resp["data"].get("id", "")
            if page_id and not cached:
                self._sync._page_cache[cache_key] = NotionPage(
                    page_id=page_id,
                    title=f"{label} ({domain})",
                    parent_id=parent_id,
                    page_type="dashboard",
                    last_synced=now,
                    guardian_key=cache_key,
                )
            result.success = True
            result.pages_created = 0 if cached else 1
            result.pages_updated = 1 if cached else 0
            result.blocks_written = len(children)
        else:
            error = resp.get("error", "Unknown error")
            result.errors.append(error)
            self._audit.record(
                agent="notion_website_sync",
                action=f"sync_failed:{domain}",
                severity=Severity.ERROR,
                details={"error": error, "domain": domain},
            )

        result.duration_ms = (time.monotonic() - start) * 1000
        return result

    # ------------------------------------------------------------------
    # Overview page (all sites summary)
    # ------------------------------------------------------------------

    def push_sites_overview(
        self, sites_data: dict[str, dict[str, Any]]
    ) -> SyncResult:
        """Push a summary overview of all managed websites.

        Args:
            sites_data: Dict mapping domain -> site_dashboard_data.
        """
        start = time.monotonic()
        result = SyncResult(success=False)

        text = json.dumps(list(sites_data.values()), default=str)
        if not classify_content(text, "agent_status"):
            result.errors.append("Content blocked by classification gate")
            return result

        parent_id = self._ensure_parent_page()
        if not parent_id:
            result.errors.append("Failed to create Website Management parent page")
            result.duration_ms = (time.monotonic() - start) * 1000
            return result

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        total_sites = len(sites_data)
        live_count = sum(1 for s in sites_data.values() if s.get("deployed"))

        children = [
            self._sync._callout(
                f"{live_count}/{total_sites} sites live | Last sync: {now}",
                "#",
            ),
            self._sync._heading("Managed Websites", 2),
        ]

        for domain, data in sites_data.items():
            label = str(data.get("label", domain))
            deployed = data.get("deployed", False)
            status = "LIVE" if deployed else "NOT DEPLOYED"
            pages = data.get("page_count", 0)
            builds = data.get("total_builds", 0)

            children.append(self._sync._heading(f"{label}", 3))
            children.append(self._sync._bulleted(f"Domain: {domain}"))
            children.append(self._sync._bulleted(f"Status: {status}"))
            children.append(self._sync._bulleted(f"Pages: {pages}"))
            children.append(self._sync._bulleted(f"Builds: {builds}"))

        children.append(self._sync._divider())
        children.append(self._sync._paragraph(f"Last synced: {now}"))

        cache_key = "websites_overview"
        cached = self._sync._page_cache.get(cache_key)

        if cached:
            resp = self._sync._append_blocks(cached.page_id, children)
        else:
            resp = self._sync._create_page(
                parent_id,
                "Sites Overview",
                icon_emoji="🌐",
                children=children,
            )

        if resp.get("success") and resp.get("data"):
            page_id = resp["data"].get("id", "")
            if page_id and not cached:
                self._sync._page_cache[cache_key] = NotionPage(
                    page_id=page_id,
                    title="Sites Overview",
                    parent_id=parent_id,
                    page_type="dashboard",
                    last_synced=now,
                    guardian_key=cache_key,
                )
            result.success = True
            result.pages_created = 0 if cached else 1
            result.pages_updated = 1 if cached else 0
            result.blocks_written = len(children)
        else:
            error = resp.get("error", "Unknown error")
            result.errors.append(error)

        result.duration_ms = (time.monotonic() - start) * 1000
        return result

    # ------------------------------------------------------------------
    # Full sync: push all site dashboards + overview
    # ------------------------------------------------------------------

    def sync_all(
        self, sites_data: dict[str, dict[str, Any]]
    ) -> dict[str, SyncResult]:
        """Push dashboards for all sites plus the overview page.

        Args:
            sites_data: Dict mapping domain -> site_dashboard_data.

        Returns:
            Dict mapping domain|"overview" -> SyncResult.
        """
        results: dict[str, SyncResult] = {}

        for domain, data in sites_data.items():
            results[domain] = self.push_site_dashboard(data)

        results["overview"] = self.push_sites_overview(sites_data)

        self._audit.record(
            agent="notion_website_sync",
            action="sync_all_complete",
            severity=Severity.INFO,
            details={
                "sites_synced": len(sites_data),
                "successes": sum(1 for r in results.values() if r.success),
                "failures": sum(1 for r in results.values() if not r.success),
            },
        )

        return results
