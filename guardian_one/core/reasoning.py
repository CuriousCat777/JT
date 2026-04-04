"""Reasoning frameworks for Guardian One agents.

Two structured reasoning strategies:

PRETEXT — Structured prompt engineering framework
    Purpose, Role, Expectations, Task, Examples, Xtra context, Tone
    Builds high-quality prompts that maximize AI reasoning quality.

ReAct — Reasoning + Acting loop (Yao et al., 2022)
    Thought → Action → Observation cycle for multi-step reasoning.
    Agents iterate through think/act/observe until they reach a conclusion.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PRETEXT Framework
# ---------------------------------------------------------------------------

@dataclass
class PretextPrompt:
    """A structured prompt built using the PRETEXT framework.

    P - Purpose:      Why is this reasoning needed?
    R - Role:         What persona should the AI adopt?
    E - Expectations: What does a good response look like?
    T - Task:         The specific task to perform.
    E - Examples:     Optional examples of desired output.
    X - Xtra context: Additional data, constraints, or background.
    T - Tone:         Communication style (concise, detailed, urgent, etc.)
    """

    purpose: str
    role: str
    expectations: str
    task: str
    examples: list[str] = field(default_factory=list)
    xtra_context: dict[str, Any] | str = field(default_factory=dict)
    tone: str = "concise and actionable"

    def build_system(self) -> str:
        """Build the system prompt from Role + Tone."""
        return f"{self.role}\n\nCommunication style: {self.tone}"

    def build_user(self) -> str:
        """Build the user prompt from Purpose + Expectations + Task + Examples + Xtra."""
        sections: list[str] = []

        sections.append(f"## Purpose\n{self.purpose}")
        sections.append(f"## Expectations\n{self.expectations}")
        sections.append(f"## Task\n{self.task}")

        if self.examples:
            examples_text = "\n".join(f"- {ex}" for ex in self.examples)
            sections.append(f"## Examples\n{examples_text}")

        if self.xtra_context:
            if isinstance(self.xtra_context, dict):
                ctx = json.dumps(self.xtra_context, indent=2, default=str)
                sections.append(f"## Additional Context\n```json\n{ctx}\n```")
            else:
                sections.append(f"## Additional Context\n{self.xtra_context}")

        return "\n\n".join(sections)

    def render(self) -> tuple[str, str]:
        """Return (system_prompt, user_prompt) tuple."""
        return self.build_system(), self.build_user()


def build_pretext(
    *,
    purpose: str,
    role: str,
    expectations: str,
    task: str,
    examples: list[str] | None = None,
    xtra_context: dict[str, Any] | str | None = None,
    tone: str = "concise and actionable",
) -> PretextPrompt:
    """Convenience builder for PRETEXT prompts."""
    return PretextPrompt(
        purpose=purpose,
        role=role,
        expectations=expectations,
        task=task,
        examples=examples or [],
        xtra_context=xtra_context or {},
        tone=tone,
    )


# ---------------------------------------------------------------------------
# ReAct Framework
# ---------------------------------------------------------------------------

class ReActStepType(Enum):
    """The three phases of a ReAct cycle."""
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"


@dataclass
class ReActStep:
    """A single step in the ReAct reasoning chain."""
    step_type: ReActStepType
    content: str
    step_number: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def format(self) -> str:
        label = self.step_type.value.capitalize()
        return f"[{label} {self.step_number}] {self.content}"


@dataclass
class ReActTrace:
    """Complete trace of a ReAct reasoning chain."""
    steps: list[ReActStep] = field(default_factory=list)
    conclusion: str = ""
    completed: bool = False
    _thought_count: int = field(default=0, repr=False)

    @property
    def iteration_count(self) -> int:
        """Number of Thought steps recorded."""
        return self._thought_count

    def add_thought(self, content: str) -> ReActStep:
        self._thought_count += 1
        step = ReActStep(
            step_type=ReActStepType.THOUGHT,
            content=content,
            step_number=self._thought_count,
        )
        self.steps.append(step)
        return step

    def add_action(self, content: str, metadata: dict[str, Any] | None = None) -> ReActStep:
        step = ReActStep(
            step_type=ReActStepType.ACTION,
            content=content,
            step_number=self._thought_count,
            metadata=metadata or {},
        )
        self.steps.append(step)
        return step

    def add_observation(self, content: str) -> ReActStep:
        step = ReActStep(
            step_type=ReActStepType.OBSERVATION,
            content=content,
            step_number=self._thought_count,
        )
        self.steps.append(step)
        return step

    def finish(self, conclusion: str) -> None:
        self.conclusion = conclusion
        self.completed = True

    def format_trace(self) -> str:
        """Render the full trace as readable text."""
        lines = ["=== ReAct Reasoning Trace ===", ""]
        for step in self.steps:
            lines.append(step.format())
        if self.conclusion:
            lines.append("")
            lines.append(f"[Conclusion] {self.conclusion}")
        return "\n".join(lines)

    def format_for_prompt(self) -> str:
        """Render the trace so far for inclusion in the next AI prompt."""
        lines: list[str] = []
        for step in self.steps:
            lines.append(step.format())
        return "\n".join(lines)


ActionHandler = Callable[[str], str]


@dataclass
class ReActConfig:
    """Configuration for a ReAct reasoning session."""
    max_iterations: int = 10
    actions: dict[str, ActionHandler] = field(default_factory=dict)
    system_prompt: str = ""
    stop_phrase: str = "FINISH"


REACT_SYSTEM_TEMPLATE = """{base_system}

You are operating in ReAct (Reasoning + Acting) mode. For each step:

1. **Thought**: Reason about the current state and what to do next.
2. **Action**: Choose an action to take. Available actions: {actions}
   Format: ACTION[action_name]: input
   When you have enough information, use ACTION[FINISH]: your final answer
