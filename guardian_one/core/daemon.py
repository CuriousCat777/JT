"""Guardian One Daemon — headless scheduler with health endpoints.

Runs all agents on their configured intervals in the background,
exposes a Flask health server for monitoring, and persists run state
to disk so restarts pick up where they left off.
"""

from __future__ import annotations

import json
import signal
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import schedule
from flask import Flask, jsonify

from guardian_one.core.audit import Severity

if TYPE_CHECKING:
    from guardian_one.core.guardian import GuardianOne


_DEFAULT_PORT = 5200
_MAX_CONSECUTIVE_FAILURES = 5
_AUTO_RESUME_SECONDS = 300  # Resume paused agents after 5 minutes of cool-down
_STATE_FILE = "daemon_state.json"


class GuardianDaemon:
    """Headless daemon that schedules agents and serves health checks."""

    def __init__(
        self,
        guardian: GuardianOne,
        port: int = _DEFAULT_PORT,
    ) -> None:
        self._guardian = guardian
        self._port = port
        self._running = False
        self._start_time: float = 0.0
        self._lock = threading.Lock()
        self._cycle_count: int = 0  # kept for metrics, not used for resume timing

        # Per-agent tracking: {"agent_name": {"last_run": iso|null, "errors": int, "runs": int, "paused": bool}}
        self._agent_state: dict[str, dict] = {}

        state_dir = Path(self._guardian.config.data_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
        self._state_path = state_dir / _STATE_FILE

        self._load_state()
        self._app = self._build_app()
        self._server_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_agent_state(raw: object) -> dict:
        """Return a validated per-agent state dict with safe defaults."""
        if not isinstance(raw, dict):
            raw = {}
        last_run = raw.get("last_run")
        if last_run is not None and not isinstance(last_run, str):
            last_run = None
        errors = raw.get("errors", 0)
        if not isinstance(errors, int) or isinstance(errors, bool):
            errors = 0
        runs = raw.get("runs", 0)
        if not isinstance(runs, int) or isinstance(runs, bool):
            runs = 0
        paused = raw.get("paused", False)
        if not isinstance(paused, bool):
            paused = False
        result = {"last_run": last_run, "errors": errors, "runs": runs, "paused": paused}
        # Preserve paused_at timestamp if present
        paused_at = raw.get("paused_at")
        if isinstance(paused_at, str):
            result["paused_at"] = paused_at
        return result

    def _load_state(self) -> None:
        """Restore agent state from disk if available."""
        self._agent_state = {}
        if self._state_path.exists():
            try:
                data = json.loads(self._state_path.read_text())
                if isinstance(data, dict):
                    for name, state in data.items():
                        if isinstance(name, str):
                            self._agent_state[name] = self._normalize_agent_state(state)
            except (json.JSONDecodeError, OSError):
                self._agent_state = {}

        # Ensure every registered agent has a state entry.
        for name in self._guardian.list_agents():
            if name not in self._agent_state:
                self._agent_state[name] = self._normalize_agent_state({})

    def _save_state(self) -> None:
        """Persist agent state to disk."""
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(json.dumps(self._agent_state, indent=2))
        except OSError:
            pass  # Non-fatal; state is also in memory.

    # ------------------------------------------------------------------
    # Agent execution
    # ------------------------------------------------------------------

    def _run_agent(self, name: str) -> None:
        """Execute a single agent, tracking results and errors."""
        with self._lock:
            state = self._agent_state.get(name)
            if state is None:
                return
            if state.get("paused"):
                return

        try:
            report = self._guardian.run_agent(name)
            now = datetime.now(timezone.utc).isoformat()
            with self._lock:
                state = self._agent_state[name]
                state["last_run"] = now
                state["runs"] = state.get("runs", 0) + 1
                # Reset consecutive error counter on success.
                if report.status != "error":
                    state["errors"] = 0
                else:
                    self._record_error(name, state)
                self._save_state()
        except Exception as exc:
            now = datetime.now(timezone.utc).isoformat()
            with self._lock:
                state = self._agent_state.setdefault(name, {
                    "last_run": None, "errors": 0, "runs": 0, "paused": False,
                })
                state["last_run"] = now
                state["runs"] = state.get("runs", 0) + 1
                self._record_error(name, state, str(exc))
                self._save_state()

    def _record_error(self, name: str, state: dict, detail: str = "") -> None:
        """Increment error count and auto-pause after too many consecutive failures."""
        state["errors"] = state.get("errors", 0) + 1
        if state["errors"] >= _MAX_CONSECUTIVE_FAILURES and not state.get("paused"):
            state["paused"] = True
            state["paused_at"] = datetime.now(timezone.utc).isoformat()
            self._guardian.audit.record(
                agent="daemon",
                action="agent_auto_paused",
                severity=Severity.WARNING,
                details={
                    "agent": name,
                    "consecutive_errors": state["errors"],
                    "reason": detail or "too many consecutive failures",
                    "will_resume_after_seconds": _AUTO_RESUME_SECONDS,
                },
            )

    def _try_resume_paused(self) -> None:
        """Auto-resume agents paused by transient failures after a cool-down period.

        Cool-down is ``_AUTO_RESUME_SECONDS`` (default 300 = 5 minutes).
        Uses wall-clock timestamps, not tick counts, for accurate timing.
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            for name, state in self._agent_state.items():
                if not state.get("paused"):
                    continue
                paused_at_iso = state.get("paused_at")
                if not paused_at_iso:
                    continue
                try:
                    paused_at = datetime.fromisoformat(paused_at_iso)
                    elapsed = (now - paused_at).total_seconds()
                except (ValueError, TypeError):
                    continue
                if elapsed >= _AUTO_RESUME_SECONDS:
                    state["paused"] = False
                    state["errors"] = 0
                    state.pop("paused_at", None)
                    self._save_state()
                    self._guardian.audit.record(
                        agent="daemon",
                        action="agent_auto_resumed",
                        severity=Severity.INFO,
                        details={
                            "agent": name,
                            "cool_down_seconds": round(elapsed),
                        },
                    )

    # ------------------------------------------------------------------
    # Schedule setup
    # ------------------------------------------------------------------

    def _schedule_agents(self) -> None:
        """Register each enabled agent with the ``schedule`` library.

        If an agent has a restored ``last_run`` timestamp, calculate
        remaining time so we honour the configured interval rather than
        always waiting a full cycle after restart.
        """
        now = datetime.now(timezone.utc)
        for name in self._guardian.list_agents():
            agent = self._guardian.get_agent(name)
            if agent is None:
                continue
            if not agent.config.enabled:
                continue
            interval = getattr(agent.config, "schedule_interval_minutes", 15)
            job = schedule.every(interval).minutes.do(self._run_agent, name)

            # If the agent ran recently, adjust next_run so we don't
            # wait a full interval after a quick restart.
            state = self._agent_state.get(name, {})
            last_run_iso = state.get("last_run")
            if last_run_iso and job is not None:
                try:
                    last_run = datetime.fromisoformat(last_run_iso)
                    elapsed = (now - last_run).total_seconds()
                    remaining = (interval * 60) - elapsed
                    if remaining <= 0:
                        # Overdue — run on next tick
                        job.next_run = datetime.now()
                    else:
                        from datetime import timedelta
                        job.next_run = datetime.now() + timedelta(seconds=remaining)
                except (ValueError, TypeError):
                    pass  # Malformed timestamp; fall back to default

        self._guardian.audit.record(
            agent="daemon",
            action="scheduler_ready",
            severity=Severity.INFO,
            details={"agents_scheduled": len(schedule.get_jobs())},
        )

    # ------------------------------------------------------------------
    # Flask health server
    # ------------------------------------------------------------------

    def _build_app(self) -> Flask:
        app = Flask("guardian_one_health")
        app.logger.disabled = True

        @app.route("/health")
        def health():  # type: ignore[reportUnusedFunction]
            uptime = time.monotonic() - self._start_time if self._start_time else 0
            healthy = self._running
            payload = {
                "status": "healthy" if healthy else "unhealthy",
                "uptime_seconds": round(uptime, 1),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            return jsonify(payload), 200 if healthy else 503

        @app.route("/status")
        def status():  # type: ignore[reportUnusedFunction]
            with self._lock:
                snapshot = {k: dict(v) for k, v in self._agent_state.items()}
            return jsonify({"agents": snapshot})

        @app.route("/metrics")
        def metrics():  # type: ignore[reportUnusedFunction]
            with self._lock:
                total_runs = sum(s.get("runs", 0) for s in self._agent_state.values())
                total_errors = sum(s.get("errors", 0) for s in self._agent_state.values())
                agent_count = len(self._agent_state)
            uptime = time.monotonic() - self._start_time if self._start_time else 0
            return jsonify({
                "agent_count": agent_count,
                "total_runs": total_runs,
                "total_errors": total_errors,
                "uptime_seconds": round(uptime, 1),
            })

        return app

    def _start_health_server(self) -> None:
        """Run the Flask health server in a daemon thread."""
        self._server_thread = threading.Thread(
            target=self._app.run,
            kwargs={"host": "127.0.0.1", "port": self._port, "use_reloader": False},
            daemon=True,
        )
        self._server_thread.start()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Block the calling thread, running scheduled agents and the health server."""
        self._running = True
        self._start_time = time.monotonic()

        # Wire up graceful shutdown on SIGTERM / SIGINT (main thread only).
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, self._handle_signal)
            signal.signal(signal.SIGINT, self._handle_signal)

        self._schedule_agents()
        self._start_health_server()

        self._guardian.audit.record(
            agent="daemon",
            action="daemon_started",
            severity=Severity.INFO,
            details={"port": self._port},
        )

        # Tick loop — runs pending jobs every second.
        while self._running:
            schedule.run_pending()
            self._cycle_count += 1
            self._try_resume_paused()
            time.sleep(1)

        # After loop exits, persist final state.
        self._save_state()
        self._guardian.audit.record(
            agent="daemon",
            action="daemon_stopped",
            severity=Severity.INFO,
            details={"uptime_seconds": round(time.monotonic() - self._start_time, 1)},
        )

    def stop(self) -> None:
        """Signal the daemon to shut down gracefully."""
        self._running = False

    def _handle_signal(self, signum: int, _frame: object) -> None:
        """Handle SIGTERM/SIGINT for graceful shutdown."""
        self._guardian.audit.record(
            agent="daemon",
            action="signal_received",
            severity=Severity.INFO,
            details={"signal": signum},
        )
        self.stop()
