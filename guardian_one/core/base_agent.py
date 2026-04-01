"""Base agent — abstract contract that every subordinate agent must implement.

This is the extensible foundation that supports the planned ~15 agents.
Now with AI reasoning capabilities via the AI Engine.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from guardian_one.core.audit import AuditLog, ChangeLogger, ChangeType, Severity
from guardian_one.core.config import AgentConfig

if TYPE_CHECKING:
    from guardian_one.core.ai_engine import AIEngine, AIResponse


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
    ai_reasoning: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# Default system prompts per agent role
AGENT_SYSTEM_PROMPTS: dict[str, str] = {
    "chronos": (
        "You are Chronos, the time management agent for Guardian One. "
        "You manage Jeremy's calendar, sleep patterns, routines, and scheduling. "
        "Analyze schedule conflicts, suggest optimizations, and ensure work-life balance. "
        "Be concise, actionable, and proactive about time management."
    ),
    "cfo": (
        "You are the CFO agent for Guardian One. "
        "You manage Jeremy's finances — accounts, budgets, bills, investments, and tax strategy. "
        "Flag anomalies in transactions, warn about overspending, and suggest savings opportunities. "
        "Always be precise with numbers and conservative with financial advice."
    ),
    "archivist": (
        "You are the Archivist agent for Guardian One. "
        "You manage Jeremy's data sovereignty — file organization, encryption, backups, and privacy. "
        "Ensure sensitive data is protected and properly classified. "
        "Be thorough about data hygiene and proactive about retention policies."
    ),
    "gmail_agent": (
        "You are the Gmail agent for Guardian One. "
        "You monitor Jeremy's inbox, categorize emails, flag important messages, and summarize threads. "
        "Prioritize actionable items and filter out noise. Be concise in summaries."
    ),
    "web_architect": (
        "You are the Web Architect agent for Guardian One. "
        "You manage Jeremy's websites (drjeremytabernero.org and jtmdai.com). "
        "Monitor security, uptime, deployments, and suggest improvements. "
        "Prioritize security posture and user experience."
    ),
    "doordash": (
        "You are the DoorDash agent for Guardian One. "
        "You coordinate meal deliveries, track spending against the food budget, "
        "and suggest cost-effective ordering. Coordinate with CFO for budget and Chronos for timing."
    ),
    "device_agent": (
        "You are the Device agent for Guardian One. "
        "You manage Jeremy's smart home devices, network security, and IoT ecosystem. "
        "Monitor for unauthorized devices, ensure firmware is updated, and maintain network isolation."
    ),
}

DEFAULT_SYSTEM_PROMPT = (
    "You are an autonomous agent in the Guardian One system, "
    "a personal life management platform for Jeremy Paulo Salvino Tabernero. "
    "Analyze the data provided, make actionable recommendations, and flag anything urgent. "
    "Be concise and direct."
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

    AI Integration:
        Call self.think() to get AI-powered reasoning about any data.
        The AI engine is injected by GuardianOne after registration.
    """

    def __init__(self, config: AgentConfig, audit: AuditLog) -> None:
        self.config = config
        self.audit = audit
        self.status = AgentStatus.IDLE
        self._name = config.name
        self._ai: AIEngine | None = None
        self._changelog: ChangeLogger | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def ai_enabled(self) -> bool:
        """Whether this agent has an active AI engine."""
        return self._ai is not None and self._ai.is_available()

    def set_ai_engine(self, engine: AIEngine) -> None:
        """Inject the AI engine (called by GuardianOne after registration)."""
        self._ai = engine

    def set_changelog(self, changelog: ChangeLogger) -> None:
        """Inject the change logger (called by GuardianOne after registration)."""
        self._changelog = changelog

    def think(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AIResponse:
        """Ask the AI to reason about something.

        This is the primary interface for agents to use AI.
        Falls back gracefully if no AI engine is available.

        Args:
            prompt: What to think about.
            context: Structured data to include.
            temperature: Override default (lower = more deterministic).
            max_tokens: Override default response length.

        Returns:
            AIResponse with the AI's reasoning.
        """
        if self._ai is None:
            from guardian_one.core.ai_engine import AIResponse
            return AIResponse(
                content="[AI not available — running in deterministic mode]",
                provider="none",
                model="none",
            )

        system = AGENT_SYSTEM_PROMPTS.get(self._name, DEFAULT_SYSTEM_PROMPT)

        response = self._ai.reason(
            agent_name=self._name,
            prompt=prompt,
            system=system,
            context=context,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Audit the AI interaction
        self.log(
            "ai_reasoning",
            details={
                "provider": response.provider,
                "model": response.model,
                "tokens": response.tokens_used,
                "latency_ms": response.latency_ms,
                "prompt_preview": prompt[:100],
            },
        )

        return response

    def think_quick(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Quick one-shot AI reasoning — returns just the text.

        Convenience wrapper around think() for simple queries.
        Returns empty string if AI is unavailable.
        """
        response = self.think(prompt, context=context)
        return response.content if response.success else ""

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
        if self._ai:
            self._ai.clear_memory(self._name)
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

    def log_change(
        self,
        change_type: ChangeType,
        title: str,
        description: str,
        files_affected: list[str] | None = None,
        breaking: bool = False,
        requires_review: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a documented change from this agent."""
        if self._changelog is None:
            return
        self._changelog.record(
            agent=self.name,
            change_type=change_type,
            title=title,
            description=description,
            files_affected=files_affected,
            breaking=breaking,
            requires_review=requires_review,
            metadata=metadata,
        )

    def _set_status(self, status: AgentStatus) -> None:
        self.status = status
        self.log(f"status_change:{status.value}")
