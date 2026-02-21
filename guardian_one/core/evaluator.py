"""Performance Evaluator — 5-point industry-standard agent rating system.

Evaluates sandbox agents on a daily cycle using five standardized metrics,
producing an overall performance score as a percentage.  The evaluation loop
continues indefinitely until the root user (Owner) enters:

    STOPSTOPSTOP

Rating Scale (Industry Standard — 5-Point):
    5 — Exceptional   (90-100%)  Consistently exceeds expectations
    4 — Proficient     (75-89%)   Meets all expectations reliably
    3 — Adequate       (50-74%)   Meets minimum requirements
    2 — Needs Work     (25-49%)   Below expectations
    1 — Critical       (0-24%)    Failing / non-functional

Metrics per agent:
    1. Availability    — Was the agent online and responsive?
    2. Task Completion — Ratio of successful runs to attempted runs
    3. Error Rate      — Inverse of errors per cycle (lower is better)
    4. Alert Handling  — Were alerts raised and surfaced correctly?
    5. Data Quality    — Did the report contain useful, actionable data?
"""

from __future__ import annotations

import json
import signal
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus

if TYPE_CHECKING:
    from guardian_one.core.guardian import GuardianOne
    from guardian_one.core.sandbox import SandboxDeployer


# ------------------------------------------------------------------
# Rating scale
# ------------------------------------------------------------------

RATING_SCALE = {
    5: {"label": "Exceptional", "range": "90-100%", "description": "Consistently exceeds expectations"},
    4: {"label": "Proficient",  "range": "75-89%",  "description": "Meets all expectations reliably"},
    3: {"label": "Adequate",    "range": "50-74%",  "description": "Meets minimum requirements"},
    2: {"label": "Needs Work",  "range": "25-49%",  "description": "Below expectations"},
    1: {"label": "Critical",    "range": "0-24%",   "description": "Failing / non-functional"},
}


def score_to_rating(score_pct: float) -> int:
    """Convert a percentage score to a 1-5 rating."""
    if score_pct >= 90:
        return 5
    elif score_pct >= 75:
        return 4
    elif score_pct >= 50:
        return 3
    elif score_pct >= 25:
        return 2
    else:
        return 1


# ------------------------------------------------------------------
# Metric evaluation
# ------------------------------------------------------------------

@dataclass
class MetricScore:
    """Score for a single evaluation metric."""
    name: str
    score_pct: float  # 0-100
    rating: int        # 1-5
    detail: str = ""


@dataclass
class AgentEvaluation:
    """Full evaluation for one agent in one cycle."""
    agent_name: str
    cycle: int
    timestamp: str
    metrics: list[MetricScore] = field(default_factory=list)
    overall_pct: float = 0.0
    overall_rating: int = 0
    rating_label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "cycle": self.cycle,
            "timestamp": self.timestamp,
            "metrics": [
                {"name": m.name, "score_pct": m.score_pct, "rating": m.rating, "detail": m.detail}
                for m in self.metrics
            ],
            "overall_pct": self.overall_pct,
            "overall_rating": self.overall_rating,
            "rating_label": self.rating_label,
        }


@dataclass
class EvaluationCycle:
    """One complete daily evaluation cycle across all sandbox agents."""
    cycle: int
    timestamp: str
    evaluations: list[AgentEvaluation] = field(default_factory=list)
    system_overall_pct: float = 0.0
    system_overall_rating: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle,
            "timestamp": self.timestamp,
            "evaluations": [e.to_dict() for e in self.evaluations],
            "system_overall_pct": self.system_overall_pct,
            "system_overall_rating": self.system_overall_rating,
        }


