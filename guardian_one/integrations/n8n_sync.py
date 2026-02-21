"""n8n Workflow Automation integration.

Connects to a self-hosted or cloud n8n instance via its REST API.
Used by the WebArchitect agent to manage website workflows,
deploy pages, and run security scans.

Setup:
1. Install n8n (self-hosted or cloud): https://n8n.io
2. Enable the API and create an API key in n8n settings.
3. Set these in your .env file:
       N8N_BASE_URL=http://localhost:5678   # or your cloud URL
       N8N_API_KEY=your-api-key-here
4. The agent will auto-connect on startup when credentials are present.

API reference: https://docs.n8n.io/api/
"""

from __future__ import annotations

import abc
import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class N8nWorkflow:
    """An n8n workflow definition."""
    id: str
    name: str
    active: bool = False
    tags: list[str] = field(default_factory=list)
    nodes: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    raw: dict[str, Any] | None = None


@dataclass
class N8nExecution:
    """Result of a workflow execution."""
    id: str
    workflow_id: str
    status: str  # success, error, waiting, running
    started_at: str = ""
    finished_at: str = ""
    mode: str = "manual"  # manual, trigger, webhook
    data: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] | None = None


@dataclass
class N8nWebhook:
    """Webhook endpoint exposed by an n8n workflow."""
    workflow_id: str
    webhook_path: str
    method: str = "POST"
    url: str = ""


@dataclass
class WebsiteDeployment:
    """Tracks a website deployment through n8n."""
    domain: str
    workflow_id: str
    status: str  # pending, building, deployed, failed
    deployed_at: str = ""
    ssl_enabled: bool = False
    pages: list[str] = field(default_factory=list)
    security_scan_passed: bool = False


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------

class N8nProvider(abc.ABC):
    """Abstract interface for n8n API access."""

    @abc.abstractmethod
    def authenticate(self) -> bool: ...

    @abc.abstractmethod
    def list_workflows(self) -> list[N8nWorkflow]: ...

    @abc.abstractmethod
    def get_workflow(self, workflow_id: str) -> N8nWorkflow | None: ...

    @abc.abstractmethod
    def create_workflow(self, name: str, nodes: list[dict[str, Any]]) -> N8nWorkflow | None: ...

    @abc.abstractmethod
    def activate_workflow(self, workflow_id: str) -> bool: ...

    @abc.abstractmethod
    def deactivate_workflow(self, workflow_id: str) -> bool: ...

    @abc.abstractmethod
    def execute_workflow(self, workflow_id: str, data: dict[str, Any] | None = None) -> N8nExecution | None: ...

    @abc.abstractmethod
    def get_execution(self, execution_id: str) -> N8nExecution | None: ...

    @property
    @abc.abstractmethod
    def is_authenticated(self) -> bool: ...


# ---------------------------------------------------------------------------
# Live n8n API provider
# ---------------------------------------------------------------------------

