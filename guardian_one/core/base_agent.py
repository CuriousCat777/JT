"""Base agent — abstract contract that every subordinate agent must implement.

This is the extensible foundation that supports the planned ~15 agents.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.config import AgentConfig


class AgentStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class AgentReport:
    """Structured report returned by an agent after a run cycle."""
    agent_name: str
    status: str
    summary: str
    actions_taken: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class BaseAgent(abc.ABC):
    """Abstract base class for all Guardian One subordinate agents.

    Lifecycle:
        1. __init__  — receive config + audit log handle
        2. initialize() — one-time setup (connect to APIs, load state)
        3. run() — periodic execution cycle
        4. report() — produce a structured report
        5. shutdown() — clean up resources

    Every agent MUST implement initialize(), run(), and report().
    """

    def __init__(self, config: AgentConfig, audit: AuditLog) -> None:
        self.config = config
        self.audit = audit
        self.status = AgentStatus.IDLE
        self._name = config.name

    @property
    def name(self) -> str:
        return self._name

    @abc.abstractmethod
    def initialize(self) -> None:
        """One-time setup: connect to services, load persisted state."""

    @abc.abstractmethod
    def run(self) -> AgentReport:
        """Execute the agent's primary duties and return a report."""

    @abc.abstractmethod
    def report(self) -> AgentReport:
        """Return a summary report of current state without side effects."""

    def shutdown(self) -> None:
        """Clean up resources.  Override if needed."""
        self.status = AgentStatus.IDLE
        self.audit.record(
            agent=self.name,
            action="shutdown",
            severity=Severity.INFO,
        )

    def log(
        self,
        action: str,
        severity: Severity = Severity.INFO,
        details: dict[str, Any] | None = None,
        requires_review: bool = False,
    ) -> None:
        """Convenience wrapper for audit logging."""
        self.audit.record(
            agent=self.name,
            action=action,
            severity=severity,
            details=details or {},
            requires_review=requires_review,
        )

    def _set_status(self, status: AgentStatus) -> None:
        self.status = status
        self.log(f"status_change:{status.value}")
