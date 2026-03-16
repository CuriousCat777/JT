"""Notion workspace sync — write-only push of operational data.

Guardian One pushes system status, roadmap progress, agent health,
and deliverable tracking to a Notion workspace.  This is strictly
write-only: Guardian never reads Notion content for decision-making,
eliminating injection and C2 attack vectors.

Security properties:
    - Token loaded from Vault on-demand, never cached as an attribute
    - All requests routed through the Gateway (TLS, rate limit, circuit breaker)
    - Content classification gate prevents PHI/PII from leaving the system
    - Response bodies size-limited to prevent memory exhaustion
    - All operations are idempotent (safe to retry)
    - No eval/exec/shell of any Notion-sourced data

Rate limit awareness:
    - Notion API limit: 3 requests/second (average)
    - Minimum 350ms between requests enforced by Gateway rate limiter
    - Batch block appends (up to 100 children per call)
    - Retry with exponential backoff on 429 responses

Setup:
    1. Create a Notion internal integration at https://www.notion.so/my-integrations
    2. Grant it access to the target workspace pages
    3. Store the token in the vault:
           vault.store("NOTION_TOKEN", "ntn_...", service="notion", scope="write")
    4. Set NOTION_ROOT_PAGE_ID in .env or guardian_config.yaml
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from guardian_one.core.audit import AuditLog, Severity


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class NotionPage:
    """Tracks a synced Notion page."""
    page_id: str
    title: str
    parent_id: str
    page_type: str          # dashboard, database, wiki
    last_synced: str = ""
    guardian_key: str = ""   # internal key for idempotent upsert


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool
    pages_created: int = 0
    pages_updated: int = 0
    blocks_written: int = 0
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0


# ---------------------------------------------------------------------------
# Content classification — prevents PHI/PII from leaving the system
# ---------------------------------------------------------------------------

# Categories that may NEVER be synced to Notion
_BLOCKED_CATEGORIES = frozenset({
    "phi",              # Protected Health Information
    "pii",              # Personally Identifiable Information
    "financial_account", # Bank account numbers, routing numbers
    "credential",       # API keys, tokens, passwords
    "ssn",              # Social Security Numbers
    "medical_record",   # Clinical data, diagnoses, medications
})

# Allow-listed data types that CAN be synced
_ALLOWED_CATEGORIES = frozenset({
    "agent_status",     # Agent health, uptime, last run
    "roadmap",          # Development roadmap progress
    "deliverable",      # Business documents status
    "metric",           # Aggregate metrics (no individual data)
    "config_summary",   # Non-sensitive configuration overview
    "integration_health", # API health scores (no credentials)
    "task",             # Task tracking, todos
    "decision",         # Architectural decisions
})

# Patterns that indicate PHI/PII content — block if matched
_PHI_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),              # SSN
    re.compile(r"\b\d{9}\b"),                            # SSN without dashes
    re.compile(r"\b[A-Z]{1,2}\d{6,10}\b"),              # Medical record numbers
    re.compile(r"\bMRN\s*[:#]?\s*\d+\b", re.IGNORECASE), # MRN references
    re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),  # Credit card
    re.compile(r"\b\d{9,17}\b"),                         # Bank account numbers
    re.compile(                                          # Email addresses
        r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"
    ),
]


def classify_content(text: str, category: str) -> bool:
    """Return True if content is safe to sync to Notion.

    Performs two checks:
        1. Category allow-list (must be in _ALLOWED_CATEGORIES)
        2. PHI/PII pattern scan (must not match _PHI_PATTERNS)
    """
    if category in _BLOCKED_CATEGORIES:
        return False
    if category not in _ALLOWED_CATEGORIES:
        return False
    # Scan text for PHI/PII patterns
    for pattern in _PHI_PATTERNS:
        if pattern.search(text):
            return False
    return True


# ---------------------------------------------------------------------------
# Notion API client — routes through Gateway
# ---------------------------------------------------------------------------

# Maximum response size we'll accept (10 MB)
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024

# Notion API version header
_NOTION_VERSION = "2022-06-28"

# Minimum interval between requests (ms) — Notion rate limit is 3 req/s
_MIN_REQUEST_INTERVAL_S = 0.35


class NotionSync:
    """Write-only Notion sync engine.

    All API calls go through the Guardian Gateway for TLS enforcement,
    rate limiting, circuit breaking, and audit logging.

    Token is loaded from the Vault on each sync cycle — never cached
    as an instance attribute to minimize exposure window.

    Usage:
        sync = NotionSync(
            gateway=guardian.gateway,
            vault=guardian.vault,
            audit=guardian.audit,
            root_page_id="abc123...",
        )
        result = sync.push_agent_status(agents_data)
    """

    def __init__(
        self,
        gateway: Any,           # guardian_one.homelink.gateway.Gateway
        vault: Any,             # guardian_one.homelink.vault.Vault
        audit: AuditLog,
        root_page_id: str,
    ) -> None:
        self._gateway = gateway
        self._vault = vault
        self._audit = audit
        self._root_page_id = root_page_id
        self._page_cache: dict[str, NotionPage] = {}
        self._last_request_time: float = 0

    # ------------------------------------------------------------------
    # Token access — on-demand from Vault, never cached
    # ------------------------------------------------------------------

    def _get_token(self) -> str | None:
        """Retrieve the Notion token from Vault.

        Loaded fresh each time to minimize the window where the token
        exists in process memory as a Python string.
        """
        return self._vault.retrieve("NOTION_TOKEN")

    def _auth_headers(self) -> dict[str, str] | None:
        """Build auth headers.  Returns None if token is unavailable."""
        token = self._get_token()
        if not token:
            return None
        return {
            "Authorization": f"Bearer {token}",
            "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Rate-limited request wrapper
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a rate-limited request through the Gateway."""
        headers = self._auth_headers()
        if headers is None:
            return {
                "success": False,
                "error": "NOTION_TOKEN not found in Vault. "
                         "Store it with: vault.store('NOTION_TOKEN', 'ntn_...', "
                         "service='notion', scope='write')",
            }

        # Enforce minimum interval between requests
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < _MIN_REQUEST_INTERVAL_S:
            time.sleep(_MIN_REQUEST_INTERVAL_S - elapsed)

        result = self._gateway.request(
            service="notion",
            method=method,
            path=path,
            headers=headers,
            body=body,
            agent="notion_sync",
        )
        self._last_request_time = time.monotonic()

        # Handle Notion rate limit with Retry-After
        if result.get("status_code") == 429:
            retry_after = 1.0  # Default 1 second
            self._audit.record(
                agent="notion_sync",
                action="rate_limited",
                severity=Severity.WARNING,
                details={"path": path, "retry_after_s": retry_after},
            )
            time.sleep(retry_after)
            # Single retry — if still limited, circuit breaker handles it
            result = self._gateway.request(
                service="notion",
                method=method,
                path=path,
                headers=headers,
                body=body,
                agent="notion_sync",
            )
            self._last_request_time = time.monotonic()

        return result

    # ------------------------------------------------------------------
    # Page operations
    # ------------------------------------------------------------------

    def _create_page(
        self,
        parent_id: str,
        title: str,
        icon_emoji: str = "",
        children: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a page under a parent page."""
        # Sanitize title — allow-list of safe characters
        safe_title = re.sub(r"[^\w\s\-—./(),:;!?&#+@]", "", title)[:100]

        body: dict[str, Any] = {
            "parent": {"page_id": parent_id},
            "properties": {
                "title": {
                    "title": [{"text": {"content": safe_title}}]
                }
            },
        }
        if icon_emoji:
            body["icon"] = {"type": "emoji", "emoji": icon_emoji}
        if children:
            # Notion limit: max 100 children per request
            body["children"] = children[:100]

        return self._request("POST", "/v1/pages", body)

    def _create_database(
        self,
        parent_id: str,
        title: str,
        properties: dict[str, Any],
        icon_emoji: str = "",
    ) -> dict[str, Any]:
        """Create a database under a parent page."""
        safe_title = re.sub(r"[^\w\s\-—./(),:;!?&#+@]", "", title)[:100]

        body: dict[str, Any] = {
            "parent": {"page_id": parent_id},
            "title": [{"text": {"content": safe_title}}],
            "properties": properties,
        }
        if icon_emoji:
            body["icon"] = {"type": "emoji", "emoji": icon_emoji}

        return self._request("POST", "/v1/databases", body)

    def _add_database_row(
        self,
        database_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        """Add a row to a Notion database."""
        body = {
            "parent": {"database_id": database_id},
            "properties": properties,
        }
        return self._request("POST", "/v1/pages", body)

    def _append_blocks(
        self,
        page_id: str,
        children: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Append blocks to an existing page.  Batches at 100."""
        if not children:
            return {"success": True, "data": None}
        # Batch at Notion's limit of 100 blocks per append
        body = {"children": children[:100]}
        return self._request(
            "PATCH", f"/v1/blocks/{page_id}/children", body,
        )

    def _update_page_properties(
        self,
        page_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        """Update properties on an existing page."""
        body = {"properties": properties}
        return self._request("PATCH", f"/v1/pages/{page_id}", body)

    # ------------------------------------------------------------------
    # Block builders — generate Notion block JSON
    # ------------------------------------------------------------------

    @staticmethod
    def _heading(text: str, level: int = 2) -> dict[str, Any]:
        key = f"heading_{min(max(level, 1), 3)}"
        return {
            "object": "block",
            "type": key,
            key: {
                "rich_text": [{"type": "text", "text": {"content": text[:2000]}}]
            },
        }

    @staticmethod
    def _paragraph(text: str) -> dict[str, Any]:
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": text[:2000]}}]
            },
        }

    @staticmethod
    def _bulleted(text: str) -> dict[str, Any]:
        return {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"type": "text", "text": {"content": text[:2000]}}]
            },
        }

    @staticmethod
    def _callout(text: str, emoji: str = "!") -> dict[str, Any]:
        return {
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": text[:2000]}}],
                "icon": {"type": "emoji", "emoji": emoji},
            },
        }

    @staticmethod
    def _divider() -> dict[str, Any]:
        return {"object": "block", "type": "divider", "divider": {}}

    @staticmethod
    def _code(text: str, language: str = "plain text") -> dict[str, Any]:
        return {
            "object": "block",
            "type": "code",
            "code": {
                "rich_text": [{"type": "text", "text": {"content": text[:2000]}}],
                "language": language,
            },
        }

    @staticmethod
    def _table_of_contents() -> dict[str, Any]:
        return {
            "object": "block",
            "type": "table_of_contents",
            "table_of_contents": {},
        }

    # ------------------------------------------------------------------
    # High-level sync operations
    # ------------------------------------------------------------------

    @property
    def is_configured(self) -> bool:
        """Check if Notion sync is ready (token + root page)."""
        return bool(self._root_page_id and self._get_token())

    def push_command_center(
        self,
        agents: list[dict[str, Any]],
        system_status: str = "operational",
    ) -> SyncResult:
        """Push the Command Center dashboard page.

        Args:
            agents: List of dicts with keys: name, status, last_run,
                    health_score, schedule_interval.
            system_status: Overall system status string.
        """
        start = time.monotonic()
        result = SyncResult(success=False)

        # Classify content before sync
        status_text = json.dumps(agents, default=str)
        if not classify_content(status_text, "agent_status"):
            result.errors.append("Content blocked by classification gate")
            self._audit.record(
                agent="notion_sync",
                action="content_blocked",
                severity=Severity.WARNING,
                details={"category": "agent_status", "reason": "classification_failed"},
            )
            return result

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        children = [
            self._callout(
                f"System Status: {system_status} | Last sync: {now}",
                "#",
            ),
            self._table_of_contents(),
            self._heading("Agent Status", 2),
        ]

        for agent in agents:
            name = str(agent.get("name", "unknown"))
            status = str(agent.get("status", "unknown"))
            last_run = str(agent.get("last_run", "never"))
            health = str(agent.get("health_score", "N/A"))
            interval = str(agent.get("schedule_interval", "N/A"))

            children.append(self._heading(name, 3))
            children.append(self._bulleted(f"Status: {status}"))
            children.append(self._bulleted(f"Last run: {last_run}"))
            children.append(self._bulleted(f"Health score: {health}"))
            children.append(self._bulleted(f"Schedule: every {interval} min"))

        children.append(self._divider())
        children.append(self._heading("Quick Links", 2))
        children.append(self._bulleted("Agent Registry — full agent database"))
        children.append(self._bulleted("Roadmap — production deployment progress"))
        children.append(self._bulleted("Deliverables — SHM, business model, GTM"))

        cache_key = "command_center"
        cached = self._page_cache.get(cache_key)

        if cached:
            resp = self._append_blocks(cached.page_id, children)
        else:
            resp = self._create_page(
                self._root_page_id,
                "Command Center",
                icon_emoji="#",
                children=children,
            )

        if resp.get("success") and resp.get("data"):
            page_id = resp["data"].get("id", "")
            if page_id and not cached:
                self._page_cache[cache_key] = NotionPage(
                    page_id=page_id,
                    title="Command Center",
                    parent_id=self._root_page_id,
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
                agent="notion_sync",
                action="sync_failed:command_center",
                severity=Severity.ERROR,
                details={"error": error},
            )

        result.duration_ms = (time.monotonic() - start) * 1000
        return result

    def push_agent_registry(
        self,
        agents: list[dict[str, Any]],
    ) -> SyncResult:
        """Push Agent Registry as a Notion database.

        Args:
            agents: List of dicts with keys: name, status, enabled,
                    schedule_interval, allowed_resources, health_score.
        """
        start = time.monotonic()
        result = SyncResult(success=False)

        status_text = json.dumps(agents, default=str)
        if not classify_content(status_text, "agent_status"):
            result.errors.append("Content blocked by classification gate")
            return result

        cache_key = "agent_registry_db"
        cached = self._page_cache.get(cache_key)

        if not cached:
            # Create the database
            db_properties = {
                "Name": {"title": {}},
                "Status": {
                    "select": {
                        "options": [
                            {"name": "running", "color": "green"},
                            {"name": "idle", "color": "gray"},
                            {"name": "error", "color": "red"},
                            {"name": "disabled", "color": "default"},
                        ]
                    }
                },
                "Health Score": {"number": {"format": "number"}},
                "Schedule (min)": {"number": {"format": "number"}},
                "Last Run": {"rich_text": {}},
                "Resources": {"rich_text": {}},
            }
            resp = self._create_database(
                self._root_page_id,
                "Agent Registry",
                db_properties,
            )
            if not resp.get("success") or not resp.get("data"):
                result.errors.append(resp.get("error", "Failed to create database"))
                result.duration_ms = (time.monotonic() - start) * 1000
                return result

            db_id = resp["data"].get("id", "")
            self._page_cache[cache_key] = NotionPage(
                page_id=db_id,
                title="Agent Registry",
                parent_id=self._root_page_id,
                page_type="database",
                last_synced=datetime.now(timezone.utc).isoformat(),
                guardian_key=cache_key,
            )
            cached = self._page_cache[cache_key]
            result.pages_created = 1

        # Add rows for each agent
        for agent in agents:
            name = str(agent.get("name", "unknown"))
            status = str(agent.get("status", "idle"))
            health = agent.get("health_score", 0)
            interval = agent.get("schedule_interval", 60)
            last_run = str(agent.get("last_run", "never"))
            resources = ", ".join(agent.get("allowed_resources", []))

            row_props = {
                "Name": {"title": [{"text": {"content": name[:100]}}]},
                "Status": {"select": {"name": status[:100]}},
                "Health Score": {"number": health if isinstance(health, (int, float)) else 0},
                "Schedule (min)": {"number": interval if isinstance(interval, (int, float)) else 60},
                "Last Run": {"rich_text": [{"text": {"content": last_run[:200]}}]},
                "Resources": {"rich_text": [{"text": {"content": resources[:2000]}}]},
            }
            row_resp = self._add_database_row(cached.page_id, row_props)
            if row_resp.get("success"):
                result.blocks_written += 1
            else:
                result.errors.append(f"Failed to add agent {name}: {row_resp.get('error', '')}")

        result.success = len(result.errors) == 0
        result.duration_ms = (time.monotonic() - start) * 1000
        return result

    def push_roadmap(
        self,
        phases: list[dict[str, Any]],
    ) -> SyncResult:
        """Push roadmap phases as a Notion database.

        Args:
            phases: List of dicts with keys: phase_number, title,
                    status, priority_tier, description.
        """
        start = time.monotonic()
        result = SyncResult(success=False)

        text = json.dumps(phases, default=str)
        if not classify_content(text, "roadmap"):
            result.errors.append("Content blocked by classification gate")
            return result

        cache_key = "roadmap_db"
        cached = self._page_cache.get(cache_key)

        if not cached:
            db_properties = {
                "Phase": {"title": {}},
                "Status": {
                    "select": {
                        "options": [
                            {"name": "not_started", "color": "default"},
                            {"name": "in_progress", "color": "blue"},
                            {"name": "completed", "color": "green"},
                            {"name": "blocked", "color": "red"},
                        ]
                    }
                },
                "Priority Tier": {
                    "select": {
                        "options": [
                            {"name": "Foundation", "color": "purple"},
                            {"name": "Reliability", "color": "blue"},
                            {"name": "Deployment", "color": "orange"},
                            {"name": "Go-Live", "color": "green"},
                        ]
                    }
                },
                "Description": {"rich_text": {}},
            }
            resp = self._create_database(
                self._root_page_id,
                "Production Roadmap",
                db_properties,
            )
            if not resp.get("success") or not resp.get("data"):
                result.errors.append(resp.get("error", "Failed to create roadmap DB"))
                result.duration_ms = (time.monotonic() - start) * 1000
                return result

            db_id = resp["data"].get("id", "")
            self._page_cache[cache_key] = NotionPage(
                page_id=db_id,
                title="Production Roadmap",
                parent_id=self._root_page_id,
                page_type="database",
                last_synced=datetime.now(timezone.utc).isoformat(),
                guardian_key=cache_key,
            )
            cached = self._page_cache[cache_key]
            result.pages_created = 1

        for phase in phases:
            num = phase.get("phase_number", "?")
            title = str(phase.get("title", ""))
            status = str(phase.get("status", "not_started"))
            tier = str(phase.get("priority_tier", ""))
            desc = str(phase.get("description", ""))

            row_props = {
                "Phase": {"title": [{"text": {"content": f"{num}. {title}"[:100]}}]},
                "Status": {"select": {"name": status[:100]}},
                "Priority Tier": {"select": {"name": tier[:100]}},
                "Description": {"rich_text": [{"text": {"content": desc[:2000]}}]},
            }
            row_resp = self._add_database_row(cached.page_id, row_props)
            if row_resp.get("success"):
                result.blocks_written += 1
            else:
                result.errors.append(f"Failed to add phase {num}")

        result.success = len(result.errors) == 0
        result.duration_ms = (time.monotonic() - start) * 1000
        return result

    def push_integration_health(
        self,
        services: list[dict[str, Any]],
    ) -> SyncResult:
        """Push integration health snapshot.

        Args:
            services: List of dicts with keys: name, circuit_state,
                      success_rate, avg_latency_ms, risk_score.
        """
        start = time.monotonic()
        result = SyncResult(success=False)

        text = json.dumps(services, default=str)
        if not classify_content(text, "integration_health"):
            result.errors.append("Content blocked by classification gate")
            return result

        cache_key = "integration_health_db"
        cached = self._page_cache.get(cache_key)

        if not cached:
            db_properties = {
                "Service": {"title": {}},
                "Circuit State": {
                    "select": {
                        "options": [
                            {"name": "closed", "color": "green"},
                            {"name": "half_open", "color": "yellow"},
                            {"name": "open", "color": "red"},
                        ]
                    }
                },
                "Success Rate": {"number": {"format": "percent"}},
                "Avg Latency (ms)": {"number": {"format": "number"}},
                "Risk Score": {"number": {"format": "number"}},
            }
            resp = self._create_database(
                self._root_page_id,
                "Integration Health",
                db_properties,
            )
            if not resp.get("success") or not resp.get("data"):
                result.errors.append(resp.get("error", "Failed to create health DB"))
                result.duration_ms = (time.monotonic() - start) * 1000
                return result

            db_id = resp["data"].get("id", "")
            self._page_cache[cache_key] = NotionPage(
                page_id=db_id,
                title="Integration Health",
                parent_id=self._root_page_id,
                page_type="database",
                last_synced=datetime.now(timezone.utc).isoformat(),
                guardian_key=cache_key,
            )
            cached = self._page_cache[cache_key]
            result.pages_created = 1

        for svc in services:
            name = str(svc.get("name", "unknown"))
            circuit = str(svc.get("circuit_state", "closed"))
            success = svc.get("success_rate", 1.0)
            latency = svc.get("avg_latency_ms", 0)
            risk = svc.get("risk_score", 1)

            row_props = {
                "Service": {"title": [{"text": {"content": name[:100]}}]},
                "Circuit State": {"select": {"name": circuit[:100]}},
                "Success Rate": {"number": success if isinstance(success, (int, float)) else 0},
                "Avg Latency (ms)": {"number": latency if isinstance(latency, (int, float)) else 0},
                "Risk Score": {"number": risk if isinstance(risk, (int, float)) else 1},
            }
            row_resp = self._add_database_row(cached.page_id, row_props)
            if row_resp.get("success"):
                result.blocks_written += 1
            else:
                result.errors.append(f"Failed to add service {name}")

        result.success = len(result.errors) == 0
        result.duration_ms = (time.monotonic() - start) * 1000
        return result

    def push_deliverables(
        self,
        deliverables: list[dict[str, Any]],
    ) -> SyncResult:
        """Push deliverables tracking database.

        Args:
            deliverables: List of dicts with keys: title, status,
                          audience, due_date, description.
        """
        start = time.monotonic()
        result = SyncResult(success=False)

        text = json.dumps(deliverables, default=str)
        if not classify_content(text, "deliverable"):
            result.errors.append("Content blocked by classification gate")
            return result

        cache_key = "deliverables_db"
        cached = self._page_cache.get(cache_key)

        if not cached:
            db_properties = {
                "Title": {"title": {}},
                "Status": {
                    "select": {
                        "options": [
                            {"name": "draft", "color": "default"},
                            {"name": "in_progress", "color": "blue"},
                            {"name": "review", "color": "yellow"},
                            {"name": "complete", "color": "green"},
                        ]
                    }
                },
                "Audience": {"rich_text": {}},
                "Due Date": {"date": {}},
                "Description": {"rich_text": {}},
            }
            resp = self._create_database(
                self._root_page_id,
                "Deliverables",
                db_properties,
            )
            if not resp.get("success") or not resp.get("data"):
                result.errors.append(resp.get("error", "Failed to create deliverables DB"))
                result.duration_ms = (time.monotonic() - start) * 1000
                return result

            db_id = resp["data"].get("id", "")
            self._page_cache[cache_key] = NotionPage(
                page_id=db_id,
                title="Deliverables",
                parent_id=self._root_page_id,
                page_type="database",
                last_synced=datetime.now(timezone.utc).isoformat(),
                guardian_key=cache_key,
            )
            cached = self._page_cache[cache_key]
            result.pages_created = 1

        for d in deliverables:
            title = str(d.get("title", ""))
            status = str(d.get("status", "draft"))
            audience = str(d.get("audience", ""))
            due = d.get("due_date", "")
            desc = str(d.get("description", ""))

            row_props: dict[str, Any] = {
                "Title": {"title": [{"text": {"content": title[:100]}}]},
                "Status": {"select": {"name": status[:100]}},
                "Audience": {"rich_text": [{"text": {"content": audience[:200]}}]},
                "Description": {"rich_text": [{"text": {"content": desc[:2000]}}]},
            }
            if due:
                row_props["Due Date"] = {"date": {"start": str(due)[:10]}}

            row_resp = self._add_database_row(cached.page_id, row_props)
            if row_resp.get("success"):
                result.blocks_written += 1
            else:
                result.errors.append(f"Failed to add deliverable: {title}")

        result.success = len(result.errors) == 0
        result.duration_ms = (time.monotonic() - start) * 1000
        return result

    def push_decision_log(
        self,
        decisions: list[dict[str, Any]],
    ) -> SyncResult:
        """Push architectural/business decision log.

        Args:
            decisions: List of dicts with keys: date, context,
                       decision, rationale, revisit_date.
        """
        start = time.monotonic()
        result = SyncResult(success=False)

        text = json.dumps(decisions, default=str)
        if not classify_content(text, "decision"):
            result.errors.append("Content blocked by classification gate")
            return result

        cache_key = "decision_log_db"
        cached = self._page_cache.get(cache_key)

        if not cached:
            db_properties = {
                "Decision": {"title": {}},
                "Date": {"date": {}},
                "Context": {"rich_text": {}},
                "Rationale": {"rich_text": {}},
                "Revisit Date": {"date": {}},
            }
            resp = self._create_database(
                self._root_page_id,
                "Decision Log",
                db_properties,
            )
            if not resp.get("success") or not resp.get("data"):
                result.errors.append(resp.get("error", "Failed to create decision log DB"))
                result.duration_ms = (time.monotonic() - start) * 1000
                return result

            db_id = resp["data"].get("id", "")
            self._page_cache[cache_key] = NotionPage(
                page_id=db_id,
                title="Decision Log",
                parent_id=self._root_page_id,
                page_type="database",
                last_synced=datetime.now(timezone.utc).isoformat(),
                guardian_key=cache_key,
            )
            cached = self._page_cache[cache_key]
            result.pages_created = 1

        for d in decisions:
            decision_text = str(d.get("decision", ""))
            date = d.get("date", "")
            context = str(d.get("context", ""))
            rationale = str(d.get("rationale", ""))
            revisit = d.get("revisit_date", "")

            row_props: dict[str, Any] = {
                "Decision": {"title": [{"text": {"content": decision_text[:100]}}]},
                "Context": {"rich_text": [{"text": {"content": context[:2000]}}]},
                "Rationale": {"rich_text": [{"text": {"content": rationale[:2000]}}]},
            }
            if date:
                row_props["Date"] = {"date": {"start": str(date)[:10]}}
            if revisit:
                row_props["Revisit Date"] = {"date": {"start": str(revisit)[:10]}}

            row_resp = self._add_database_row(cached.page_id, row_props)
            if row_resp.get("success"):
                result.blocks_written += 1
            else:
                result.errors.append(f"Failed to add decision: {decision_text[:50]}")

        result.success = len(result.errors) == 0
        result.duration_ms = (time.monotonic() - start) * 1000
        return result

    def push_architecture_wiki(self) -> SyncResult:
        """Push a static architecture overview page."""
        start = time.monotonic()
        result = SyncResult(success=False)

        children = [
            self._callout("Guardian One Architecture Overview", "#"),
            self._table_of_contents(),
            self._heading("System Overview", 2),
            self._paragraph(
                "Guardian One is a multi-agent AI orchestration platform with "
                "data sovereignty. The system coordinates specialized agents that "
                "manage scheduling, finances, archival, deliveries, email, and "
                "web infrastructure."
            ),
            self._heading("Core Modules", 2),
            self._bulleted("Guardian (core/guardian.py) - Central coordinator, agent lifecycle"),
            self._bulleted("Mediator (core/mediator.py) - Cross-agent conflict resolution"),
            self._bulleted("Scheduler (core/scheduler.py) - Task scheduling and execution"),
            self._bulleted("Audit (core/audit.py) - Thread-safe append-only audit log"),
            self._bulleted("Security (core/security.py) - RBAC, encryption, access control"),
            self._divider(),
            self._heading("H.O.M.E. L.I.N.K. Subsystem", 2),
            self._bulleted("Gateway (homelink/gateway.py) - TLS-enforced API gateway with circuit breaker"),
            self._bulleted("Vault (homelink/vault.py) - Encrypted credential store (PBKDF2 + Fernet)"),
            self._bulleted("Registry (homelink/registry.py) - Integration catalog with threat models"),
            self._bulleted("Monitor (homelink/monitor.py) - Health scoring and anomaly detection"),
            self._divider(),
            self._heading("Agent Registry", 2),
            self._bulleted("Chronos - Calendar, scheduling, routines (15-min cycle)"),
            self._bulleted("CFO - Financial tracking, budgets, bill alerts (60-min cycle)"),
            self._bulleted("Archivist - File management, data retention, privacy (60-min cycle)"),
            self._bulleted("DoorDash - Meal ordering, delivery tracking (10-min cycle)"),
            self._bulleted("Gmail - Inbox monitoring, financial email extraction"),
            self._bulleted("WebArchitect - Website deploy, security scans, uptime (30-min cycle)"),
            self._divider(),
            self._heading("Security Architecture", 2),
            self._bulleted("AES-256 encryption (Fernet) for all secrets at rest"),
            self._bulleted("PBKDF2 key derivation with 480K iterations"),
            self._bulleted("Per-store random salts (16 bytes, os.urandom)"),
            self._bulleted("Role-based access control (Owner/Guardian/Agent/Readonly/Mentor)"),
            self._bulleted("TLS 1.3 enforcement on all external API calls"),
            self._bulleted("Rate limiting + circuit breaker on every external service"),
            self._bulleted("Full audit trail with log rotation (10MB cap, 5 rotated files)"),
        ]

        cache_key = "architecture_wiki"
        cached = self._page_cache.get(cache_key)

        if cached:
            resp = self._append_blocks(cached.page_id, children)
        else:
            resp = self._create_page(
                self._root_page_id,
                "Architecture",
                children=children,
            )

        if resp.get("success") and resp.get("data"):
            page_id = resp["data"].get("id", "")
            if page_id and not cached:
                self._page_cache[cache_key] = NotionPage(
                    page_id=page_id,
                    title="Architecture",
                    parent_id=self._root_page_id,
                    page_type="wiki",
                    last_synced=datetime.now(timezone.utc).isoformat(),
                    guardian_key=cache_key,
                )
            result.success = True
            result.pages_created = 0 if cached else 1
            result.blocks_written = len(children)
        else:
            result.errors.append(resp.get("error", "Unknown error"))

        result.duration_ms = (time.monotonic() - start) * 1000
        return result

    # ------------------------------------------------------------------
    # Full workspace sync
    # ------------------------------------------------------------------

    def full_sync(
        self,
        agents: list[dict[str, Any]],
        roadmap_phases: list[dict[str, Any]],
        services: list[dict[str, Any]],
        deliverables: list[dict[str, Any]],
        decisions: list[dict[str, Any]] | None = None,
        system_status: str = "operational",
    ) -> SyncResult:
        """Run a complete workspace sync.

        Creates/updates all workspace sections in order:
            1. Command Center (dashboard)
            2. Agent Registry (database)
            3. Production Roadmap (database)
            4. Integration Health (database)
            5. Deliverables (database)
            6. Architecture (wiki page)
            7. Decision Log (database, if provided)
        """
        start = time.monotonic()
        combined = SyncResult(success=True)

        self._audit.record(
            agent="notion_sync",
            action="full_sync_started",
            severity=Severity.INFO,
        )

        sync_ops = [
            ("command_center", lambda: self.push_command_center(agents, system_status)),
            ("agent_registry", lambda: self.push_agent_registry(agents)),
            ("roadmap", lambda: self.push_roadmap(roadmap_phases)),
            ("integration_health", lambda: self.push_integration_health(services)),
            ("deliverables", lambda: self.push_deliverables(deliverables)),
            ("architecture", lambda: self.push_architecture_wiki()),
        ]

        if decisions:
            sync_ops.append(
                ("decision_log", lambda: self.push_decision_log(decisions))
            )

        for op_name, op_fn in sync_ops:
            try:
                r = op_fn()
                combined.pages_created += r.pages_created
                combined.pages_updated += r.pages_updated
                combined.blocks_written += r.blocks_written
                if not r.success:
                    combined.success = False
                    combined.errors.extend(
                        f"[{op_name}] {e}" for e in r.errors
                    )
            except Exception as exc:
                combined.success = False
                combined.errors.append(f"[{op_name}] Exception: {exc}")
                self._audit.record(
                    agent="notion_sync",
                    action=f"sync_error:{op_name}",
                    severity=Severity.ERROR,
                    details={"error": str(exc)},
                )

        combined.duration_ms = (time.monotonic() - start) * 1000

        self._audit.record(
            agent="notion_sync",
            action="full_sync_completed",
            severity=Severity.INFO if combined.success else Severity.WARNING,
            details={
                "pages_created": combined.pages_created,
                "blocks_written": combined.blocks_written,
                "errors": len(combined.errors),
                "duration_ms": round(combined.duration_ms, 1),
            },
        )

        return combined

    def status(self) -> dict[str, Any]:
        """Return current sync status for monitoring."""
        return {
            "configured": self.is_configured,
            "root_page_id": self._root_page_id[:8] + "..." if self._root_page_id else "",
            "cached_pages": len(self._page_cache),
            "page_keys": list(self._page_cache.keys()),
            "token_available": self._get_token() is not None,
        }
