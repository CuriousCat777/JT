"""Chronos — Time Management Agent.

Responsibilities:
- Calendar integration (Google Calendar, Epic scheduling)
- Sleep pattern analysis and wake-up alerts
- Appointment reminders with configurable lead times
- Pre-charting workflow optimization
- Personal routine scheduling (skincare, home care)
- Travel itinerary tracking
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig


@dataclass
class CalendarEvent:
    """Represents a single calendar event."""
    title: str
    start: datetime
    end: datetime
    location: str = ""
    category: str = "general"  # work, personal, medical, travel, routine
    source: str = "manual"     # google, epic, manual
    reminders_minutes: list[int] = field(default_factory=lambda: [30, 10])
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SleepRecord:
    """Sleep tracking data point."""
    date: str
    bedtime: str
    waketime: str
    duration_hours: float
    quality_score: float = 0.0  # 0-1 scale from smartwatch data


@dataclass
class Routine:
    """A repeating personal routine (skincare, home care, etc.)."""
    name: str
    time_of_day: str  # "morning", "evening", "midday"
    duration_minutes: int
    days: list[str] = field(default_factory=lambda: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"])
    steps: list[str] = field(default_factory=list)


class Chronos(BaseAgent):
    """Time management agent for Jeremy's schedule optimization."""

    def __init__(self, config: AgentConfig, audit: AuditLog) -> None:
        super().__init__(config, audit)
        self._events: list[CalendarEvent] = []
        self._sleep_log: list[SleepRecord] = []
        self._routines: list[Routine] = []
        self._workflow_index: dict[str, list[str]] = {}

    def initialize(self) -> None:
        self._set_status(AgentStatus.IDLE)
        self._setup_default_routines()
        self.log("initialized", details={"routines": len(self._routines)})

    def _setup_default_routines(self) -> None:
        """Pre-configure Jeremy's known routines."""
        self._routines = [
            Routine(
                name="Morning Skincare",
                time_of_day="morning",
                duration_minutes=15,
                steps=["Cleanser", "Toner", "Serum", "Moisturizer", "Sunscreen"],
            ),
            Routine(
                name="Evening Skincare",
                time_of_day="evening",
                duration_minutes=20,
                steps=["Oil cleanser", "Water cleanser", "Exfoliant (alt days)", "Serum", "Night cream"],
            ),
            Routine(
                name="Home Care",
                time_of_day="evening",
                duration_minutes=30,
                days=["sat", "sun"],
                steps=["Tidy workspace", "Laundry check", "Meal prep review"],
            ),
        ]

    # ------------------------------------------------------------------
    # Calendar management
    # ------------------------------------------------------------------

    def add_event(self, event: CalendarEvent) -> None:
        self._events.append(event)
        self.log("event_added", details={"title": event.title, "start": event.start.isoformat()})

    def upcoming_events(self, hours: int = 24) -> list[CalendarEvent]:
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=hours)
        return sorted(
            [e for e in self._events if now <= e.start <= cutoff],
            key=lambda e: e.start,
        )

    def check_conflicts(self) -> list[tuple[CalendarEvent, CalendarEvent]]:
        """Detect all overlapping event pairs (not just adjacent)."""
        conflicts = []
        events = list(self._events)
        for i, a in enumerate(events):
            for b in events[i + 1:]:
                if a.start < b.end and b.start < a.end:
                    conflicts.append((a, b))
        return conflicts

    # ------------------------------------------------------------------
    # Sleep analysis
    # ------------------------------------------------------------------

    def record_sleep(self, record: SleepRecord) -> None:
        self._sleep_log.append(record)

    def sleep_analysis(self) -> dict[str, Any]:
        if not self._sleep_log:
            return {"status": "no_data"}
        recent = self._sleep_log[-7:]
        avg_duration = sum(r.duration_hours for r in recent) / len(recent)
        avg_quality = sum(r.quality_score for r in recent) / len(recent)
        return {
            "avg_duration_hours": round(avg_duration, 1),
            "avg_quality": round(avg_quality, 2),
            "recommendation": self._sleep_recommendation(avg_duration),
            "samples": len(recent),
        }

    @staticmethod
    def _sleep_recommendation(avg_hours: float) -> str:
        if avg_hours < 6:
            return "Sleep deficit detected. Consider earlier bedtime or reducing screen time before bed."
        elif avg_hours < 7:
            return "Slightly below optimal. Aim for 7-8 hours for peak performance."
        elif avg_hours <= 9:
            return "Sleep duration is in a healthy range."
        else:
            return "Excess sleep may indicate fatigue. Consider checking stress or activity levels."

    # ------------------------------------------------------------------
    # Workflow indexing
    # ------------------------------------------------------------------

    def index_workflow(self, name: str, steps: list[str]) -> None:
        """Store a repeatable workflow so it can be recalled quickly."""
        self._workflow_index[name] = steps
        self.log("workflow_indexed", details={"name": name, "steps": len(steps)})

    def get_workflow(self, name: str) -> list[str] | None:
        return self._workflow_index.get(name)

    def list_workflows(self) -> list[str]:
        return list(self._workflow_index.keys())

    # ------------------------------------------------------------------
    # Pre-charting optimisation
    # ------------------------------------------------------------------

    def prechart_checklist(self) -> list[str]:
        """Standard pre-charting steps for patient encounters (Epic-style)."""
        return [
            "Review patient's active problem list",
            "Check latest lab results and imaging",
            "Review current medications and allergies",
            "Note recent visit summaries and specialist notes",
            "Flag pending orders or referrals",
            "Prepare relevant templates or smart phrases",
        ]

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def run(self) -> AgentReport:
        self._set_status(AgentStatus.RUNNING)
        alerts: list[str] = []
        recommendations: list[str] = []
        actions: list[str] = []

        # Check upcoming events
        upcoming = self.upcoming_events(hours=12)
        if upcoming:
            actions.append(f"Found {len(upcoming)} events in next 12 hours.")

        # Check calendar conflicts
        conflicts = self.check_conflicts()
        if conflicts:
            for a, b in conflicts:
                alerts.append(f"Time conflict: '{a.title}' overlaps with '{b.title}'")

        # Sleep check
        sleep_info = self.sleep_analysis()
        if sleep_info.get("recommendation"):
            recommendations.append(sleep_info["recommendation"])

        self._set_status(AgentStatus.IDLE)
        return AgentReport(
            agent_name=self.name,
            status=AgentStatus.IDLE.value,
            summary=f"{len(upcoming)} upcoming events, {len(conflicts)} conflicts.",
            actions_taken=actions,
            recommendations=recommendations,
            alerts=alerts,
            data={"upcoming_count": len(upcoming), "sleep": sleep_info},
        )

    def report(self) -> AgentReport:
        return AgentReport(
            agent_name=self.name,
            status=self.status.value,
            summary=f"Tracking {len(self._events)} events, {len(self._routines)} routines, {len(self._workflow_index)} workflows.",
            data={
                "events": len(self._events),
                "routines": len(self._routines),
                "workflows": len(self._workflow_index),
                "sleep_records": len(self._sleep_log),
            },
        )
