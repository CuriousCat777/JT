"""Automated response actions — SOAR-lite containment engine.

SAFETY RULE: Destructive actions (host isolation, token revocation, process kill)
NEVER execute automatically without rule confirmation. The response engine
queues actions and requires explicit approval for anything beyond alerting.

Response hierarchy:
1. ALERT — always automatic (Slack, email, audit log)
2. CONTAIN — requires rule match + severity >= HIGH
3. DESTROY — requires human approval (never auto-execute)
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from guardian_one.varys.models import Alert, AlertSeverity, Incident, IncidentStatus

logger = logging.getLogger(__name__)


class ActionType(Enum):
    ALERT = "alert"
    BLOCK_IP = "block_ip"
    KILL_PROCESS = "kill_process"
    REVOKE_SESSIONS = "revoke_sessions"
    ISOLATE_HOST = "isolate_host"
    DISABLE_USER = "disable_user"


class ActionStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    EXECUTED = "executed"
    DENIED = "denied"
    FAILED = "failed"


@dataclass
class ResponseAction:
    """A proposed or executed response action."""
    action_type: ActionType
    target: str              # IP, PID, username, hostname
    reason: str
    alert_id: str = ""
    status: ActionStatus = ActionStatus.PENDING
    requires_approval: bool = True
    executed_at: str = ""
    result: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type.value,
            "target": self.target,
            "reason": self.reason,
            "alert_id": self.alert_id,
            "status": self.status.value,
            "requires_approval": self.requires_approval,
            "executed_at": self.executed_at,
            "result": self.result,
        }


class ResponseEngine:
    """Evaluate alerts and propose/execute response actions.

    By default, only ALERT actions execute automatically.
    Everything else is queued for approval.
    """

    # Actions that can auto-execute by severity.
    # Per safety rule: only ALERT auto-executes. All containment
    # actions (BLOCK_IP, KILL_PROCESS, etc.) require explicit approval.
    _AUTO_EXECUTE: dict[AlertSeverity, set[ActionType]] = {
        AlertSeverity.LOW: {ActionType.ALERT},
        AlertSeverity.MEDIUM: {ActionType.ALERT},
        AlertSeverity.HIGH: {ActionType.ALERT},
        AlertSeverity.CRITICAL: {ActionType.ALERT},
    }

    def __init__(self, dry_run: bool = True) -> None:
        self._dry_run = dry_run
        self._pending_actions: list[ResponseAction] = []
        self._executed_actions: list[ResponseAction] = []
        self._alert_callbacks: list[Callable[[Alert], None]] = []
        self._incidents: list[Incident] = []

    @property
    def pending_actions(self) -> list[ResponseAction]:
        return list(self._pending_actions)

    @property
    def executed_actions(self) -> list[ResponseAction]:
        return list(self._executed_actions)

    @property
    def incidents(self) -> list[Incident]:
        return list(self._incidents)

    def on_alert(self, callback: Callable[[Alert], None]) -> None:
        """Register an alert notification callback (Slack, email, etc.)."""
        self._alert_callbacks.append(callback)

    def respond(self, alert: Alert) -> list[ResponseAction]:
        """Evaluate an alert and propose response actions.

        Returns the list of actions proposed (some may auto-execute).
        """
        actions: list[ResponseAction] = []

        # Always create an alert action
        alert_action = ResponseAction(
            action_type=ActionType.ALERT,
            target=alert.source_ip or alert.source_user or alert.host_name or "system",
            reason=f"[{alert.severity.value.upper()}] {alert.title}",
            alert_id=alert.alert_id,
            requires_approval=False,
        )
        actions.append(alert_action)
        self._execute_action(alert_action, alert)

        # Severity-based escalation
        if alert.severity in (AlertSeverity.HIGH, AlertSeverity.CRITICAL):
            # Propose IP block for network-sourced attacks
            if alert.source_ip:
                actions.append(ResponseAction(
                    action_type=ActionType.BLOCK_IP,
                    target=alert.source_ip,
                    reason=f"Block source of: {alert.title}",
                    alert_id=alert.alert_id,
                    requires_approval=True,  # Containment always requires approval
                ))

        if alert.severity == AlertSeverity.CRITICAL:
            # Propose session revocation for compromised users
            if alert.source_user:
                actions.append(ResponseAction(
                    action_type=ActionType.REVOKE_SESSIONS,
                    target=alert.source_user,
                    reason=f"Revoke sessions due to: {alert.title}",
                    alert_id=alert.alert_id,
                    requires_approval=True,  # Always require approval
                ))

            # Create an incident
            incident = Incident(
                title=f"INCIDENT: {alert.title}",
                summary=alert.description,
                status=IncidentStatus.OPEN,
                severity=alert.severity,
                alerts=[alert],
                affected_hosts=[alert.host_name] if alert.host_name else [],
                affected_users=[alert.source_user] if alert.source_user else [],
            )
            self._incidents.append(incident)

        # Auto-execute eligible actions
        auto_set = self._AUTO_EXECUTE.get(alert.severity, {ActionType.ALERT})
        for action in actions:
            if action.status == ActionStatus.PENDING and not action.requires_approval:
                if action.action_type in auto_set:
                    self._execute_action(action, alert)

        self._pending_actions.extend(
            a for a in actions if a.status == ActionStatus.PENDING
        )

        return actions

    def approve_action(self, action: ResponseAction) -> bool:
        """Approve a pending action for execution."""
        if action.status != ActionStatus.PENDING:
            return False
        action.status = ActionStatus.APPROVED
        self._execute_action(action)
        if action in self._pending_actions:
            self._pending_actions.remove(action)
        return True

    def deny_action(self, action: ResponseAction) -> None:
        """Deny a pending action."""
        action.status = ActionStatus.DENIED
        if action in self._pending_actions:
            self._pending_actions.remove(action)

    def _execute_action(
        self, action: ResponseAction, alert: Alert | None = None
    ) -> None:
        """Execute a response action."""
        now = datetime.now(timezone.utc).isoformat()

        if action.action_type == ActionType.ALERT:
            # Fire alert callbacks
            if alert:
                for cb in self._alert_callbacks:
                    try:
                        cb(alert)
                    except Exception as exc:
                        logger.error("Alert callback failed: %s", exc)
            action.status = ActionStatus.EXECUTED
            action.executed_at = now
            action.result = "Alert dispatched"
            self._executed_actions.append(action)
            return

        if self._dry_run:
            action.status = ActionStatus.EXECUTED
            action.executed_at = now
            action.result = f"[DRY RUN] Would execute {action.action_type.value} on {action.target}"
            logger.info(action.result)
            self._executed_actions.append(action)
            return

        # Live execution
        try:
            if action.action_type == ActionType.BLOCK_IP:
                result = self._block_ip(action.target)
            elif action.action_type == ActionType.KILL_PROCESS:
                result = self._kill_process(action.target)
            else:
                result = f"Action type {action.action_type.value} not implemented for live execution"

            action.status = ActionStatus.EXECUTED
            action.executed_at = now
            action.result = result
        except Exception as exc:
            action.status = ActionStatus.FAILED
            action.result = str(exc)
            logger.error("Action execution failed: %s", exc)

        self._executed_actions.append(action)

    @staticmethod
    def _block_ip(ip: str) -> str:
        """Block an IP via iptables (requires root)."""
        try:
            subprocess.run(
                ["iptables", "-A", "INPUT", "-s", ip, "-j", "DROP"],
                check=True,
                capture_output=True,
                timeout=10,
            )
            return f"Blocked IP {ip} via iptables"
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"iptables block failed: {exc.stderr.decode()}") from exc

    @staticmethod
    def _kill_process(pid: str) -> str:
        """Kill a process by PID (requires appropriate permissions)."""
        try:
            subprocess.run(
                ["kill", "-9", pid],
                check=True,
                capture_output=True,
                timeout=5,
            )
            return f"Killed process {pid}"
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"Kill failed: {exc.stderr.decode()}") from exc

    def status(self) -> dict[str, Any]:
        return {
            "dry_run": self._dry_run,
            "pending_actions": len(self._pending_actions),
            "executed_actions": len(self._executed_actions),
            "open_incidents": sum(
                1 for i in self._incidents
                if i.status in (IncidentStatus.OPEN, IncidentStatus.INVESTIGATING)
            ),
            "total_incidents": len(self._incidents),
        }
