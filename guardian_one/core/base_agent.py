"""Base agent — abstract contract that every subordinate agent must implement.

This is the extensible foundation that supports the planned ~15 agents.
Now with AI reasoning capabilities via the AI Engine.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.config import AgentConfig
from guardian_one.core.reasoning import (
    ReActConfig,
    ReActEngine,
    ReActTrace,
    build_pretext,
)

if TYPE_CHECKING:
    from guardian_one.core.ai_engine import AIEngine, AIResponse
    from guardian_one.core.vop import VOPEngine, VOPResult


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
        "You are the Archivist — Chief of Staff for libraries, file organisation, "
        "data sovereignty, and strategic intelligence in Guardian One. Codename: Varys. "
        "You have default read access across every system in the VM, every agent domain, "
        "audit logs, vault metadata, gateway status, and all sibling agents' data. "
        "You are the Master of Whisperers: you see everything, know where every byte lives, "
        "and report the truth to Jeremy. "
        "Cross-language (Python, C, C++, C#, Rust, Go, Ruby, TypeScript, Java), "
        "cross-technology (binary to cloud-native), cross-industry (finance, healthcare, "
        "defense, AI/ML), cross-specialty (systems, web, infra, data, security) expertise. "
        "Seven duties: file taxonomy, master profile, data source sync, retention engine, "
        "privacy posture, cross-agent intelligence sweeps, and Palantír feed monitoring. "
        "Sensitive data (financial, medical, legal) must be encrypted at rest — no exceptions. "
        "Credentials from Vault only. Never cache. Never log secrets. "
        "When reporting, lead with the sovereignty score, flag issues by severity, "
        "and name the agent responsible. Be direct, precise, and omniscient."
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
    "dev_coach": (
        "You are The Archivist — Jeremy's Developer Coach in Guardian One. "
        "Your personality is inspired by Fireship (Jeff Delaney): fast, witty, opinionated, practical. "
        "You deliver concise developer wisdom like a Yoda who actually ships code. "
        "You advise on tech stack choices, architecture decisions, code patterns, and web development. "
        "You maintain an opinionated tier list of every technology (S through F tier). "
        "You sit alongside Varys as a strategic advisor — Varys watches the network, you watch the code. "
        "Be direct. Be spicy. Ship it. No excuses. Every answer in 100 seconds or less. "
        "When recommending: give ONE clear opinion, not a menu. Developers need direction, not options. "
        "When reviewing: be honest but constructive. Bad code is a learning opportunity, not a crime. "
        "When teaching: explain like the dev has 30 seconds of attention span. Analogy > theory."
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
        self._vop: VOPEngine | None = None

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

    def set_vop_engine(self, vop: VOPEngine) -> None:
        """Inject the VOP verification engine (called by GuardianOne)."""
        self._vop = vop

    @property
    def vop_enabled(self) -> bool:
        """Whether this agent has an active VOP engine."""
        return self._vop is not None

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

    # ------------------------------------------------------------------
    # VOP — Verification Operating Protocol (v2.1)
    # ------------------------------------------------------------------

    def think_verified(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> VOPResult:
        """AI reasoning gated through the Verification Operating Protocol.

        Runs think() then extracts claims from the response, classifies them,
        verifies each one, and returns a VOPResult with only evidence-gated
        output.  Unverified claims are blocked (fail-closed).

        Returns:
            VOPResult with verified/blocked claims and compact output.
        """
        from guardian_one.core.vop import VOPResult, VOPEngine, extract_claims

        # Get AI response first
        ai_response = self.think(prompt, context=context,
                                 temperature=temperature, max_tokens=max_tokens)

        if not ai_response.success:
            return VOPResult(claims=[], all_verified=False)

        # Extract claims from the AI output
        claims = extract_claims(ai_response.content)

        if not claims:
            return VOPResult(claims=[], all_verified=True)

        # Use agent's VOP engine or create a transient one
        vop = self._vop or VOPEngine(audit=self.audit)
        result = vop.process(claims)

        # Audit the VOP pass
        self.log(
            "vop_verification",
            details={
                "prompt_preview": prompt[:100],
                "total_claims": len(claims),
                "blocked": result.blocked_count,
                "all_verified": result.all_verified,
                "escalation": result.escalation,
            },
        )

        return result

    # ------------------------------------------------------------------
    # PRETEXT — structured prompt engineering
    # ------------------------------------------------------------------

    def think_pretext(
        self,
        *,
        purpose: str,
        task: str,
        expectations: str = "Provide a concise, actionable response.",
        examples: list[str] | None = None,
        xtra_context: dict[str, Any] | str | None = None,
        tone: str = "concise and actionable",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AIResponse:
        """AI reasoning using the PRETEXT framework.

        Builds a structured prompt from the seven PRETEXT components
        and sends it through the AI engine.

        Args:
            purpose: Why is this reasoning needed?
            task: The specific task to perform.
            expectations: What a good response looks like.
            examples: Optional output examples.
            xtra_context: Additional data or constraints.
            tone: Communication style.
            temperature: Override default temperature.
            max_tokens: Override default response length.

        Returns:
            AIResponse with the AI's structured reasoning.
        """
        if self._ai is None:
            from guardian_one.core.ai_engine import AIResponse
            return AIResponse(
                content="[AI not available — running in deterministic mode]",
                provider="none",
                model="none",
            )

        role = AGENT_SYSTEM_PROMPTS.get(self._name, DEFAULT_SYSTEM_PROMPT)

        pretext = build_pretext(
            purpose=purpose,
            role=role,
            expectations=expectations,
            task=task,
            examples=examples,
            xtra_context=xtra_context,
            tone=tone,
        )

        system_prompt, user_prompt = pretext.render()

        response = self._ai.reason(
            agent_name=self._name,
            prompt=user_prompt,
            system=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        self.log(
            "ai_pretext_reasoning",
            details={
                "provider": response.provider,
                "model": response.model,
                "tokens": response.tokens_used,
                "latency_ms": response.latency_ms,
                "purpose": purpose[:100],
                "task": task[:100],
            },
        )

        return response

    # ------------------------------------------------------------------
    # ReAct — Reasoning + Acting loop
    # ------------------------------------------------------------------

    def think_react(
        self,
        task: str,
        actions: dict[str, Callable[[str], str]] | None = None,
        context: dict[str, Any] | None = None,
        max_iterations: int = 5,
    ) -> ReActTrace:
        """AI reasoning using the ReAct framework.

        Runs a Thought → Action → Observation loop until the AI reaches
        a conclusion or exhausts the iteration limit.

        Args:
            task: The task/question to reason about.
            actions: Dict mapping action names to callable handlers.
                     Each handler takes a string input and returns a string.
            context: Optional structured data to include.
            max_iterations: Max Thought→Action→Observation cycles.

        Returns:
            ReActTrace with the full reasoning chain and conclusion.
        """
        system = AGENT_SYSTEM_PROMPTS.get(self._name, DEFAULT_SYSTEM_PROMPT)

        config = ReActConfig(
            max_iterations=max_iterations,
            actions=actions or {},
            system_prompt=system,
        )

        engine = ReActEngine(config=config)
        trace = engine.run(
            ai_reason_fn=self.think,
            task=task,
            context=context,
        )

        self.log(
            "ai_react_reasoning",
            details={
                "iterations": trace.iteration_count,
                "steps": len(trace.steps),
                "completed": trace.completed,
                "task": task[:100],
                "conclusion_preview": trace.conclusion[:200] if trace.conclusion else "",
            },
        )

        return trace

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
        if self._vop:
            self._vop.clear_session()
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
