"""Health check HTTP server — lightweight status endpoints for Guardian One.

Runs a stdlib ``http.server`` in a daemon thread on 127.0.0.1 (never
exposed externally).  Provides three JSON endpoints:

    GET /health   — quick liveness probe (200 healthy / 503 degraded)
    GET /status   — detailed agent and subsystem state
    GET /metrics  — key numbers (net worth, alerts, audit count, etc.)
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from guardian_one.core.guardian import GuardianOne


class _HealthHandler(BaseHTTPRequestHandler):
    """HTTP request handler for health check endpoints."""

    # Assigned by HealthServer before the HTTPServer is started.
    guardian: GuardianOne | None = None
    start_time: float = 0.0

    # Silence per-request log lines
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        routes = {
            "/health": self._handle_health,
            "/status": self._handle_status,
            "/metrics": self._handle_metrics,
        }
        handler = routes.get(self.path)
        if handler is None:
            self._send_json({"error": "not found"}, status=404)
            return
        handler()

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    def _handle_health(self) -> None:
        guardian = self.guardian
        if guardian is None:
            self._send_json({"status": "unhealthy", "reason": "no guardian instance"}, status=503)
            return

        agents = guardian.list_agents()
        healthy = True
        for name in agents:
            agent = guardian.get_agent(name)
            if agent and agent.status.value == "error":
                healthy = False
                break

        uptime = time.monotonic() - self.start_time
        body = {
            "status": "healthy" if healthy else "degraded",
            "uptime_seconds": round(uptime, 2),
            "agents_registered": len(agents),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._send_json(body, status=200 if healthy else 503)

    def _handle_status(self) -> None:
        guardian = self.guardian
        if guardian is None:
            self._send_json({"error": "no guardian instance"}, status=503)
            return

        # Agent details
        agent_states: list[dict[str, Any]] = []
        for name in guardian.list_agents():
            agent = guardian.get_agent(name)
            if agent is None:
                continue
            agent_states.append({
                "name": name,
                "status": agent.status.value,
                "enabled": agent.config.enabled,
                "ai_enabled": agent.ai_enabled,
            })

        # Vault health
        vault_health = guardian.vault.health_report()

        # Gateway services
        services: list[dict[str, Any]] = []
        for svc_name in guardian.gateway.list_services():
            svc_status = guardian.gateway.service_status(svc_name)
            services.append({
                "name": svc_name,
                "circuit_state": svc_status.get("circuit_state", "unknown"),
            })

        # AI engine status
        ai_status = guardian.ai_engine.status()

        body = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": round(time.monotonic() - self.start_time, 2),
            "agents": agent_states,
            "vault": {
                "total_credentials": vault_health.get("total_credentials", 0),
                "due_for_rotation": vault_health.get("due_for_rotation", 0),
            },
            "gateway_services": services,
            "ai_engine": {
                "active_provider": ai_status.get("active_provider"),
                "ollama_available": ai_status.get("ollama", {}).get("available", False),
                "anthropic_available": ai_status.get("anthropic", {}).get("available", False),
                "total_requests": ai_status.get("total_requests", 0),
            },
        }
        self._send_json(body, status=200)

    def _handle_metrics(self) -> None:
        guardian = self.guardian
        if guardian is None:
            self._send_json({"error": "no guardian instance"}, status=503)
            return

        # Agent health count
        agents = guardian.list_agents()
        healthy_count = 0
        for name in agents:
            agent = guardian.get_agent(name)
            if agent and agent.status.value != "error":
                healthy_count += 1

        # Alert count from pending audit reviews
        alert_count = len(guardian.audit.pending_reviews())

        # Audit entry count
        audit_entry_count = guardian.audit._total_recorded

        # Net worth from CFO if available
        net_worth = None
        cfo = guardian.get_agent("cfo")
        if cfo is not None:
            try:
                report = cfo.report()
                if hasattr(report, "data") and "net_worth" in report.data:
                    net_worth = report.data["net_worth"]
            except Exception:
                pass

        # Last sync time — look for most recent sync-related audit entry
        last_sync: str | None = None
        for entry in reversed(list(guardian.audit._entries)):
            if "sync" in entry.action.lower():
                last_sync = entry.timestamp
                break

        body = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agents_healthy": healthy_count,
            "agents_total": len(agents),
            "alert_count": alert_count,
            "audit_entry_count": audit_entry_count,
            "net_worth": net_worth,
            "last_sync_time": last_sync,
        }
        self._send_json(body, status=200)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _send_json(self, data: dict[str, Any], *, status: int = 200) -> None:
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class HealthServer:
    """Lightweight HTTP health-check server for Guardian One.

    Binds to ``127.0.0.1`` only (never externally exposed) and runs in a
    daemon thread so it won't block the main process.

    Usage::

        server = HealthServer(guardian, port=5200)
        server.start()
        # … later …
        server.stop()
    """

    def __init__(self, guardian: GuardianOne, port: int = 5200) -> None:
        self._guardian = guardian
        self._port = port
        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._start_time: float = 0.0

    def start(self) -> None:
        """Start the health server in a background daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return  # already running

        self._start_time = time.monotonic()

        # Build a handler subclass bound to this server's state.
        handler = type(
            "_BoundHealthHandler",
            (_HealthHandler,),
            {
                "guardian": self._guardian,
                "start_time": self._start_time,
            },
        )

        self._httpd = HTTPServer(("127.0.0.1", self._port), handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="guardian-health",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Shut down the health server."""
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    @property
    def port(self) -> int:
        return self._port

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
