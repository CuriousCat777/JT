"""Scheduler — interactive background runner for Guardian One agents.

Runs agents on their configured intervals while giving Jeremy full control
via an interactive command prompt.

Commands (while running):
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

import signal
import sys
import threading
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import schedule

from guardian_one.core.audit import Severity

if TYPE_CHECKING:
    from guardian_one.core.guardian import GuardianOne


class Scheduler:
    """Interactive scheduler that runs agents on configured intervals."""

    def __init__(self, guardian: GuardianOne) -> None:
        self.guardian = guardian
        self._paused: set[str] = set()
        self._stop_event = threading.Event()
        self._scheduler_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_run: dict[str, str] = {}

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
                _print_report_brief(name, report)
            except Exception as exc:
                print(f"\n  [{name}] Error: {exc}")

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
            try:
                schedule.run_pending()
            except Exception as exc:
                self.guardian.audit.record(
                    agent="scheduler",
                    action="tick_error",
                    severity=Severity.ERROR,
                    details={"error_type": type(exc).__name__},
                    requires_review=True,
                )
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
                if minutes < 1 or minutes > 1440:
                    raise ValueError
            except ValueError:
                print("  Interval must be a positive integer (1–1440 minutes).")
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