3. **Observation**: You will receive the result of your action.

Repeat until you can provide a final answer using ACTION[FINISH].

Rules:
- Always start with a Thought.
- Each Thought must be followed by exactly one Action.
- Never skip the Thought step.
- Be concise in your reasoning.
"""

REACT_CONTINUATION_TEMPLATE = """Here is the reasoning trace so far:

{trace}

Continue reasoning. Provide your next Thought, then your Action.
"""


class ReActEngine:
    """Executes ReAct reasoning loops using the AI engine.

    Usage:
        engine = ReActEngine(config=ReActConfig(
            max_iterations=5,
            actions={"lookup": my_lookup_fn, "calculate": my_calc_fn},
            system_prompt="You are a financial analyst.",
        ))

        trace = engine.run(
            ai_reason_fn=agent.think,
            task="Analyze this month's spending for anomalies.",
            context={"transactions": [...]},
        )

        print(trace.conclusion)
    """

    def __init__(self, config: ReActConfig | None = None) -> None:
        self.config = config or ReActConfig()

    def _build_system(self) -> str:
        action_names = list(self.config.actions.keys()) + [self.config.stop_phrase]
        return REACT_SYSTEM_TEMPLATE.format(
            base_system=self.config.system_prompt,
            actions=", ".join(action_names),
        )

    def _parse_response(self, text: str) -> tuple[str, str | None, str | None]:
        """Parse AI response into (thought, action_name, action_input).

        Expected format:
            Thought: <reasoning>
            ACTION[<name>]: <input>
        """
        thought = ""
        action_name = None
        action_input = None

        lines = text.strip().split("\n")
        thought_lines: list[str] = []
        for line in lines:
            stripped = line.strip()

            # Check for ACTION[name]: input pattern
            if stripped.upper().startswith("ACTION["):
                bracket_end = stripped.find("]")
                if bracket_end == -1:
                    # Malformed action line — treat as thought text
                    thought_lines.append(stripped)
                    continue
                action_name = stripped[7:bracket_end].strip()
                action_input = stripped[bracket_end + 1:].lstrip(": ").strip()
                break
            else:
                # Remove "Thought:" prefix if present
                if stripped.lower().startswith("thought:"):
                    stripped = stripped[8:].strip()
                thought_lines.append(stripped)

        thought = " ".join(thought_lines).strip()
        return thought, action_name, action_input

    def _execute_action(self, action_name: str, action_input: str) -> str:
        """Execute a registered action and return the observation."""
        if action_name.casefold() == self.config.stop_phrase.casefold():
            return action_input

        # Case-insensitive action lookup
        actions_lower = {k.casefold(): v for k, v in self.config.actions.items()}
        handler = actions_lower.get(action_name.casefold())
        if handler is None:
            available = list(self.config.actions.keys()) + [self.config.stop_phrase]
            return f"[ERROR] Unknown action '{action_name}'. Available: {available}"

        try:
            return handler(action_input)
        except Exception as exc:
            logger.error("ReAct action '%s' failed: %s", action_name, exc)
            return f"[ERROR] Action '{action_name}' failed: {exc}"

    def run(
        self,
        ai_reason_fn: Callable[..., Any],
        task: str,
        context: dict[str, Any] | None = None,
    ) -> ReActTrace:
        """Execute a full ReAct reasoning loop.

        Args:
            ai_reason_fn: A callable that accepts (prompt, context, ...) and
                returns an object with a .content attribute (like AIResponse).
                Typically agent.think() or ai_engine.reason_stateless().
            task: The task/question to reason about.
            context: Optional structured data to include.

        Returns:
            ReActTrace with the full reasoning chain and conclusion.
        """
        trace = ReActTrace()
        system_instructions = self._build_system()

        # Prepend ReAct instructions so the AI knows the expected format
        initial_prompt = f"{system_instructions}\n\nTask: {task}"
        if context:
            ctx_str = json.dumps(context, indent=2, default=str)
            initial_prompt += f"\n\nContext:\n```json\n{ctx_str}\n```"
        initial_prompt += "\n\nBegin with your first Thought."

        current_prompt = initial_prompt

        for i in range(self.config.max_iterations):
            # Get AI response
            response = ai_reason_fn(
                prompt=current_prompt,
                context=None,  # Already embedded in prompt
            )

            content = response.content if hasattr(response, "content") else str(response)

            # Parse thought and action
            thought, action_name, action_input = self._parse_response(content)

            if thought:
                trace.add_thought(thought)

            if action_name is None:
                # No action found — treat entire response as thought, ask to continue
                current_prompt = REACT_CONTINUATION_TEMPLATE.format(
                    trace=trace.format_for_prompt()
                ) + "\nPlease provide an ACTION."
                continue

            # Check for FINISH
            if action_name.upper() == self.config.stop_phrase:
                trace.add_action(f"FINISH: {action_input}")
                trace.finish(action_input or thought)
                break

            # Execute action
            trace.add_action(f"{action_name}: {action_input}", metadata={
                "action": action_name,
                "input": action_input,
            })

            observation = self._execute_action(action_name, action_input or "")
            trace.add_observation(observation)

            # Build continuation prompt
            current_prompt = REACT_CONTINUATION_TEMPLATE.format(
                trace=trace.format_for_prompt()
            )

        # If we exhausted iterations without finishing
        if not trace.completed:
            last_thoughts = [
                s.content for s in trace.steps
                if s.step_type == ReActStepType.THOUGHT
            ]
            trace.finish(
                last_thoughts[-1] if last_thoughts
                else "[ReAct loop exhausted without conclusion]"
            )

        return trace