def _evaluate_agent(
    agent_name: str,
    report: AgentReport,
    agent_status: AgentStatus,
    cycle: int,
) -> AgentEvaluation:
    """Score an agent across the 5 industry-standard metrics."""
    metrics: list[MetricScore] = []
    now = datetime.now(timezone.utc).isoformat()

    # 1. Availability — is the agent online and not in error state?
    if agent_status in (AgentStatus.IDLE, AgentStatus.RUNNING):
        avail_pct = 100.0
        avail_detail = "Agent online and responsive"
    elif agent_status == AgentStatus.DISABLED:
        avail_pct = 0.0
        avail_detail = "Agent disabled"
    else:
        avail_pct = 25.0
        avail_detail = f"Agent in error state: {agent_status.value}"
    metrics.append(MetricScore("Availability", avail_pct, score_to_rating(avail_pct), avail_detail))

    # 2. Task Completion — did the run cycle complete with a valid report?
    if report.status in (AgentStatus.IDLE.value, "idle", "running"):
        completion_pct = 100.0
        completion_detail = "Run cycle completed successfully"
    elif report.status in (AgentStatus.ERROR.value, "error"):
        completion_pct = 20.0
        completion_detail = f"Run cycle failed: {report.summary}"
    elif report.status in (AgentStatus.DISABLED.value, "disabled"):
        completion_pct = 0.0
        completion_detail = "Agent disabled — no task completion"
    else:
        completion_pct = 50.0
        completion_detail = f"Unknown status: {report.status}"
    metrics.append(MetricScore("Task Completion", completion_pct, score_to_rating(completion_pct), completion_detail))

    # 3. Error Rate — penalize based on alerts (lower alerts = better)
    alert_count = len(report.alerts) if report.alerts else 0
    if alert_count == 0:
        error_pct = 100.0
        error_detail = "No errors or alerts"
    elif alert_count <= 2:
        error_pct = 75.0
        error_detail = f"{alert_count} alert(s) — within acceptable range"
    elif alert_count <= 5:
        error_pct = 50.0
        error_detail = f"{alert_count} alerts — elevated, needs monitoring"
    else:
        error_pct = max(0.0, 100.0 - (alert_count * 10))
        error_detail = f"{alert_count} alerts — high error rate"
    metrics.append(MetricScore("Error Rate", error_pct, score_to_rating(error_pct), error_detail))

    # 4. Alert Handling — did the agent surface actionable alerts/recommendations?
    recommendations = len(report.recommendations) if report.recommendations else 0
    actions = len(report.actions_taken) if report.actions_taken else 0
    if actions > 0 and recommendations >= 0:
        handling_pct = min(100.0, 60.0 + (actions * 10) + (recommendations * 5))
        handling_detail = f"{actions} actions taken, {recommendations} recommendations"
    elif actions == 0 and alert_count == 0:
        handling_pct = 80.0
        handling_detail = "No alerts to handle — nominal"
    else:
        handling_pct = 40.0
        handling_detail = "Alerts present but no actions taken"
    metrics.append(MetricScore("Alert Handling", handling_pct, score_to_rating(handling_pct), handling_detail))

    # 5. Data Quality — did the report contain meaningful data?
    data_fields = len(report.data) if report.data else 0
    has_summary = bool(report.summary and len(report.summary) > 10)
    if data_fields >= 3 and has_summary:
        quality_pct = 100.0
        quality_detail = f"Rich report: {data_fields} data fields, detailed summary"
    elif data_fields >= 1 and has_summary:
        quality_pct = 75.0
        quality_detail = f"Good report: {data_fields} data fields"
    elif has_summary:
        quality_pct = 50.0
        quality_detail = "Summary only, limited data"
    else:
        quality_pct = 20.0
        quality_detail = "Minimal or empty report"
    metrics.append(MetricScore("Data Quality", quality_pct, score_to_rating(quality_pct), quality_detail))

    # Overall
    overall_pct = round(sum(m.score_pct for m in metrics) / len(metrics), 1)
    overall_rating = score_to_rating(overall_pct)
    rating_label = RATING_SCALE[overall_rating]["label"]

    return AgentEvaluation(
        agent_name=agent_name,
        cycle=cycle,
        timestamp=now,
        metrics=metrics,
        overall_pct=overall_pct,
        overall_rating=overall_rating,
        rating_label=rating_label,
    )


# ------------------------------------------------------------------
# Evaluation loop
# ------------------------------------------------------------------

KILL_COMMAND = "STOPSTOPSTOP"

# How often to run evaluation cycles (in seconds)
# Default: 86400 (24 hours).  For demo/testing use a shorter interval.
DEFAULT_CYCLE_SECONDS = 86400


