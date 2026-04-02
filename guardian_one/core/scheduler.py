"""Scheduler — background runner for Guardian One agents.

Supports two modes:
    Interactive (--schedule): agents run on intervals with a command prompt.
    Daemon (--daemon): headless 24/7 operation for systemd / background use.

Commands (interactive mode):
    status             — Show all agents and their next run time
    run <agent>        — Run an agent immediately
    run all            — Run all agents immediately
    pause <agent>      — Pause an agent (skip scheduled runs)
    resume <agent>     — Resume a paused agent
    summary            — Print the daily summary
    dashboard          — Print CFO financial dashboard
    interval <agent> N — Change an agent's interval to N minutes
    stop / quit / q    — Graceful shutdown
    help               — Show this command list
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import schedule

from guardian_one.core.audit import Severity

if TYPE_CHECKING:
    from guardian_one.core.guardian import GuardianOne

log = logging.getLogger("guardian_one.scheduler")

# Default error budget: disable agent after this many consecutive failures
_DEFAULT_ERROR_BUDGET = 5


class Scheduler:
    """Scheduler that runs agents on configured intervals.

    Supports interactive mode (with command prompt) and daemon mode
    (headless, for systemd / 24/7 operation).
    """

    def __init__(self, guardian: GuardianOne) -> None:
        self.guardian = guardian
        self._paused: set[str] = set()
        self._stop_event = threading.Event()
        self._scheduler_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_run: dict[str, str] = {}
        self._consecutive_errors: dict[str, int] = {}
        self._error_budget = _DEFAULT_ERROR_BUDGET

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
            schedule.every(interval).minutes.do(self._run_agent_job, name)

        # Daily CFO financial sync — pulls latest from Plaid/Empower
        schedule.every().day.at("06:00").do(self._run_cfo_sync)
        # Also run a mid-day check
        schedule.every().day.at("18:00").do(self._run_cfo_sync)

    def _run_agent_job(self, name: str) -> None:
        """Execute a single agent's run cycle (called by scheduler)."""
        with self._lock:
            if name in self._paused:
                return
            try:
                report = self.guardian.run_agent(name)
                self._last_run[name] = datetime.now(timezone.utc).isoformat()
                self._consecutive_errors[name] = 0  # reset on success
                _print_report_brief(name, report)
                log.info("Agent run complete", extra={
                    "agent": name, "status": report.status,
                })
            except Exception as exc:
                errors = self._consecutive_errors.get(name, 0) + 1
                self._consecutive_errors[name] = errors
                log.error("Agent run failed", extra={
                    "agent": name, "error": str(exc),
                    "consecutive_errors": errors,
                })
                print(f"\n  [{name}] Error ({errors}/{self._error_budget}): {exc}")

                # Error budget: auto-pause after too many consecutive failures
                if errors >= self._error_budget:
                    self._paused.add(name)
                    self.guardian.audit.record(
                        agent="scheduler",
                        action=f"agent_auto_paused:{name}",
                        severity=Severity.WARNING,
                        details={
                            "reason": "error_budget_exhausted",
                            "consecutive_errors": errors,
                        },
                        requires_review=True,
                    )
                    log.warning(
                        "Agent auto-paused after %d consecutive errors",
                        errors, extra={"agent": name},
                    )
                    print(f"  [{name}] AUTO-PAUSED — {errors} consecutive failures")

    def _run_cfo_sync(self) -> None:
        """Daily CFO financial sync — pulls latest from all connected providers."""
        with self._lock:
            if "cfo" in self._paused:
                return
            try:
                from guardian_one.agents.cfo import CFO
                cfo = self.guardian.get_agent("cfo")
                if not cfo or not isinstance(cfo, CFO):
                    return

                ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
                print(f"\n  [cfo-sync] Daily financial sync starting ({ts})...")

                results = cfo.sync_all()
                nw = results.get("net_worth", 0)
                accts = results.get("account_count", 0)
                txns = results.get("transaction_count", 0)

                # Plaid summary
                plaid = results.get("plaid", {})
                if plaid.get("connected"):
                    print(f"  [cfo-sync] Plaid: +{plaid.get('accounts_added', 0)} accts, "
                          f"+{plaid.get('transactions_added', 0)} txns "
                          f"from {plaid.get('institutions', 0)} bank(s)")

                # Empower summary
                emp = results.get("empower", {})
                if emp.get("connected"):
                    print(f"  [cfo-sync] Empower: +{emp.get('accounts_added', 0)} accts, "
                          f"+{emp.get('transactions_added', 0)} txns")

                print(f"  [cfo-sync] Net worth: ${nw:,.2f} | {accts} accounts | {txns} transactions")

                # Budget alerts
                alerts = results.get("budget_alerts", [])
                for alert in alerts:
                    print(f"  [cfo-sync] [!] {alert}")

                self._last_run["cfo-sync"] = datetime.now(timezone.utc).isoformat()
            except Exception as exc:
                print(f"\n  [cfo-sync] Error: {exc}")

    # ------------------------------------------------------------------
    # Background thread
    # ------------------------------------------------------------------

    def _tick_loop(self) -> None:
        """Run pending scheduled jobs until stop is signaled."""
        while not self._stop_event.is_set():
            schedule.run_pending()
            self._stop_event.wait(timeout=1)

    # ------------------------------------------------------------------
    # Interactive commands
    # ------------------------------------------------------------------

    def _handle_command(self, raw: str) -> bool:
        """Process a command. Return False to exit the loop."""
        parts = raw.strip().split()
        if not parts:
            return True

        cmd = parts[0].lower()

        if cmd in ("stop", "quit", "q"):
            return False

        elif cmd == "help":
            print(HELP_TEXT)

        elif cmd == "status":
            self._cmd_status()

        elif cmd == "summary":
            print(self.guardian.daily_summary())

        elif cmd == "dashboard":
            from guardian_one.agents.cfo import CFO
            import json
            cfo = self.guardian.get_agent("cfo")
            if cfo and isinstance(cfo, CFO):
                print(json.dumps(cfo.dashboard(), indent=2, default=str))
            else:
                print("  CFO agent not available.")

        elif cmd == "run" and len(parts) >= 2:
            target = parts[1].lower()
            if target == "all":
                print("  Running all agents...")
                reports = self.guardian.run_all()
                for r in reports:
                    _print_report_brief(r.agent_name, r)
                    self._last_run[r.agent_name] = datetime.now(timezone.utc).isoformat()
            elif target in self.guardian.list_agents():
                print(f"  Running {target}...")
                report = self.guardian.run_agent(target)
                self._last_run[target] = datetime.now(timezone.utc).isoformat()
                _print_report_brief(target, report)
            else:
                print(f"  Unknown agent: {target}")
                print(f"  Available: {', '.join(self.guardian.list_agents())}")

        elif cmd == "pause" and len(parts) >= 2:
            target = parts[1].lower()
            if target in self.guardian.list_agents():
                with self._lock:
                    self._paused.add(target)
                self.guardian.audit.record(
                    agent="scheduler",
                    action=f"agent_paused:{target}",
                    severity=Severity.INFO,
                    details={"paused_by": "owner"},
                )
                print(f"  {target} paused — scheduled runs will be skipped.")
            else:
                print(f"  Unknown agent: {target}")

        elif cmd == "resume" and len(parts) >= 2:
            target = parts[1].lower()
            with self._lock:
                is_paused = target in self._paused
                if is_paused:
                    self._paused.discard(target)
            if is_paused:
                self.guardian.audit.record(
                    agent="scheduler",
                    action=f"agent_resumed:{target}",
                    severity=Severity.INFO,
                    details={"resumed_by": "owner"},
                )
                print(f"  {target} resumed.")
            elif target in self.guardian.list_agents():
                print(f"  {target} is not paused.")
            else:
                print(f"  Unknown agent: {target}")

        elif cmd == "interval" and len(parts) >= 3:
            target = parts[1].lower()
            try:
                minutes = int(parts[2])
                if minutes < 1:
                    raise ValueError
            except ValueError:
                print("  Interval must be a positive integer (minutes).")
                return True
            agent = self.guardian.get_agent(target)
            if agent:
                agent.config.schedule_interval_minutes = minutes
                self._register_jobs()  # rebuild schedule with new interval
                print(f"  {target} interval changed to {minutes} min.")
            else:
                print(f"  Unknown agent: {target}")

        elif cmd == "sync":
            print("  Running CFO financial sync now...")
            self._run_cfo_sync()

        else:
            print(f"  Unknown command: {raw.strip()}")
            print("  Type 'help' for available commands.")

        return True

    def _cmd_status(self) -> None:
        """Print status of all agents."""
        now = datetime.now(timezone.utc)
        print()
        print(f"  {'Agent':<14} {'Interval':<12} {'Status':<12} {'Last Run'}")
        print(f"  {'─' * 14} {'─' * 12} {'─' * 12} {'─' * 24}")
        for name in self.guardian.list_agents():
            agent = self.guardian.get_agent(name)
            if agent is None:
                continue
            interval = f"{agent.config.schedule_interval_minutes} min"
            if name in self._paused:
                status = "PAUSED"
            elif not agent.config.enabled:
                status = "DISABLED"
            else:
                status = "active"
            last = self._last_run.get(name, "—")
            print(f"  {name:<14} {interval:<12} {status:<12} {last}")
        print()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the scheduler and enter the interactive command loop."""
        # Handle Ctrl+C gracefully
        original_sigint = signal.getsignal(signal.SIGINT)

        def _sigint_handler(signum, frame):
            print("\n  Caught Ctrl+C — shutting down...")
            self._stop_event.set()

        signal.signal(signal.SIGINT, _sigint_handler)

        self._register_jobs()

        # Run all agents once at startup
        print("\n  Guardian One Scheduler — starting up")
        print(f"  Owner: {self.guardian.config.owner}")
        print(f"  Agents: {', '.join(self.guardian.list_agents())}")
        print("  Running initial cycle...")
        print()

        reports = self.guardian.run_all()
        for r in reports:
            _print_report_brief(r.agent_name, r)
            self._last_run[r.agent_name] = datetime.now(timezone.utc).isoformat()

        self.guardian.audit.record(
            agent="scheduler",
            action="scheduler_started",
            severity=Severity.INFO,
        )

        # Start background scheduler thread
        self._scheduler_thread = threading.Thread(
            target=self._tick_loop, daemon=True
        )
        self._scheduler_thread.start()

        print()
        print("  Scheduler running. Type 'help' for commands, 'stop' to quit.")
        print()

        # Interactive command loop (main thread)
        try:
            while not self._stop_event.is_set():
                try:
                    cmd = input("guardian> ")
                except EOFError:
                    break
                if not self._handle_command(cmd):
                    break
        except KeyboardInterrupt:
            pass

        # Shutdown
        self._stop_event.set()
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)
        schedule.clear()

        self.guardian.audit.record(
            agent="scheduler",
            action="scheduler_stopped",
            severity=Severity.INFO,
            details={"stopped_by": "owner"},
        )
        print("\n  Scheduler stopped. Goodbye, Jeremy.")

        # Restore original handler
        signal.signal(signal.SIGINT, original_sigint)

    # ------------------------------------------------------------------
    # Daemon mode — headless 24/7 operation
    # ------------------------------------------------------------------

    def start_daemon(
        self,
        health_port: int = 8080,
        enable_health: bool = True,
    ) -> None:
        """Start in daemon mode — headless, for systemd / 24/7 operation.

        No interactive prompt. Responds to SIGTERM/SIGHUP for graceful
        shutdown and config reload. Optionally starts the health API.
        Sends systemd watchdog pings if WatchdogSec is configured.
        """
        log.info("Starting Guardian One in daemon mode")

        # Signal handlers for systemd
        def _shutdown_handler(signum, frame):
            sig_name = signal.Signals(signum).name
            log.info("Received %s — shutting down", sig_name)
            self._stop_event.set()

        def _reload_handler(signum, frame):
            log.info("Received SIGHUP — reloading agent schedules")
            self._register_jobs()
            self.guardian.audit.record(
                agent="scheduler",
                action="config_reloaded",
                severity=Severity.INFO,
                details={"trigger": "SIGHUP"},
            )

        signal.signal(signal.SIGTERM, _shutdown_handler)
        signal.signal(signal.SIGINT, _shutdown_handler)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, _reload_handler)

        # Register scheduled jobs
        self._register_jobs()

        # Start health API if requested
        health_server = None
        if enable_health:
            try:
                from guardian_one.core.health import HealthServer
                health_server = HealthServer(self.guardian, port=health_port)
                health_server.start(daemon=True)
                log.info("Health API started on port %d", health_port)
            except Exception as exc:
                log.warning("Health API failed to start: %s", exc)

        # Initial run
        log.info("Running initial agent cycle")
        reports = self.guardian.run_all()
        for r in reports:
            self._last_run[r.agent_name] = datetime.now(timezone.utc).isoformat()
            log.info("Initial run: %s=%s", r.agent_name, r.status)

        self.guardian.audit.record(
            agent="scheduler",
            action="daemon_started",
            severity=Severity.INFO,
            details={
                "agents": self.guardian.list_agents(),
                "health_port": health_port if enable_health else None,
                "pid": os.getpid(),
            },
        )

        # Notify systemd we're ready
        _sd_notify("READY=1")
        _sd_notify(f"STATUS=Running {len(self.guardian.list_agents())} agents")

        # Start background tick thread
        self._scheduler_thread = threading.Thread(
            target=self._tick_loop, daemon=True,
        )
        self._scheduler_thread.start()

        # Main loop: sleep + watchdog pings (no interactive prompt)
        watchdog_usec = int(os.environ.get("WATCHDOG_USEC", "0"))
        watchdog_interval = (watchdog_usec / 1_000_000 / 2) if watchdog_usec else 30

        log.info(
            "Daemon running (PID=%d, watchdog_interval=%.1fs)",
            os.getpid(), watchdog_interval,
        )

        while not self._stop_event.is_set():
            _sd_notify("WATCHDOG=1")

            # Periodic status update for systemd
            active = len(self.guardian.list_agents()) - len(self._paused)
            _sd_notify(f"STATUS={active} agents active, "
                       f"{len(self._paused)} paused")

            self._stop_event.wait(timeout=watchdog_interval)

        # Graceful shutdown
        log.info("Daemon shutting down")
        _sd_notify("STOPPING=1")
        self._stop_event.set()
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=10)
        schedule.clear()

        self.guardian.audit.record(
            agent="scheduler",
            action="daemon_stopped",
            severity=Severity.INFO,
            details={"pid": os.getpid()},
        )
        log.info("Daemon stopped cleanly")

    @property
    def error_counts(self) -> dict[str, int]:
        """Return consecutive error counts per agent (for monitoring)."""
        with self._lock:
            return dict(self._consecutive_errors)

    @property
    def paused_agents(self) -> set[str]:
        """Return the set of paused agents."""
        with self._lock:
            return set(self._paused)


def _sd_notify(state: str) -> None:
    """Send a notification to systemd (sd_notify protocol).

    This implements the sd_notify socket protocol directly, avoiding
    the need for the python-systemd package.
    """
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return
    try:
        if addr.startswith("@"):
            addr = "\0" + addr[1:]
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.sendto(state.encode(), addr)
        sock.close()
    except OSError:
        pass  # not running under systemd — that's fine


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _print_report_brief(name: str, report) -> None:
    """Print a one-line report summary."""
    status = report.status
    alerts = len(report.alerts) if report.alerts else 0
    line = f"  [{name}] {status} — {report.summary}"
    if alerts:
        line += f"  ({alerts} alert{'s' if alerts > 1 else ''})"
    print(line)


HELP_TEXT = """
  Guardian One Scheduler — Commands
  ──────────────────────────────────
  status             Show all agents and their schedule
  run <agent>        Run an agent right now
  run all            Run all agents right now
  pause <agent>      Pause an agent (skip scheduled runs)
  resume <agent>     Resume a paused agent
  interval <agent> N Change agent's interval to N minutes
  summary            Print daily summary
  dashboard          Print CFO financial dashboard
  stop / quit / q    Shut down the scheduler
  help               Show this message
"""
