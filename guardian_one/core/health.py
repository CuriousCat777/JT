"""Health check API — lightweight Flask endpoints for monitoring.

Provides /health, /ready, and /status endpoints for load balancers,
uptime monitors, and operational dashboards.

Usage:
    from guardian_one.core.health import HealthServer
    server = HealthServer(guardian)
    server.start(port=8080)  # runs in background thread
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from flask import Flask, jsonify

if TYPE_CHECKING:
    from guardian_one.core.guardian import GuardianOne


class HealthServer:
    """Background HTTP server exposing health/status endpoints."""

    def __init__(self, guardian: GuardianOne, port: int = 8080) -> None:
        self.guardian = guardian
        self.port = port
        self._app = Flask("guardian_health")
        self._thread: threading.Thread | None = None
        self._start_time = datetime.now(timezone.utc)
        self._register_routes()

    def _register_routes(self) -> None:
        app = self._app

        @app.route("/health")
        def health() -> tuple[Any, int]:
            """Liveness probe — is the process alive?"""
            return jsonify({"status": "ok", "timestamp": _now()}), 200

        @app.route("/ready")
        def ready() -> tuple[Any, int]:
            """Readiness probe — are agents registered and running?"""
            agents = self.guardian.list_agents()
            if not agents:
                return jsonify({
                    "status": "not_ready",
                    "reason": "no agents registered",
                }), 503
            return jsonify({
                "status": "ready",
                "agents": len(agents),
                "timestamp": _now(),
            }), 200

        @app.route("/status")
        def status() -> tuple[Any, int]:
            """Full system status for dashboards."""
            agents = self.guardian.list_agents()
            agent_statuses = {}
            for name in agents:
                agent = self.guardian.get_agent(name)
                if agent:
                    agent_statuses[name] = {
                        "status": agent.status.value,
                        "ai_enabled": agent.ai_enabled,
                    }

            ai_info = self.guardian.ai_status()
            uptime = (datetime.now(timezone.utc) - self._start_time).total_seconds()

            return jsonify({
                "status": "operational",
                "uptime_seconds": round(uptime, 1),
                "owner": self.guardian.config.owner,
                "agents": agent_statuses,
                "ai_engine": {
                    "active_provider": ai_info.get("active_provider", "offline"),
                    "total_requests": ai_info.get("total_requests", 0),
                },
                "homelink": {
                    "services": len(self.guardian.gateway.list_services()),
                    "vault_credentials": self.guardian.vault.health_report()["total_credentials"],
                },
                "timestamp": _now(),
            }), 200

        @app.route("/metrics")
        def metrics() -> tuple[Any, int]:
            """Prometheus-compatible metrics (text format)."""
            agents = self.guardian.list_agents()
            ai_info = self.guardian.ai_status()
            uptime = (datetime.now(timezone.utc) - self._start_time).total_seconds()

            lines = [
                f'# HELP guardian_uptime_seconds Time since boot',
                f'# TYPE guardian_uptime_seconds gauge',
                f'guardian_uptime_seconds {uptime:.1f}',
                f'# HELP guardian_agents_total Number of registered agents',
                f'# TYPE guardian_agents_total gauge',
                f'guardian_agents_total {len(agents)}',
                f'# HELP guardian_ai_requests_total Total AI reasoning requests',
                f'# TYPE guardian_ai_requests_total counter',
                f'guardian_ai_requests_total {ai_info.get("total_requests", 0)}',
                f'# HELP guardian_vault_credentials_total Stored credentials',
                f'# TYPE guardian_vault_credentials_total gauge',
                f'guardian_vault_credentials_total {self.guardian.vault.health_report()["total_credentials"]}',
            ]

            for name in agents:
                agent = self.guardian.get_agent(name)
                if agent:
                    running = 1 if agent.status.value == "running" else 0
                    lines.append(
                        f'guardian_agent_running{{agent="{name}"}} {running}'
                    )

            return "\n".join(lines) + "\n", 200, {"Content-Type": "text/plain"}

    def start(self, daemon: bool = True) -> None:
        """Start the health server in a background thread."""
        self._thread = threading.Thread(
            target=self._app.run,
            kwargs={"host": "0.0.0.0", "port": self.port, "use_reloader": False},
            daemon=daemon,
            name="guardian-health",
        )
        self._thread.start()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
