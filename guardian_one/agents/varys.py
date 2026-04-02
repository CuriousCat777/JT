"""Varys — Intelligence Coordinator Agent for Guardian One.

The "little birds" intelligence network. Receives reports from Boris and other
agents, correlates them, and surfaces actionable intelligence to the Guardian.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import (
    AGENT_SYSTEM_PROMPTS,
    AgentConfig,
    AgentReport,
    AgentStatus,
    BaseAgent,
)

# ---------------------------------------------------------------------------
# System prompt registration
# ---------------------------------------------------------------------------

AGENT_SYSTEM_PROMPTS["varys"] = (
    "You are Varys, the intelligence coordinator for Guardian One. "
    "You receive reports from all subordinate agents (Boris, CFO, Chronos, etc.), "
    "correlate patterns, and surface actionable intelligence to the Guardian. "
    "Prioritize escalation-worthy items, identify cross-agent patterns, and "
    "produce concise daily briefs. Be precise, discreet, and proactive about threats."
)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

VALID_CATEGORIES = frozenset({"breach", "degradation", "repair", "anomaly", "health"})
VALID_SEVERITIES = frozenset({"low", "medium", "high", "critical"})
ESCALATION_SEVERITIES = frozenset({"high", "critical"})


@dataclass
class IntelReport:
    """A single piece of intelligence received from another agent."""

    source: str
    category: str
    severity: str
    title: str
    details: dict[str, Any]
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    acknowledged: bool = False


# ---------------------------------------------------------------------------
# Agent implementation
# ---------------------------------------------------------------------------


class Varys(BaseAgent):
    """Intelligence coordinator — correlates cross-agent reports and escalates."""

    def __init__(self, config: AgentConfig, audit: AuditLog) -> None:
        super().__init__(config, audit)
        self._ledger: list[IntelReport] = []
        self._max_ledger_size: int = 5000
        self._last_brief: str = ""
        self._last_correlation: dict[str, Any] = {}

    # -- lifecycle -----------------------------------------------------------

    def initialize(self) -> None:
        """One-time setup."""
        self._set_status(AgentStatus.IDLE)
        self.log("initialize", severity=Severity.INFO, details={"agent": "varys"})

    def run(self) -> AgentReport:
        """Correlate recent intel and produce a summary brief."""
        self._set_status(AgentStatus.RUNNING)

        try:
            correlation = self._correlate()
            self._last_correlation = correlation

            escalations = self._find_escalations()
            brief = self._build_brief(correlation, escalations)
            self._last_brief = brief

            actions: list[str] = []
            alerts: list[str] = []

            if escalations:
                actions.append(
                    f"Identified {len(escalations)} escalation-worthy item(s)"
                )
                for item in escalations:
                    alerts.append(
                        f"[{item.severity.upper()}] {item.source}: {item.title}"
                    )

            unacked = [r for r in self._ledger if not r.acknowledged]
            if unacked:
                actions.append(f"{len(unacked)} unacknowledged intel item(s) pending")

            self.log(
                "run_complete",
                severity=Severity.INFO,
                details={
                    "total_intel": len(self._ledger),
                    "escalations": len(escalations),
                    "unacknowledged": len(unacked),
                },
            )

            self._set_status(AgentStatus.IDLE)

            return AgentReport(
                agent_name=self.name,
                status="ok",
                summary=brief,
                actions_taken=actions,
                alerts=alerts,
                data={
                    "correlation": correlation,
                    "escalation_count": len(escalations),
                    "unacknowledged_count": len(unacked),
                    "total_intel": len(self._ledger),
                },
            )

        except Exception as exc:
            self._set_status(AgentStatus.ERROR)
            self.log(
                "run_error",
                severity=Severity.ERROR,
                details={"error": str(exc)},
            )
            return AgentReport(
                agent_name=self.name,
                status="error",
                summary=f"Intelligence run failed: {exc}",
                alerts=[f"Varys encountered an error: {exc}"],
            )

    def report(self) -> AgentReport:
        """Return structured report of current intelligence state (no side effects)."""
        by_category: dict[str, int] = defaultdict(int)
        by_severity: dict[str, int] = defaultdict(int)

        for item in self._ledger:
            by_category[item.category] += 1
            by_severity[item.severity] += 1

        unacked = [
            {
                "index": i,
                "source": r.source,
                "category": r.category,
                "severity": r.severity,
                "title": r.title,
                "timestamp": r.timestamp,
            }
            for i, r in enumerate(self._ledger)
            if not r.acknowledged
        ]

        escalations = [
            {
                "index": i,
                "source": r.source,
                "category": r.category,
                "severity": r.severity,
                "title": r.title,
                "timestamp": r.timestamp,
            }
            for i, r in enumerate(self._ledger)
            if r.severity in ESCALATION_SEVERITIES
        ]

        return AgentReport(
            agent_name=self.name,
            status=self.status.value,
            summary=(
                f"Intelligence ledger: {len(self._ledger)} items, "
                f"{len(unacked)} unacknowledged, {len(escalations)} escalation-worthy"
            ),
            data={
                "by_category": dict(by_category),
                "by_severity": dict(by_severity),
                "unacknowledged": unacked,
                "escalations": escalations,
                "total_intel": len(self._ledger),
            },
        )

    # -- public API ----------------------------------------------------------

    def receive_intel(
        self,
        source: str,
        category: str,
        severity: str,
        title: str,
        details: dict[str, Any] | None = None,
    ) -> int:
        """Accept incoming intelligence from another agent.

        Returns the index of the new intel item in the ledger.
        """
        category = category.lower()
        severity = severity.lower()

        if category not in VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category '{category}'. Must be one of: {sorted(VALID_CATEGORIES)}"
            )
        if severity not in VALID_SEVERITIES:
            raise ValueError(
                f"Invalid severity '{severity}'. Must be one of: {sorted(VALID_SEVERITIES)}"
            )

        report = IntelReport(
            source=source,
            category=category,
            severity=severity,
            title=title,
            details=details or {},
        )
        self._ledger.append(report)
        # Prune oldest acknowledged entries if ledger exceeds cap
        if len(self._ledger) > self._max_ledger_size:
            self._ledger = [
                r for r in self._ledger if not r.acknowledged
            ] + [
                r for r in self._ledger if r.acknowledged
            ][-self._max_ledger_size // 2:]
        index = len(self._ledger) - 1

        audit_severity = {
            "low": Severity.INFO,
            "medium": Severity.WARNING,
            "high": Severity.ERROR,
            "critical": Severity.CRITICAL,
        }.get(severity, Severity.INFO)

        self.log(
            "intel_received",
            severity=audit_severity,
            details={
                "source": source,
                "category": category,
                "severity": severity,
                "title": title,
                "index": index,
            },
            requires_review=severity in ESCALATION_SEVERITIES,
        )

        return index

    def acknowledge(self, index: int) -> None:
        """Mark an intel item as reviewed."""
        if index < 0 or index >= len(self._ledger):
            raise IndexError(
                f"Intel index {index} out of range (ledger has {len(self._ledger)} items)"
            )

        self._ledger[index].acknowledged = True
        item = self._ledger[index]
        self.log(
            "intel_acknowledged",
            severity=Severity.INFO,
            details={
                "index": index,
                "source": item.source,
                "title": item.title,
            },
        )

    def get_intel(
        self,
        category: str | None = None,
        severity: str | None = None,
        acknowledged: bool | None = None,
    ) -> list[IntelReport]:
        """Return filtered intel from the ledger."""
        results = self._ledger

        if category is not None:
            category = category.lower()
            results = [r for r in results if r.category == category]

        if severity is not None:
            severity = severity.lower()
            results = [r for r in results if r.severity == severity]

        if acknowledged is not None:
            results = [r for r in results if r.acknowledged == acknowledged]

        return results

    def daily_brief(self) -> str:
        """Return a human-readable daily intelligence brief."""
        correlation = self._correlate()
        escalations = self._find_escalations()
        return self._build_brief(correlation, escalations)

    # -- internal helpers ----------------------------------------------------

    def _correlate(self) -> dict[str, Any]:
        """Group intel by category and source, identify patterns."""
        by_category: dict[str, list[int]] = defaultdict(list)
        by_source: dict[str, list[int]] = defaultdict(list)
        by_severity: dict[str, int] = defaultdict(int)

        for i, item in enumerate(self._ledger):
            by_category[item.category].append(i)
            by_source[item.source].append(i)
            by_severity[item.severity] += 1

        # Detect patterns: categories with 3+ reports may indicate a trend
        patterns: list[str] = []
        for cat, indices in by_category.items():
            if len(indices) >= 3:
                patterns.append(
                    f"Recurring {cat} reports ({len(indices)} occurrences)"
                )

        # Detect source concentration
        for src, indices in by_source.items():
            critical_count = sum(
                1
                for i in indices
                if self._ledger[i].severity in ESCALATION_SEVERITIES
            )
            if critical_count >= 2:
                patterns.append(
                    f"Multiple high/critical items from {src} ({critical_count})"
                )

        return {
            "by_category": {k: len(v) for k, v in by_category.items()},
            "by_source": {k: len(v) for k, v in by_source.items()},
            "by_severity": dict(by_severity),
            "patterns": patterns,
        }

    def _find_escalations(self) -> list[IntelReport]:
        """Return all high/critical severity items that are unacknowledged."""
        return [
            item
            for item in self._ledger
            if item.severity in ESCALATION_SEVERITIES and not item.acknowledged
        ]

    def _build_brief(
        self,
        correlation: dict[str, Any],
        escalations: list[IntelReport],
    ) -> str:
        """Build a human-readable intelligence brief."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines: list[str] = []

        lines.append(f"=== VARYS INTELLIGENCE BRIEF ({now}) ===")
        lines.append("")

        total = len(self._ledger)
        unacked = sum(1 for r in self._ledger if not r.acknowledged)

        lines.append(f"Total intel items: {total}")
        lines.append(f"Unacknowledged: {unacked}")
        lines.append("")

        # Severity breakdown
        sev = correlation.get("by_severity", {})
        if sev:
            lines.append("-- Severity Breakdown --")
            for level in ("critical", "high", "medium", "low"):
                count = sev.get(level, 0)
                if count:
                    lines.append(f"  {level.upper()}: {count}")
            lines.append("")

        # Category breakdown
        cat = correlation.get("by_category", {})
        if cat:
            lines.append("-- Category Breakdown --")
            for category, count in sorted(cat.items(), key=lambda x: -x[1]):
                lines.append(f"  {category}: {count}")
            lines.append("")

        # Escalations
        if escalations:
            lines.append(f"-- Escalations ({len(escalations)}) --")
            for item in escalations:
                lines.append(
                    f"  [{item.severity.upper()}] ({item.source}) {item.title}"
                )
            lines.append("")

        # Patterns
        patterns = correlation.get("patterns", [])
        if patterns:
            lines.append("-- Detected Patterns --")
            for p in patterns:
                lines.append(f"  * {p}")
            lines.append("")

        if not total:
            lines.append("No intelligence on file. The realm is quiet.")
            lines.append("")

        lines.append("=== END BRIEF ===")
        return "\n".join(lines)
