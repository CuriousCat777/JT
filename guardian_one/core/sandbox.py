"""Sandbox — deploy and validate agents in an isolated sandbox environment.

Provides a 10-step deployment checklist that boots Chronos and Archivist
(the first two layers) in sandbox mode, validates their health, and
hands off to the PerformanceEvaluator for daily grading.

Usage:
    python main.py --sandbox   # Deploy first 2 agents in sandbox + start eval loop
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, TYPE_CHECKING

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig

if TYPE_CHECKING:
    from guardian_one.core.guardian import GuardianOne


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DeployStep:
    """A single step in the sandbox deployment checklist."""
    number: int
    name: str
    description: str
    status: StepStatus = StepStatus.PENDING
    result: str = ""
    started_at: str | None = None
    completed_at: str | None = None


class SandboxDeployer:
    """10-step deployment checklist for sandbox agent validation.

    Steps:
      1. Verify system configuration
      2. Initialize audit logging in sandbox mode
      3. Boot Chronos agent (Layer 1 — Time Management)
      4. Validate Chronos initialization health
      5. Boot Archivist agent (Layer 2 — Data Management)
      6. Validate Archivist initialization health
      7. Run Chronos first cycle and capture report
      8. Run Archivist first cycle and capture report
      9. Cross-agent conflict check (Mediator)
     10. Sandbox deployment complete — hand off to evaluator
    """

    SANDBOX_AGENTS = ["chronos", "archivist"]

    def __init__(self, guardian: "GuardianOne") -> None:
        self.guardian = guardian
        self._steps: list[DeployStep] = self._build_checklist()
        self._reports: dict[str, AgentReport] = {}
        self._sandbox_active = False

    def _build_checklist(self) -> list[DeployStep]:
        return [
            DeployStep(
                number=1,
                name="verify_config",
                description="Verify system configuration and sandbox readiness",
            ),
            DeployStep(
                number=2,
                name="init_audit",
                description="Initialize audit logging in sandbox mode",
            ),
            DeployStep(
                number=3,
                name="boot_chronos",
                description="Boot Chronos agent (Layer 1 — Time Management)",
            ),
            DeployStep(
                number=4,
                name="validate_chronos",
                description="Validate Chronos initialization health",
            ),
            DeployStep(
                number=5,
                name="boot_archivist",
                description="Boot Archivist agent (Layer 2 — Data Management)",
            ),
            DeployStep(
                number=6,
                name="validate_archivist",
                description="Validate Archivist initialization health",
            ),
            DeployStep(
                number=7,
                name="run_chronos",
                description="Run Chronos first cycle and capture report",
            ),
            DeployStep(
                number=8,
                name="run_archivist",
                description="Run Archivist first cycle and capture report",
            ),
            DeployStep(
                number=9,
                name="conflict_check",
                description="Cross-agent conflict check (Mediator)",
            ),
            DeployStep(
                number=10,
                name="handoff",
                description="Sandbox deployment complete — hand off to evaluator",
            ),
        ]

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------

    def _mark_step(self, step: DeployStep, status: StepStatus, result: str) -> None:
        step.status = status
        step.result = result
        step.completed_at = datetime.now(timezone.utc).isoformat()
        symbol = "PASS" if status == StepStatus.PASSED else "FAIL"
        print(f"  [{step.number:>2}/10] [{symbol}] {step.description}")
        if result:
            print(f"         -> {result}")

    def _start_step(self, step: DeployStep) -> None:
        step.status = StepStatus.RUNNING
        step.started_at = datetime.now(timezone.utc).isoformat()

    def _step_1_verify_config(self, step: DeployStep) -> bool:
        """Verify system configuration is loaded and valid."""
        self._start_step(step)
        cfg = self.guardian.config
        if not cfg.owner:
            self._mark_step(step, StepStatus.FAILED, "No owner configured")
            return False
        agent_names = list(cfg.agents.keys()) if cfg.agents else []
        self._mark_step(
            step,
            StepStatus.PASSED,
            f"Owner: {cfg.owner} | Agents configured: {', '.join(agent_names) or 'defaults'}",
        )
        return True

    def _step_2_init_audit(self, step: DeployStep) -> bool:
        """Start audit logging in sandbox mode."""
        self._start_step(step)
        self.guardian.audit.record(
            agent="sandbox",
            action="sandbox_boot",
            severity=Severity.INFO,
            details={"mode": "sandbox", "target_agents": self.SANDBOX_AGENTS},
        )
        self._mark_step(step, StepStatus.PASSED, "Audit logging active (sandbox mode)")
        return True

    def _step_3_boot_chronos(self, step: DeployStep) -> bool:
        """Initialize the Chronos agent."""
        self._start_step(step)
        agent = self.guardian.get_agent("chronos")
        if agent is None:
            self._mark_step(step, StepStatus.FAILED, "Chronos agent not registered")
            return False
        self._mark_step(step, StepStatus.PASSED, f"Chronos booted (status: {agent.status.value})")
        return True

    def _step_4_validate_chronos(self, step: DeployStep) -> bool:
        """Validate Chronos is healthy."""
        self._start_step(step)
        agent = self.guardian.get_agent("chronos")
        if agent is None or agent.status == AgentStatus.ERROR:
            self._mark_step(step, StepStatus.FAILED, "Chronos health check failed")
            return False
        report = agent.report()
        self._mark_step(
            step,
            StepStatus.PASSED,
            f"Chronos healthy — {report.summary}",
        )
        return True

    def _step_5_boot_archivist(self, step: DeployStep) -> bool:
        """Initialize the Archivist agent."""
        self._start_step(step)
        agent = self.guardian.get_agent("archivist")
        if agent is None:
            self._mark_step(step, StepStatus.FAILED, "Archivist agent not registered")
            return False
        self._mark_step(step, StepStatus.PASSED, f"Archivist booted (status: {agent.status.value})")
        return True

    def _step_6_validate_archivist(self, step: DeployStep) -> bool:
        """Validate Archivist is healthy."""
        self._start_step(step)
        agent = self.guardian.get_agent("archivist")
        if agent is None or agent.status == AgentStatus.ERROR:
            self._mark_step(step, StepStatus.FAILED, "Archivist health check failed")
            return False
        report = agent.report()
        self._mark_step(
            step,
            StepStatus.PASSED,
            f"Archivist healthy — {report.summary}",
        )
        return True

    def _step_7_run_chronos(self, step: DeployStep) -> bool:
        """Execute Chronos first sandbox cycle."""
        self._start_step(step)
        try:
            report = self.guardian.run_agent("chronos")
            self._reports["chronos"] = report
            alerts = len(report.alerts) if report.alerts else 0
            self._mark_step(
                step,
                StepStatus.PASSED,
                f"Chronos cycle complete — {report.summary} ({alerts} alerts)",
            )
            return True
        except Exception as exc:
            self._mark_step(step, StepStatus.FAILED, f"Chronos run error: {exc}")
            return False

    def _step_8_run_archivist(self, step: DeployStep) -> bool:
        """Execute Archivist first sandbox cycle."""
        self._start_step(step)
        try:
            report = self.guardian.run_agent("archivist")
            self._reports["archivist"] = report
            alerts = len(report.alerts) if report.alerts else 0
            self._mark_step(
                step,
                StepStatus.PASSED,
                f"Archivist cycle complete — {report.summary} ({alerts} alerts)",
            )
            return True
        except Exception as exc:
            self._mark_step(step, StepStatus.FAILED, f"Archivist run error: {exc}")
            return False

    def _step_9_conflict_check(self, step: DeployStep) -> bool:
        """Check for cross-agent conflicts via the Mediator."""
        self._start_step(step)
        conflicts = self.guardian.mediator.check_conflicts()
        if conflicts:
            self._mark_step(
                step,
                StepStatus.PASSED,
                f"{len(conflicts)} conflict(s) detected — mediator engaged",
            )
        else:
            self._mark_step(step, StepStatus.PASSED, "No cross-agent conflicts")
        self.guardian.mediator.clear_pending()
        return True

    def _step_10_handoff(self, step: DeployStep) -> bool:
        """Finalize sandbox deployment."""
        self._start_step(step)
        self._sandbox_active = True
        self.guardian.audit.record(
            agent="sandbox",
            action="sandbox_deployment_complete",
            severity=Severity.INFO,
            details={
                "agents_deployed": self.SANDBOX_AGENTS,
                "reports": {k: v.status for k, v in self._reports.items()},
            },
        )
        self._mark_step(
            step,
            StepStatus.PASSED,
            "Sandbox active — handing off to Performance Evaluator",
        )
        return True

    # ------------------------------------------------------------------
    # Main deploy sequence
    # ------------------------------------------------------------------

    _STEP_MAP = {
        1: "_step_1_verify_config",
        2: "_step_2_init_audit",
        3: "_step_3_boot_chronos",
        4: "_step_4_validate_chronos",
        5: "_step_5_boot_archivist",
        6: "_step_6_validate_archivist",
        7: "_step_7_run_chronos",
        8: "_step_8_run_archivist",
        9: "_step_9_conflict_check",
        10: "_step_10_handoff",
    }

    def deploy(self) -> bool:
        """Execute the full 10-step deployment checklist.

        Returns True if all steps passed.
        """
        print()
        print("  ================================================================")
        print("  GUARDIAN ONE — SANDBOX DEPLOYMENT CHECKLIST")
        print("  Target Agents: Chronos (Layer 1) + Archivist (Layer 2)")
        print(f"  Started: {datetime.now(timezone.utc).isoformat()}")
        print("  ================================================================")
        print()

        all_passed = True
        for step in self._steps:
            method_name = self._STEP_MAP.get(step.number)
            if method_name is None:
                continue
            method = getattr(self, method_name)
            passed = method(step)
            if not passed:
                all_passed = False
                # Continue with remaining steps for full diagnostic
                self.guardian.audit.record(
                    agent="sandbox",
                    action=f"step_{step.number}_failed",
                    severity=Severity.ERROR,
                    details={"step": step.name, "result": step.result},
                    requires_review=True,
                )

        print()
        passed_count = sum(1 for s in self._steps if s.status == StepStatus.PASSED)
        failed_count = sum(1 for s in self._steps if s.status == StepStatus.FAILED)
        print(f"  Result: {passed_count}/10 PASSED, {failed_count}/10 FAILED")

        if all_passed:
            print("  Status: SANDBOX READY")
        else:
            print("  Status: DEPLOYMENT INCOMPLETE — review failures above")

        print("  ================================================================")
        print()
        return all_passed

    @property
    def is_active(self) -> bool:
        return self._sandbox_active

    @property
    def reports(self) -> dict[str, AgentReport]:
        return dict(self._reports)

    def checklist_summary(self) -> list[dict[str, Any]]:
        """Return the checklist as a serializable list."""
        return [
            {
                "step": s.number,
                "name": s.name,
                "description": s.description,
                "status": s.status.value,
                "result": s.result,
                "started_at": s.started_at,
                "completed_at": s.completed_at,
            }
            for s in self._steps
        ]