class PerformanceEvaluator:
    """Daily evaluation loop for sandbox agents.

    Runs Chronos and Archivist through their cycles, scores them on
    5 industry-standard metrics, and persists results.  Repeats every
    day until the owner enters STOPSTOPSTOP.
    """

    SANDBOX_AGENTS = ["chronos", "archivist"]

    def __init__(
        self,
        guardian: "GuardianOne",
        data_dir: str = "data",
        cycle_seconds: int = DEFAULT_CYCLE_SECONDS,
    ) -> None:
        self.guardian = guardian
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._eval_file = self._data_dir / "evaluations.jsonl"
        self._cycle_seconds = cycle_seconds
        self._cycle_count = 0
        self._history: list[EvaluationCycle] = []
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Single evaluation cycle
    # ------------------------------------------------------------------

    def run_cycle(self) -> EvaluationCycle:
        """Execute one evaluation cycle: run agents, score them, persist."""
        self._cycle_count += 1
        now = datetime.now(timezone.utc).isoformat()
        evaluations: list[AgentEvaluation] = []

        for agent_name in self.SANDBOX_AGENTS:
            agent = self.guardian.get_agent(agent_name)
            if agent is None:
                continue

            # Run the agent
            report = self.guardian.run_agent(agent_name)

            # Evaluate
            evaluation = _evaluate_agent(
                agent_name=agent_name,
                report=report,
                agent_status=agent.status,
                cycle=self._cycle_count,
            )
            evaluations.append(evaluation)

        # System-wide score
        if evaluations:
            system_pct = round(
                sum(e.overall_pct for e in evaluations) / len(evaluations), 1
            )
        else:
            system_pct = 0.0

        cycle_result = EvaluationCycle(
            cycle=self._cycle_count,
            timestamp=now,
            evaluations=evaluations,
            system_overall_pct=system_pct,
            system_overall_rating=score_to_rating(system_pct),
        )
        self._history.append(cycle_result)
        self._persist_cycle(cycle_result)

        # Audit
        self.guardian.audit.record(
            agent="evaluator",
            action=f"eval_cycle_{self._cycle_count}",
            severity=Severity.INFO,
            details={
                "cycle": self._cycle_count,
                "system_pct": system_pct,
                "system_rating": cycle_result.system_overall_rating,
                "agents": {e.agent_name: e.overall_pct for e in evaluations},
            },
        )

        return cycle_result

    def _persist_cycle(self, cycle: EvaluationCycle) -> None:
        """Append evaluation to JSONL file for history tracking."""
        with open(self._eval_file, "a") as f:
            f.write(json.dumps(cycle.to_dict()) + "\n")

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    @staticmethod
    def print_cycle(cycle: EvaluationCycle) -> None:
        """Pretty-print a single evaluation cycle."""
        print()
        print("  ================================================================")
        print(f"  PERFORMANCE EVALUATION — Cycle {cycle.cycle}")
        print(f"  Timestamp: {cycle.timestamp}")
        print("  ================================================================")

        for ev in cycle.evaluations:
            print()
            print(f"  --- {ev.agent_name.upper()} ---")
            print(f"  {'Metric':<20} {'Score':>7} {'Rating':>7}  Detail")
            print(f"  {'─' * 20} {'─' * 7} {'─' * 7}  {'─' * 40}")
            for m in ev.metrics:
                bar = _bar(m.score_pct)
                print(f"  {m.name:<20} {m.score_pct:>5.1f}%  {m.rating}/5 {bar}  {m.detail}")
            print()
            print(f"  OVERALL: {ev.overall_pct}% — {ev.overall_rating}/5 ({ev.rating_label})")

        print()
        sys_label = RATING_SCALE[cycle.system_overall_rating]["label"]
        print(f"  SYSTEM SCORE: {cycle.system_overall_pct}% — {cycle.system_overall_rating}/5 ({sys_label})")
        print("  ================================================================")
        print()

    # ------------------------------------------------------------------
    # Daily loop (blocks until STOPSTOPSTOP)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the daily evaluation loop.

        Blocks the calling thread.  The loop repeats every ``cycle_seconds``
        seconds (default 24h).  It terminates when the owner types
        STOPSTOPSTOP at the prompt, or sends SIGINT (Ctrl+C).
        """
        original_sigint = signal.getsignal(signal.SIGINT)

        def _sigint_handler(signum, frame):
            print("\n  Caught Ctrl+C — stopping evaluator...")
            self._stop_event.set()

        signal.signal(signal.SIGINT, _sigint_handler)

        print()
        print("  ================================================================")
        print("  GUARDIAN ONE — PERFORMANCE EVALUATOR")
        print("  Agents under evaluation: Chronos, Archivist")
        print(f"  Cycle interval: {self._cycle_seconds}s ({self._cycle_seconds // 3600}h)")
        print("  ----------------------------------------------------------------")
        print(f"  Type {KILL_COMMAND} to stop the evaluation loop.")
        print("  Type 'eval' to trigger an immediate evaluation cycle.")
        print("  Type 'history' to view past evaluations.")
        print("  Type 'status' to see current agent status.")
        print("  ================================================================")
        print()

        self.guardian.audit.record(
            agent="evaluator",
            action="evaluator_started",
            severity=Severity.INFO,
        )

        # Run first cycle immediately
        cycle_result = self.run_cycle()
        self.print_cycle(cycle_result)

        # Start the timer thread for daily cycling
        timer_thread = threading.Thread(target=self._timer_loop, daemon=True)
        timer_thread.start()

        # Interactive command loop
        try:
            while not self._stop_event.is_set():
                try:
                    cmd = input("evaluator> ").strip()
                except EOFError:
                    break

                if cmd == KILL_COMMAND:
                    print()
                    print("  *** STOPSTOPSTOP received from root user ***")
                    print("  Terminating evaluation loop...")
                    self._stop_event.set()
                    break
                elif cmd.lower() == "eval":
                    print("  Triggering manual evaluation cycle...")
                    result = self.run_cycle()
                    self.print_cycle(result)
                elif cmd.lower() == "history":
                    self._print_history()
                elif cmd.lower() == "status":
                    self._print_agent_status()
                elif cmd.lower() in ("help", "?"):
                    self._print_help()
                elif cmd.lower() in ("stop", "quit", "q"):
                    print(f"  Use {KILL_COMMAND} to stop (root owner command).")
                elif cmd.strip():
                    print(f"  Unknown command: {cmd}")
                    print(f"  Type 'help' for commands or {KILL_COMMAND} to stop.")

        except KeyboardInterrupt:
            pass

        # Shutdown
        self._stop_event.set()
        timer_thread.join(timeout=5)

        self.guardian.audit.record(
            agent="evaluator",
            action="evaluator_stopped",
            severity=Severity.INFO,
            details={
                "total_cycles": self._cycle_count,
                "stopped_by": "owner",
            },
        )

        self._print_final_summary()
        signal.signal(signal.SIGINT, original_sigint)

    def _timer_loop(self) -> None:
        """Background thread that triggers eval cycles on interval."""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self._cycle_seconds)
            if not self._stop_event.is_set():
                print("\n  [Auto] Daily evaluation cycle starting...")
                result = self.run_cycle()
                self.print_cycle(result)
                print("evaluator> ", end="", flush=True)

    def _print_history(self) -> None:
        """Print summary of all past evaluation cycles."""
        if not self._history:
            print("  No evaluation history yet.")
            return
        print()
        print(f"  {'Cycle':>6} {'Timestamp':<28} {'System %':>9} {'Rating':>7}")
        print(f"  {'─' * 6} {'─' * 28} {'─' * 9} {'─' * 7}")
        for c in self._history:
            label = RATING_SCALE[c.system_overall_rating]["label"]
            print(f"  {c.cycle:>6} {c.timestamp:<28} {c.system_overall_pct:>7.1f}%  {c.system_overall_rating}/5 ({label})")
        print()

    def _print_agent_status(self) -> None:
        """Print current status of sandbox agents."""
        print()
        for name in self.SANDBOX_AGENTS:
            agent = self.guardian.get_agent(name)
            if agent:
                print(f"  {name}: {agent.status.value}")
            else:
                print(f"  {name}: NOT REGISTERED")
        print()

    def _print_help(self) -> None:
        print()
        print("  Performance Evaluator — Commands")
        print("  ─────────────────────────────────")
        print("  eval           Run an evaluation cycle now")
        print("  history        Show all past evaluation scores")
        print("  status         Show current agent status")
        print(f"  STOPSTOPSTOP   Stop the evaluator (root owner only)")
        print("  help           Show this message")
        print()

    def _print_final_summary(self) -> None:
        """Print a final summary when the evaluator stops."""
        print()
        print("  ================================================================")
        print("  EVALUATION COMPLETE")
        print(f"  Total cycles: {self._cycle_count}")
        if self._history:
            avg_pct = round(
                sum(c.system_overall_pct for c in self._history) / len(self._history), 1
            )
            avg_rating = score_to_rating(avg_pct)
            label = RATING_SCALE[avg_rating]["label"]
            print(f"  Average system score: {avg_pct}% — {avg_rating}/5 ({label})")

            # Per-agent averages
            for name in self.SANDBOX_AGENTS:
                agent_scores = []
                for c in self._history:
                    for e in c.evaluations:
                        if e.agent_name == name:
                            agent_scores.append(e.overall_pct)
                if agent_scores:
                    agent_avg = round(sum(agent_scores) / len(agent_scores), 1)
                    agent_rating = score_to_rating(agent_avg)
                    agent_label = RATING_SCALE[agent_rating]["label"]
                    print(f"  {name}: {agent_avg}% — {agent_rating}/5 ({agent_label})")

        print("  ================================================================")
        print("  Goodbye, Jeremy.")
        print()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _bar(pct: float, width: int = 10) -> str:
    """Simple ASCII progress bar."""
    filled = int(pct / 100 * width)
    return "[" + "#" * filled + "." * (width - filled) + "]"