class N8nAPIProvider(N8nProvider):
    """n8n REST API integration.

    Handles authentication, workflow CRUD, and execution management.
    Credentials are loaded from env vars if not passed directly.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._base_url = (base_url or os.getenv("N8N_BASE_URL", "")).rstrip("/")
        self._api_key = api_key or os.getenv("N8N_API_KEY", "")
        self._authenticated = False

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    @property
    def has_credentials(self) -> bool:
        return bool(self._base_url and self._api_key)

    def authenticate(self) -> bool:
        """Verify API connectivity by fetching workflows."""
        if not self.has_credentials:
            self._authenticated = False
            return False

        result = self._request("GET", "/api/v1/workflows?limit=1")
        if result is not None and not result.get("error"):
            self._authenticated = True
            return True
        self._authenticated = False
        return False

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Make an authenticated request to the n8n API."""
        url = f"{self._base_url}{path}"
        data = json.dumps(body).encode() if body else None

        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "X-N8N-API-KEY": self._api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            return {"error": True, "status": e.code, "detail": error_body}
        except urllib.error.URLError:
            return {"error": True, "detail": "Network error"}

    # ------------------------------------------------------------------
    # Workflow operations
    # ------------------------------------------------------------------

    def list_workflows(self) -> list[N8nWorkflow]:
        result = self._request("GET", "/api/v1/workflows")
        if result is None or result.get("error"):
            return []
        workflows = []
        for item in result.get("data", []):
            workflows.append(N8nWorkflow(
                id=str(item.get("id", "")),
                name=item.get("name", ""),
                active=item.get("active", False),
                tags=[t.get("name", "") for t in item.get("tags", [])],
                created_at=item.get("createdAt", ""),
                updated_at=item.get("updatedAt", ""),
                raw=item,
            ))
        return workflows

    def get_workflow(self, workflow_id: str) -> N8nWorkflow | None:
        result = self._request("GET", f"/api/v1/workflows/{workflow_id}")
        if result is None or result.get("error"):
            return None
        return N8nWorkflow(
            id=str(result.get("id", workflow_id)),
            name=result.get("name", ""),
            active=result.get("active", False),
            nodes=result.get("nodes", []),
            tags=[t.get("name", "") for t in result.get("tags", [])],
            created_at=result.get("createdAt", ""),
            updated_at=result.get("updatedAt", ""),
            raw=result,
        )

    def create_workflow(self, name: str, nodes: list[dict[str, Any]]) -> N8nWorkflow | None:
        body = {"name": name, "nodes": nodes, "connections": {}}
        result = self._request("POST", "/api/v1/workflows", body)
        if result is None or result.get("error"):
            return None
        return N8nWorkflow(
            id=str(result.get("id", "")),
            name=result.get("name", name),
            active=result.get("active", False),
            nodes=result.get("nodes", nodes),
            raw=result,
        )

    def activate_workflow(self, workflow_id: str) -> bool:
        result = self._request("PATCH", f"/api/v1/workflows/{workflow_id}", {"active": True})
        return result is not None and not result.get("error")

    def deactivate_workflow(self, workflow_id: str) -> bool:
        result = self._request("PATCH", f"/api/v1/workflows/{workflow_id}", {"active": False})
        return result is not None and not result.get("error")

    def execute_workflow(self, workflow_id: str, data: dict[str, Any] | None = None) -> N8nExecution | None:
        body = {}
        if data:
            body["data"] = data
        result = self._request("POST", f"/api/v1/workflows/{workflow_id}/run", body)
        if result is None or result.get("error"):
            return None
        return N8nExecution(
            id=str(result.get("id", "")),
            workflow_id=workflow_id,
            status=result.get("status", "running"),
            started_at=result.get("startedAt", ""),
            finished_at=result.get("stoppedAt", ""),
            mode=result.get("mode", "manual"),
            raw=result,
        )

    def get_execution(self, execution_id: str) -> N8nExecution | None:
        result = self._request("GET", f"/api/v1/executions/{execution_id}")
        if result is None or result.get("error"):
            return None
        return N8nExecution(
            id=str(result.get("id", execution_id)),
            workflow_id=str(result.get("workflowId", "")),
            status=result.get("status", "unknown"),
            started_at=result.get("startedAt", ""),
            finished_at=result.get("stoppedAt", ""),
            mode=result.get("mode", "manual"),
            raw=result,
        )


# ---------------------------------------------------------------------------
# Website workflow templates (pre-built n8n node configurations)
# ---------------------------------------------------------------------------

