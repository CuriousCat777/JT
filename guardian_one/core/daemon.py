"""Daemon — headless runner for Guardian One with optional health API.

Runs agents on their configured intervals without an interactive prompt.
Exposes an HTTP health endpoint for monitoring by systemd, Docker, or
load balancers.

Usage (via main.py):
    python main.py --daemon                          # health API on :8080
    python main.py --daemon --daemon-health-port 9090  # custom port
    python main.py --daemon --no-health              # without health API
"""

from __future__ import annotations

import json
import signal
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import TYPE_CHECKING

import schedule

from guardian_one.core.audit import Severity

if TYPE_CHECKING:
    from guardian_one.core.guardian import GuardianOne


class _HealthHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for /health and /status endpoints."""

    # Reference to the DaemonRunner set by DaemonRunner._start_health_server
    daemon: DaemonRunner | None = None

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._respond_health()
        elif self.path == "/status":
            self._respond_status()
        else:
            self.send_error(404)

    def _respond_health(self) -> None:
        """Lightweight liveness probe."""
        assert self.daemon is not None
        body = {
            "status": "ok" if not self.daemon._stop_event.is_set() else "stopping",
            "uptime_seconds": self.daemon.uptime_seconds(),
            "agents": len(self.daemon.guardian.list_agents()),
        }
        self._json_response(200, body)

    def _respond_status(self) -> None:
        """Detailed readiness / status check."""
        assert self.daemon is not None
        agents_info = {}
        for name in self.daemon.guardian.list_agents():
            agent = self.daemon.guardian.get_agent(name)
            if agent is None:
                continue
            agents_info[name] = {
                "enabled": agent.config.enabled,
                "paused": name in self.daemon._paused,
                "status": agent.status.value if hasattr(agent, "status") else "unknown",
                "last_run": self.daemon._last_run.get(name),
                "interval_minutes": agent.config.schedule_interval_minutes,
            }

        health_snapshots = []
        try:
            for snap in self.daemon.guardian.monitor.all_health():
                health_snapshots.append({
                    "service": snap.service,
                    "circuit_state": snap.circuit_state,
                    "success_rate": snap.success_rate,
                    "risk_score": snap.risk_score,
                })
        except Exception:
            pass

        body = {
            "status": "ok" if not self.daemon._stop_event.is_set() else "stopping",
            "uptime_seconds": self.daemon.uptime_seconds(),
            "started_at": self.daemon._started_at.isoformat() if self.daemon._started_at else None,
            "agents": agents_info,
            "services": health_snapshots,
        }
        self._json_response(200, body)

    def _json_response(self, code: int, body: dict) -> None:
        payload = json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args) -> None:  # noqa: A002
        """Suppress default stderr logging from BaseHTTPRequestHandler."""
        pass


class DaemonRunner:
    """Headless scheduler with an optional HTTP health API."""

    def __init__(
        self,
        guardian: GuardianOne,
        *,
        health_port: int = 8080,
        enable_health: bool = True,
        config_path: str | None = None,
    ) -> None:
        self.guardian = guardian
        self._health_port = health_port
        self._enable_health = enable_health
        self._config_path = config_path
        self._paused: set[str] = set()
        self._stop_event = threading.Event()
        self._reload_event = threading.Event()
        self._lock = threading.Lock()
        self._last_run: dict[str, str] = {}
        self._started_at: datetime | None = None
        self._scheduler_thread: threading.Thread | None = None
        self._health_server: HTTPServer | None = None
        self._health_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _register_jobs(self) -> None:
        """Create a scheduled job for each enabled agent."""
        schedule.clear()
        for name in self.guardian.list_agents():
            agent = self.guardian.get_agent(name)
            if agent is None or not agent.config.enabled:
                continue
            interval = agent.config.schedule_interval_minutes
            if interval is None or interval < 1:
                self.guardian.audit.record(
                    agent="daemon",
                    action=f"invalid_schedule_interval:{name}",
                    severity=Severity.WARNING,
                    details={"schedule_interval_minutes": interval},
                )
                continue
            schedule.every(interval).minutes.do(self._run_agent_job, name)

        schedule.every().day.at("06:00").do(self._run_cfo_sync)
        schedule.every().day.at("18:00").do(self._run_cfo_sync)

    def _run_agent_job(self, name: str) -> None:
        with self._lock:
            if name in self._paused:
                return
        try:
            self.guardian.run_agent(name)
            with self._lock:
                self._last_run[name] = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            self.guardian.audit.record(
                agent="daemon",
                action=f"agent_error:{name}",
                severity=Severity.ERROR,
                details={"error": str(exc)},
            )

    def _run_cfo_sync(self) -> None:
        with self._lock:
            if "cfo" in self._paused:
                return
        try:
            from guardian_one.agents.cfo import CFO
            cfo = self.guardian.get_agent("cfo")
            if cfo and isinstance(cfo, CFO):
                cfo.sync_all()
                with self._lock:
                    self._last_run["cfo-sync"] = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            self.guardian.audit.record(
                agent="daemon",
                action="cfo_sync_error",
                severity=Severity.ERROR,
                details={"error": str(exc)},
            )

    # ------------------------------------------------------------------
    # Config reload (SIGHUP)
    # ------------------------------------------------------------------

    def _reload_config(self) -> None:
        """Reload configuration from disk and re-register scheduled jobs."""
        from guardian_one.core.config import load_config
        from pathlib import Path

        try:
            config_path = Path(self._config_path) if self._config_path else None
            new_config = load_config(config_path)
            self.guardian.config = new_config

            # Propagate updated agent configs into live agent instances
            new_agent_configs = getattr(new_config, "agents", {})
            if isinstance(new_agent_configs, dict):
                for name, agent_config in new_agent_configs.items():
                    agent = self.guardian.get_agent(name)
                    if agent is not None and hasattr(agent, "config"):
                        agent.config = agent_config

            self._register_jobs()
            self.guardian.audit.record(
                agent="daemon",
                action="config_reloaded",
                severity=Severity.INFO,
            )
            print("  Config reloaded.")
        except Exception as exc:
            self.guardian.audit.record(
                agent="daemon",
                action="config_reload_failed",
                severity=Severity.ERROR,
                details={"error": str(exc)},
            )
            print(f"  Config reload failed: {exc}")

    # ------------------------------------------------------------------
    # Background loops
    # ------------------------------------------------------------------

    def _tick_loop(self) -> None:
        while not self._stop_event.is_set():
            schedule.run_pending()
            self._stop_event.wait(timeout=1)

    def _start_health_server(self) -> None:
        """Start the HTTP health endpoint in a daemon thread."""
        handler_class = type(
            "_BoundHealthHandler",
            (_HealthHandler,),
            {"daemon": self},
        )
        self._health_server = HTTPServer(("127.0.0.1", self._health_port), handler_class)
        self._health_thread = threading.Thread(target=self._health_server.serve_forever, daemon=True)
        self._health_thread.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def uptime_seconds(self) -> float:
        if self._started_at is None:
            return 0.0
        delta = datetime.now(timezone.utc) - self._started_at
        return delta.total_seconds()

    def start(self) -> None:
        """Start the daemon: run initial cycle, schedule jobs, serve health API."""
        self._started_at = datetime.now(timezone.utc)

        # Graceful shutdown on SIGTERM and SIGINT (main thread only)
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)
        _is_main = threading.current_thread() is threading.main_thread()

        def _shutdown_handler(signum, frame):
            self._stop_event.set()

        def _reload_handler(signum, frame):
            self._reload_event.set()

        if _is_main:
            signal.signal(signal.SIGINT, _shutdown_handler)
            signal.signal(signal.SIGTERM, _shutdown_handler)
            if hasattr(signal, "SIGHUP"):
                signal.signal(signal.SIGHUP, _reload_handler)

        self._register_jobs()

        # Run all agents once at startup
        print(f"  Guardian One Daemon — starting up")
        print(f"  Owner: {self.guardian.config.owner}")
        print(f"  Agents: {', '.join(self.guardian.list_agents())}")
        print("  Running initial cycle...")

        reports = self.guardian.run_all()
        for r in reports:
            with self._lock:
                self._last_run[r.agent_name] = datetime.now(timezone.utc).isoformat()

        self.guardian.audit.record(
            agent="daemon",
            action="daemon_started",
            severity=Severity.INFO,
            details={"health_port": self._health_port if self._enable_health else None},
        )

        # Start health API
        if self._enable_health:
            self._start_health_server()
            print(f"  Health API listening on :{self._health_port}")

        # Start scheduler thread
        self._scheduler_thread = threading.Thread(target=self._tick_loop, daemon=True)
        self._scheduler_thread.start()

        print("  Daemon running. Send SIGTERM or Ctrl+C to stop, SIGHUP to reload config.")

        # Block main thread; wake on stop or reload
        try:
            while not self._stop_event.is_set():
                self._stop_event.wait(timeout=1)
                if self._reload_event.is_set():
                    self._reload_config()
                    self._reload_event.clear()
        except KeyboardInterrupt:
            pass

        # Shutdown
        if self._health_server:
            self._health_server.shutdown()
        self._stop_event.set()
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)
        schedule.clear()

        self.guardian.audit.record(
            agent="daemon",
            action="daemon_stopped",
            severity=Severity.INFO,
        )
        print("\n  Daemon stopped.")

        if _is_main:
            signal.signal(signal.SIGINT, original_sigint)
            signal.signal(signal.SIGTERM, original_sigterm)
            if hasattr(signal, "SIGHUP"):
                signal.signal(signal.SIGHUP, signal.SIG_DFL)
