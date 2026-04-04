"""Notion-n8n bridge — push n8n workflow status to Notion dashboards.

Syncs n8n workflow inventory, execution history, and health metrics
to a dedicated Notion dashboard page.  Follows the same write-only,
content-gated architecture as NotionSync and NotionWebsiteDashboard.

This bridges the gap between the n8n automation engine (used by
WebArchitect for website builds/deploys/scans) and the Notion
workspace (used for operational visibility).
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.integrations.n8n_sync import (
    N8nProvider,
    N8nWorkflow,
    N8nExecution,
)
from guardian_one.integrations.notion_sync import (
    NotionSync,
    NotionPage,
    SyncResult,
    classify_content,
)


class NotionN8nSync:
    """Push n8n workflow status and execution history to Notion.

    Creates an "n8n Workflows" parent page under the Notion root,
    with sub-sections for:
        - Workflow inventory (name, active/inactive, tags)
        - Recent executions (status, timing, mode)
        - Health summary (success rate, active count)

    Usage:
        sync = NotionN8nSync(notion_sync, audit)
        result = sync.push_workflow_dashboard(workflows, executions)
    """

    def __init__(self, notion_sync: NotionSync, audit: AuditLog) -> None:
        self._sync = notion_sync
        self._audit = audit
        self._parent_page_id: str = ""

    # ------------------------------------------------------------------
    # Parent page management
    # ------------------------------------------------------------------

    def _ensure_parent_page(self) -> str | None:
        """Create or return the 'n8n Workflows' parent page."""
        if self._parent_page_id:
            return self._parent_page_id

        cache_key = "n8n_workflows"
        cached = self._sync._page_cache.get(cache_key)
        if cached:
            self._parent_page_id = cached.page_id
            return self._parent_page_id

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        children = [
            self._sync._callout(
                f"n8n Workflow Dashboard | Last sync: {now}",
                "\u2699\ufe0f",
            ),
            self._sync._paragraph(
                "Automation workflow status for Guardian One. "
                "Covers website builds, security scans, uptime monitors, "
                "and custom automations managed via n8n."
            ),
            self._sync._divider(),
        ]

        resp = self._sync._create_page(
            self._sync._root_page_id,
            "n8n Workflows",
            icon_emoji="\u2699\ufe0f",
            children=children,
        )

        if resp.get("success") and resp.get("data"):
            page_id = resp["data"].get("id", "")
            self._parent_page_id = page_id
            self._sync._page_cache[cache_key] = NotionPage(
                page_id=page_id,
                title="n8n Workflows",
                parent_id=self._sync._root_page_id,
                page_type="dashboard",
                last_synced=now,
                guardian_key=cache_key,
            )
            return page_id

        return None

    # ------------------------------------------------------------------
    # Workflow dashboard
    # ------------------------------------------------------------------

    def push_workflow_dashboard(
        self,
        workflows: list[N8nWorkflow],
        executions: list[N8nExecution] | None = None,
        n8n_connected: bool = False,
    ) -> SyncResult:
        """Push the n8n workflow dashboard to Notion.

        Args:
            workflows: List of N8nWorkflow objects from the provider.
            executions: Optional list of recent N8nExecution results.
            n8n_connected: Whether the n8n API is currently reachable.
        """
        start = time.monotonic()
        result = SyncResult(success=False)
        executions = executions or []

        # Content gate — serialize workflow metadata (no secrets)
        safe_data = [
            {"id": w.id, "name": w.name, "active": w.active, "tags": w.tags}
            for w in workflows
        ]
        text = json.dumps(safe_data, default=str)
        if not classify_content(text, "integration_health"):
            result.errors.append("Content blocked by classification gate")
            return result

        parent_id = self._ensure_parent_page()
        if not parent_id:
            result.errors.append("Failed to create n8n Workflows parent page")
            result.duration_ms = (time.monotonic() - start) * 1000
            return result

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        # Compute stats
        total = len(workflows)
        active_count = sum(1 for w in workflows if w.active)
        exec_success = sum(1 for e in executions if e.status == "success")
        exec_error = sum(1 for e in executions if e.status == "error")
        exec_total = len(executions)

        # Connection status
        conn_icon = "\U0001f7e2" if n8n_connected else "\U0001f534"
        conn_text = "Connected" if n8n_connected else "Disconnected"

        children = [
            self._sync._callout(
                f"n8n: {conn_text} | {active_count}/{total} workflows active | "
                f"Last sync: {now}",
                conn_icon,
            ),
        ]

        # Health summary
        children.append(self._sync._heading("Health Summary", 2))
        children.append(self._sync._bulleted(f"Connection: {conn_text}"))
        children.append(self._sync._bulleted(
            f"Workflows: {total} total, {active_count} active"
        ))
        if exec_total > 0:
            success_rate = (exec_success / exec_total) * 100
            children.append(self._sync._bulleted(
                f"Executions: {exec_total} recent "
                f"({exec_success} success, {exec_error} error, "
                f"{success_rate:.0f}% success rate)"
            ))
        else:
            children.append(self._sync._bulleted("Executions: no recent data"))

        # Workflow inventory
        children.append(self._sync._divider())
        children.append(self._sync._heading("Workflow Inventory", 2))

        if not workflows:
            children.append(self._sync._paragraph(
                "No workflows registered. Use WebArchitect to create site workflows."
            ))
        else:
            for wf in workflows:
                status_icon = "\U0001f7e2" if wf.active else "\u26aa"
                status_text = "Active" if wf.active else "Inactive"
                tags_text = f" [{', '.join(wf.tags)}]" if wf.tags else ""
                children.append(self._sync._bulleted(
                    f"{status_icon} {wf.name} — {status_text}{tags_text}"
                ))
                if wf.updated_at:
                    children.append(self._sync._bulleted(
                        f"  Last updated: {wf.updated_at}"
                    ))

        # Recent executions
        if executions:
            children.append(self._sync._divider())
            children.append(self._sync._heading("Recent Executions", 2))

            for exe in executions[:20]:  # Cap at 20 most recent
                if exe.status == "success":
                    icon = "\u2705"
                elif exe.status == "error":
                    icon = "\u274c"
                elif exe.status == "running":
                    icon = "\u23f3"
                else:
                    icon = "\u2b1c"

                mode_text = f" ({exe.mode})" if exe.mode != "manual" else ""
                children.append(self._sync._bulleted(
                    f"{icon} Workflow {exe.workflow_id}: {exe.status}{mode_text}"
                ))
                if exe.started_at:
                    children.append(self._sync._bulleted(
                        f"  Started: {exe.started_at}"
                    ))

        # Website integration note
        children.append(self._sync._divider())
        children.append(self._sync._heading("Website Integration", 2))
        children.append(self._sync._paragraph(
            "n8n workflows are managed by the WebArchitect agent for website "
            "builds, security scans, and uptime monitoring. See Website Management "
            "dashboard for per-site deployment status."
        ))

        children.append(self._sync._divider())
        children.append(self._sync._paragraph(f"Last synced: {now}"))

        # Upsert the page
        cache_key = "n8n_dashboard"
        cached = self._sync._page_cache.get(cache_key)

        if cached:
            resp = self._sync._replace_blocks(cached.page_id, children)
        else:
            resp = self._sync._create_page(
                parent_id,
                "Workflow Status",
                icon_emoji="\u2699\ufe0f",
                children=children,
            )

        if resp.get("success") and resp.get("data"):
            page_id = resp["data"].get("id", "")
            if page_id and not cached:
                self._sync._page_cache[cache_key] = NotionPage(
                    page_id=page_id,
                    title="Workflow Status",
                    parent_id=parent_id,
                    page_type="dashboard",
                    last_synced=now,
                    guardian_key=cache_key,
                )
            result.success = True
            result.pages_created = 0 if cached else 1
            result.pages_updated = 1 if cached else 0
            result.blocks_written = len(children)

            self._audit.record(
                agent="notion_n8n_sync",
                action="dashboard_synced",
                severity=Severity.INFO,
                details={
                    "workflows": total,
                    "active": active_count,
                    "executions": exec_total,
                },
            )
        else:
            error = resp.get("error", "Unknown error")
            result.errors.append(error)
            self._audit.record(
                agent="notion_n8n_sync",
                action="sync_failed",
                severity=Severity.ERROR,
                details={"error": error},
            )

        result.duration_ms = (time.monotonic() - start) * 1000
        return result