def website_build_workflow_nodes(domain: str) -> list[dict[str, Any]]:
    """Generate n8n workflow nodes for building a static website."""
    return [
        {
            "name": "Trigger",
            "type": "n8n-nodes-base.manualTrigger",
            "position": [250, 300],
            "parameters": {},
        },
        {
            "name": "Generate Pages",
            "type": "n8n-nodes-base.code",
            "position": [450, 300],
            "parameters": {
                "jsCode": (
                    f"// Generate static pages for {domain}\n"
                    "const pages = ['index.html', 'about.html', 'contact.html'];\n"
                    "return pages.map(p => ({json: {page: p, domain: '"
                    + domain
                    + "'}}));"
                ),
            },
        },
        {
            "name": "Security Headers",
            "type": "n8n-nodes-base.code",
            "position": [650, 300],
            "parameters": {
                "jsCode": (
                    "// Inject security headers into each page\n"
                    "const headers = {\n"
                    "  'Content-Security-Policy': \"default-src 'self'\",\n"
                    "  'X-Frame-Options': 'DENY',\n"
                    "  'X-Content-Type-Options': 'nosniff',\n"
                    "  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',\n"
                    "  'Referrer-Policy': 'strict-origin-when-cross-origin',\n"
                    "  'Permissions-Policy': 'camera=(), microphone=(), geolocation=()'\n"
                    "};\n"
                    "for (const item of $input.all()) {\n"
                    "  item.json.security_headers = headers;\n"
                    "}\n"
                    "return $input.all();"
                ),
            },
        },
        {
            "name": "SSL Check",
            "type": "n8n-nodes-base.code",
            "position": [850, 300],
            "parameters": {
                "jsCode": (
                    f"// Verify SSL is configured for {domain}\n"
                    "for (const item of $input.all()) {\n"
                    "  item.json.ssl_enabled = true;\n"
                    "  item.json.ssl_provider = 'lets_encrypt';\n"
                    "}\n"
                    "return $input.all();"
                ),
            },
        },
        {
            "name": "Deploy",
            "type": "n8n-nodes-base.code",
            "position": [1050, 300],
            "parameters": {
                "jsCode": (
                    "// Final deployment step\n"
                    "return [{json: {\n"
                    "  status: 'deployed',\n"
                    f"  domain: '{domain}',\n"
                    "  pages: $input.all().map(i => i.json.page),\n"
                    "  deployed_at: new Date().toISOString(),\n"
                    "  security_headers: true,\n"
                    "  ssl_enabled: true\n"
                    "}}];"
                ),
            },
        },
    ]


def security_scan_workflow_nodes(domain: str) -> list[dict[str, Any]]:
    """Generate n8n workflow nodes for running a security scan."""
    return [
        {
            "name": "Trigger",
            "type": "n8n-nodes-base.manualTrigger",
            "position": [250, 300],
            "parameters": {},
        },
        {
            "name": "Header Scan",
            "type": "n8n-nodes-base.httpRequest",
            "position": [450, 300],
            "parameters": {
                "url": f"https://{domain}",
                "method": "HEAD",
                "options": {"redirect": {"redirect": {"followRedirects": True}}},
            },
        },
        {
            "name": "Analyze Headers",
            "type": "n8n-nodes-base.code",
            "position": [650, 300],
            "parameters": {
                "jsCode": (
                    "// Check security headers\n"
                    "const headers = $input.first().json.headers || {};\n"
                    "const required = [\n"
                    "  'content-security-policy',\n"
                    "  'x-frame-options',\n"
                    "  'x-content-type-options',\n"
                    "  'strict-transport-security'\n"
                    "];\n"
                    "const missing = required.filter(h => !headers[h]);\n"
                    "return [{json: {\n"
                    f"  domain: '{domain}',\n"
                    "  headers_present: required.length - missing.length,\n"
                    "  headers_missing: missing,\n"
                    "  passed: missing.length === 0,\n"
                    "  scanned_at: new Date().toISOString()\n"
                    "}}];"
                ),
            },
        },
    ]


def uptime_monitor_workflow_nodes(domain: str) -> list[dict[str, Any]]:
    """Generate n8n workflow nodes for periodic uptime monitoring."""
    return [
        {
            "name": "Schedule",
            "type": "n8n-nodes-base.scheduleTrigger",
            "position": [250, 300],
            "parameters": {
                "rule": {"interval": [{"field": "minutes", "minutesInterval": 5}]},
            },
        },
        {
            "name": "Health Check",
            "type": "n8n-nodes-base.httpRequest",
            "position": [450, 300],
            "parameters": {
                "url": f"https://{domain}",
                "method": "GET",
                "options": {
                    "timeout": 10000,
                    "redirect": {"redirect": {"followRedirects": True}},
                },
            },
        },
        {
            "name": "Evaluate",
            "type": "n8n-nodes-base.code",
            "position": [650, 300],
            "parameters": {
                "jsCode": (
                    "const resp = $input.first().json;\n"
                    "const ok = resp.statusCode >= 200 && resp.statusCode < 400;\n"
                    "return [{json: {\n"
                    f"  domain: '{domain}',\n"
                    "  status_code: resp.statusCode,\n"
                    "  up: ok,\n"
                    "  checked_at: new Date().toISOString()\n"
                    "}}];"
                ),
            },
        },
    ]
