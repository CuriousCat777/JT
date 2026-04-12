"""Mediator — resolves conflicts between subordinate agent proposals.

When Chronos wants to schedule a meeting but CFO flags a budget concern,
or Archivist recommends a backup window that overlaps a patient block,
the Mediator arbitrates.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from guardian_one.core.audit import AuditLog, Severity


class ConflictType(Enum):
    TIME_OVERLAP = "time_overlap"
    BUDGET_EXCEEDED = "budget_exceeded"
    DATA_ACCESS = "data_access"
    RESOURCE_CONTENTION = "resource_contention"


class Resolution(Enum):
    APPROVE_FIRST = "approve_first"
    APPROVE_SECOND = "approve_second"
    DEFER_TO_OWNER = "defer_to_owner"
    MERGE = "merge"
    REJECT_BOTH = "reject_both"


@dataclass
class Proposal:
    """A proposed action from an agent."""
    agent: str
    action: str
    resource: str
    time_start: str | None = None
    time_end: str | None = None
    cost: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConflictRecord:
    conflict_type: ConflictType
    proposals: list[Proposal]
    resolution: Resolution
    rationale: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class Mediator:
    """Cross-agent conflict resolution engine."""

    def __init__(self, audit: AuditLog, budget_limit: float = 0.0) -> None:
        self._audit = audit
        self._history: list[ConflictRecord] = []
        self._pending_proposals: list[Proposal] = []
        self._lock = threading.Lock()
        self._budget_limit = budget_limit

    def submit_proposal(self, proposal: Proposal) -> None:
        with self._lock:
            self._pending_proposals.append(proposal)
        self._audit.record(
            agent="mediator",
            action=f"proposal_received:{proposal.agent}:{proposal.action}",
            details={"resource": proposal.resource},
        )

    def check_conflicts(self) -> list[ConflictRecord]:
        """Scan pending proposals for conflicts and resolve them."""
        conflicts: list[ConflictRecord] = []
        with self._lock:
            proposals = list(self._pending_proposals)

        for i in range(len(proposals)):
            for j in range(i + 1, len(proposals)):
                a, b = proposals[i], proposals[j]

                # Time overlap check
                if a.time_start and b.time_start and a.time_end and b.time_end:
                    if a.time_start < b.time_end and b.time_start < a.time_end:
                        record = self._resolve_time_conflict(a, b)
                        conflicts.append(record)

                # Budget exceeded check
                if (
                    self._budget_limit > 0
                    and a.cost is not None
                    and b.cost is not None
                    and a.cost + b.cost > self._budget_limit
                ):
                    record = self._resolve_budget_conflict(a, b)
                    conflicts.append(record)

                # Same resource contention
                if a.resource == b.resource and a.agent != b.agent:
                    record = self._resolve_resource_conflict(a, b)
                    conflicts.append(record)

        with self._lock:
            self._history.extend(conflicts)
        return conflicts

    def _resolve_time_conflict(self, a: Proposal, b: Proposal) -> ConflictRecord:
        """Priority: Chronos (schedule) > CFO (payment) > Archivist (backup)."""
        priority = {"chronos": 3, "cfo": 2, "archivist": 1}
        pa = priority.get(a.agent.lower(), 0)
        pb = priority.get(b.agent.lower(), 0)

        if pa > pb:
            resolution = Resolution.APPROVE_FIRST
            rationale = f"{a.agent} has higher scheduling priority than {b.agent}."
        elif pb > pa:
            resolution = Resolution.APPROVE_SECOND
            rationale = f"{b.agent} has higher scheduling priority than {a.agent}."
        else:
            resolution = Resolution.DEFER_TO_OWNER
            rationale = "Equal priority — deferring to Jeremy for decision."

        record = ConflictRecord(
            conflict_type=ConflictType.TIME_OVERLAP,
            proposals=[a, b],
            resolution=resolution,
            rationale=rationale,
        )
        self._audit.record(
            agent="mediator",
            action="conflict_resolved:time_overlap",
            severity=Severity.WARNING,
            details={"rationale": rationale},
            requires_review=(resolution == Resolution.DEFER_TO_OWNER),
        )
        return record

    def _resolve_budget_conflict(self, a: Proposal, b: Proposal) -> ConflictRecord:
        """Approve the lower-cost proposal; defer to owner if costs are equal."""
        cost_a = a.cost if a.cost is not None else 0.0
        cost_b = b.cost if b.cost is not None else 0.0

        if cost_a < cost_b:
            resolution = Resolution.APPROVE_FIRST
            rationale = (
                f"{a.agent} (${cost_a:,.2f}) is cheaper than "
                f"{b.agent} (${cost_b:,.2f}). Combined ${cost_a + cost_b:,.2f} "
                f"exceeds budget ${self._budget_limit:,.2f}."
            )
        elif cost_b < cost_a:
            resolution = Resolution.APPROVE_SECOND
            rationale = (
                f"{b.agent} (${cost_b:,.2f}) is cheaper than "
                f"{a.agent} (${cost_a:,.2f}). Combined ${cost_a + cost_b:,.2f} "
                f"exceeds budget ${self._budget_limit:,.2f}."
            )
        else:
            resolution = Resolution.DEFER_TO_OWNER
            rationale = (
                f"Both proposals cost ${cost_a:,.2f}. Combined ${cost_a + cost_b:,.2f} "
                f"exceeds budget ${self._budget_limit:,.2f}. Deferring to Jeremy."
            )

        record = ConflictRecord(
            conflict_type=ConflictType.BUDGET_EXCEEDED,
            proposals=[a, b],
            resolution=resolution,
            rationale=rationale,
        )
        self._audit.record(
            agent="mediator",
            action="conflict_resolved:budget_exceeded",
            severity=Severity.WARNING,
            details={
                "rationale": rationale,
                "cost_a": cost_a,
                "cost_b": cost_b,
                "budget_limit": self._budget_limit,
            },
            requires_review=(resolution == Resolution.DEFER_TO_OWNER),
        )
        return record

    def _resolve_resource_conflict(self, a: Proposal, b: Proposal) -> ConflictRecord:
        record = ConflictRecord(
            conflict_type=ConflictType.RESOURCE_CONTENTION,
            proposals=[a, b],
            resolution=Resolution.DEFER_TO_OWNER,
            rationale=f"Both {a.agent} and {b.agent} want resource '{a.resource}'. Deferring to Jeremy.",
        )
        self._audit.record(
            agent="mediator",
            action="conflict_resolved:resource_contention",
            severity=Severity.WARNING,
            details={"resource": a.resource},
            requires_review=True,
        )
        return record

    def clear_pending(self) -> None:
        with self._lock:
            self._pending_proposals.clear()

    def conflict_history(self) -> list[ConflictRecord]:
        with self._lock:
            return list(self._history)
