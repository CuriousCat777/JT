"""Tests for PRETEXT and ReAct reasoning frameworks."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from guardian_one.core.ai_engine import AIConfig, AIEngine, AIProvider, AIResponse
from guardian_one.core.audit import AuditLog
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig
from guardian_one.core.reasoning import (
    PretextPrompt,
    ReActConfig,
    ReActEngine,
    ReActStepType,
    ReActTrace,
    build_pretext,
)


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

class FakeAgent(BaseAgent):
    """Concrete agent for testing."""

    def initialize(self) -> None:
        pass

    def run(self) -> AgentReport:
        return AgentReport(
            agent_name=self.name,
            status=AgentStatus.IDLE.value,
            summary="Test run",
        )

    def report(self) -> AgentReport:
        return self.run()


def _make_agent(name: str = "test_agent", tmp_dir: str | None = None) -> FakeAgent:
    log_dir = Path(tmp_dir) if tmp_dir else Path(tempfile.mkdtemp())
    audit = AuditLog(log_dir=log_dir)
    config = AgentConfig(name=name, enabled=True, allowed_resources=[])
    return FakeAgent(config=config, audit=audit)


def _make_mock_ai(response_text: str = "Mock response") -> MagicMock:
    """Create a mock AI engine that returns a fixed response."""
    engine = MagicMock(spec=AIEngine)
    engine.is_available.return_value = True
    engine.reason.return_value = AIResponse(
        content=response_text,
        provider="mock",
        model="mock-model",
        tokens_used=42,
        latency_ms=10.0,
    )
    return engine


# ---------------------------------------------------------------
# PRETEXT — PretextPrompt
# ---------------------------------------------------------------

class TestPretextPrompt:
    def test_basic_render(self):
        p = PretextPrompt(
            purpose="Detect overspending",
            role="You are a financial analyst.",
            expectations="Flag transactions over $500.",
            task="Review this month's transactions.",
            tone="concise and actionable",
        )
        system, user = p.render()
        assert "financial analyst" in system
        assert "concise and actionable" in system
        assert "## Purpose" in user
        assert "Detect overspending" in user
        assert "## Task" in user
        assert "Review this month" in user
        assert "## Expectations" in user

    def test_with_examples(self):
        p = PretextPrompt(
            purpose="Classify emails",
            role="You are an email classifier.",
            expectations="Return category and priority.",
            task="Classify the following email.",
            examples=["Input: 'Meeting tomorrow' → Category: Calendar, Priority: High"],
        )
        _, user = p.render()
        assert "## Examples" in user
        assert "Meeting tomorrow" in user

    def test_with_dict_context(self):
        p = PretextPrompt(
            purpose="Analyze data",
            role="Analyst",
            expectations="Summarize findings.",
            task="Analyze.",
            xtra_context={"total": 1500, "category": "food"},
        )
        _, user = p.render()
        assert "## Additional Context" in user
        assert '"total": 1500' in user

    def test_with_string_context(self):
        p = PretextPrompt(
            purpose="Analyze",
            role="Analyst",
            expectations="Summarize.",
            task="Analyze.",
            xtra_context="The user is in CST timezone.",
        )
        _, user = p.render()
        assert "CST timezone" in user

    def test_no_examples_no_context(self):
        p = PretextPrompt(
            purpose="P",
            role="R",
            expectations="E",
            task="T",
        )
        _, user = p.render()
        assert "## Examples" not in user
        assert "## Additional Context" not in user

    def test_build_pretext_convenience(self):
        p = build_pretext(
            purpose="Test",
            role="Tester",
            expectations="Pass",
            task="Run tests",
            tone="formal",
        )
        assert isinstance(p, PretextPrompt)
        assert p.purpose == "Test"
        assert p.tone == "formal"


# ---------------------------------------------------------------
# PRETEXT — BaseAgent integration
# ---------------------------------------------------------------

class TestAgentPretext:
    def test_think_pretext_with_ai(self):
        agent = _make_agent("cfo")
        mock_ai = _make_mock_ai("Budget analysis complete.")
        agent.set_ai_engine(mock_ai)

        response = agent.think_pretext(
            purpose="Monthly budget review",
            task="Analyze spending patterns",
            expectations="Identify top 3 spending categories",
            xtra_context={"month": "March", "total": 3200},
        )

        assert response.content == "Budget analysis complete."
        assert mock_ai.reason.called
        call_kwargs = mock_ai.reason.call_args
        # Check the prompt kwarg contains PRETEXT structure
        prompt = call_kwargs.kwargs.get("prompt", "")
        assert "## Purpose" in prompt

    def test_think_pretext_no_ai(self):
        agent = _make_agent("cfo")
        # No AI engine set

        response = agent.think_pretext(
            purpose="Test",
            task="Test task",
        )

        assert "deterministic mode" in response.content

    def test_think_pretext_custom_tone(self):
        agent = _make_agent("chronos")
        mock_ai = _make_mock_ai("Schedule optimized.")
        agent.set_ai_engine(mock_ai)

        agent.think_pretext(
            purpose="Optimize schedule",
            task="Find conflicts",
            tone="urgent and direct",
        )

        call_args = mock_ai.reason.call_args
        system = call_args.kwargs.get("system", call_args[1].get("system", ""))
        assert "urgent and direct" in system


# ---------------------------------------------------------------
# ReAct — ReActTrace
# ---------------------------------------------------------------

class TestReActTrace:
    def test_empty_trace(self):
        trace = ReActTrace()
        assert trace.iteration_count == 0
        assert trace.completed is False
        assert "=== ReAct Reasoning Trace ===" in trace.format_trace()

    def test_add_steps(self):
        trace = ReActTrace()
        trace.add_thought("I need to check the balance")
        trace.add_action("lookup: checking_account")
        trace.add_observation("Balance: $1,500")
        trace.add_thought("Balance looks normal")
        trace.add_action("FINISH: Balance is healthy at $1,500")
        trace.finish("Balance is healthy at $1,500")

        assert trace.iteration_count == 2
        assert trace.completed is True
        assert len(trace.steps) == 5
        assert trace.conclusion == "Balance is healthy at $1,500"

    def test_format_trace(self):
        trace = ReActTrace()
        trace.add_thought("Checking data")
        trace.add_action("lookup: accounts")
        trace.add_observation("Found 3 accounts")
        trace.finish("All accounts active")

        output = trace.format_trace()
        assert "[Thought 1]" in output
        assert "[Action 1]" in output
        assert "[Observation 1]" in output
        assert "[Conclusion]" in output

    def test_format_for_prompt(self):
        trace = ReActTrace()
        trace.add_thought("Step 1")
        trace.add_action("check: something")

        prompt_text = trace.format_for_prompt()
        assert "[Thought 1]" in prompt_text
        assert "[Action 1]" in prompt_text


# ---------------------------------------------------------------
# ReAct — ReActEngine
# ---------------------------------------------------------------

class TestReActEngine:
    def test_immediate_finish(self):
        """AI immediately provides a FINISH action."""

        def fake_think(prompt, context=None):
            return AIResponse(
                content="Thought: The answer is clear.\nACTION[FINISH]: 42",
                provider="mock",
                model="mock",
            )

        engine = ReActEngine(ReActConfig(
            max_iterations=5,
            system_prompt="Test agent",
        ))

        trace = engine.run(ai_reason_fn=fake_think, task="What is 6*7?")

        assert trace.completed is True
        assert "42" in trace.conclusion

    def test_multi_step_reasoning(self):
        """AI does a lookup action before finishing."""
        call_count = 0

        def fake_think(prompt, context=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return AIResponse(
                    content="Thought: I need to look up the account balance.\nACTION[lookup]: checking",
                    provider="mock",
                    model="mock",
                )
            else:
                return AIResponse(
                    content="Thought: Got the balance, it's healthy.\nACTION[FINISH]: Balance is $1,500, looks good.",
                    provider="mock",
                    model="mock",
                )

        def lookup_handler(input_str: str) -> str:
            return f"Account '{input_str}' balance: $1,500"

        engine = ReActEngine(ReActConfig(
            max_iterations=5,
            actions={"lookup": lookup_handler},
            system_prompt="Financial agent",
        ))

        trace = engine.run(ai_reason_fn=fake_think, task="Check account health")

        assert trace.completed is True
        assert trace.iteration_count >= 1
        assert any(s.step_type == ReActStepType.OBSERVATION for s in trace.steps)
        assert "$1,500" in trace.format_trace()

    def test_unknown_action(self):
        """AI tries an action that doesn't exist."""
        call_count = 0

        def fake_think(prompt, context=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return AIResponse(
                    content="Thought: Try something.\nACTION[nonexistent]: test",
                    provider="mock",
                    model="mock",
                )
            else:
                return AIResponse(
                    content="Thought: That didn't work.\nACTION[FINISH]: Giving up.",
                    provider="mock",
                    model="mock",
                )

        engine = ReActEngine(ReActConfig(max_iterations=5))
        trace = engine.run(ai_reason_fn=fake_think, task="Test")

        observations = [s for s in trace.steps if s.step_type == ReActStepType.OBSERVATION]
        assert any("ERROR" in o.content for o in observations)

    def test_max_iterations_exhausted(self):
        """AI never finishes — should still return a trace."""

        def fake_think(prompt, context=None):
            return AIResponse(
                content="Thought: Still thinking...\nACTION[lookup]: data",
                provider="mock",
                model="mock",
            )

        def dummy_handler(s: str) -> str:
            return "some data"

        engine = ReActEngine(ReActConfig(
            max_iterations=3,
            actions={"lookup": dummy_handler},
        ))

        trace = engine.run(ai_reason_fn=fake_think, task="Infinite loop test")

        assert trace.completed is True  # Forced completion
        assert trace.iteration_count <= 3

    def test_action_handler_exception(self):
        """Action handler raises an exception — should be caught."""

        call_count = 0

        def fake_think(prompt, context=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return AIResponse(
                    content="Thought: Try broken action.\nACTION[broken]: test",
                    provider="mock",
                    model="mock",
                )
            return AIResponse(
                content="Thought: Error handled.\nACTION[FINISH]: Recovered from error.",
                provider="mock",
                model="mock",
            )

        def broken_handler(s: str) -> str:
            raise ValueError("Something went wrong")

        engine = ReActEngine(ReActConfig(
            max_iterations=5,
            actions={"broken": broken_handler},
        ))

        trace = engine.run(ai_reason_fn=fake_think, task="Test error handling")
        assert trace.completed is True
        observations = [s for s in trace.steps if s.step_type == ReActStepType.OBSERVATION]
        assert any("ERROR" in o.content for o in observations)


# ---------------------------------------------------------------
# ReAct — BaseAgent integration
# ---------------------------------------------------------------

class TestAgentReAct:
    def test_think_react_basic(self):
        agent = _make_agent("cfo")
        call_count = 0

        def mock_reason(agent_name, prompt, system=None, context=None,
                        temperature=None, max_tokens=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return AIResponse(
                    content="Thought: Checking budget.\nACTION[FINISH]: Budget is on track.",
                    provider="mock",
                    model="mock",
                )
            return AIResponse(
                content="Thought: Done.\nACTION[FINISH]: Complete.",
                provider="mock",
                model="mock",
            )

        mock_ai = MagicMock(spec=AIEngine)
        mock_ai.is_available.return_value = True
        mock_ai.reason.side_effect = mock_reason
        agent.set_ai_engine(mock_ai)

        trace = agent.think_react(
            task="Review monthly budget",
            max_iterations=3,
        )

        assert isinstance(trace, ReActTrace)
        assert trace.completed is True
        assert "Budget" in trace.conclusion or "budget" in trace.conclusion.lower()

    def test_think_react_with_actions(self):
        agent = _make_agent("cfo")
        call_count = 0

        def mock_reason(agent_name, prompt, system=None, context=None,
                        temperature=None, max_tokens=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return AIResponse(
                    content="Thought: Need to check balance.\nACTION[check_balance]: savings",
                    provider="mock",
                    model="mock",
                )
            return AIResponse(
                content="Thought: Balance is good.\nACTION[FINISH]: Savings at $5,000.",
                provider="mock",
                model="mock",
            )

        mock_ai = MagicMock(spec=AIEngine)
        mock_ai.is_available.return_value = True
        mock_ai.reason.side_effect = mock_reason
        agent.set_ai_engine(mock_ai)

        trace = agent.think_react(
            task="Check account health",
            actions={"check_balance": lambda acc: f"{acc}: $5,000"},
            max_iterations=5,
        )

        assert trace.completed is True
        assert any(s.step_type == ReActStepType.OBSERVATION for s in trace.steps)
