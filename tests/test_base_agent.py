"""Tests for core/base_agent.py — agent lifecycle, AI integration, audit logging."""

from unittest.mock import MagicMock, patch

import pytest

from guardian_one.core.ai_engine import AIResponse
from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import (
    AGENT_SYSTEM_PROMPTS,
    DEFAULT_SYSTEM_PROMPT,
    AgentReport,
    AgentStatus,
    BaseAgent,
)
from guardian_one.core.config import AgentConfig


# --- Concrete stub for testing the abstract base ---

class StubAgent(BaseAgent):
    """Minimal concrete agent for testing BaseAgent behaviour."""

    def __init__(self, config, audit):
        super().__init__(config, audit)
        self._initialized = False
        self._ran = False

    def initialize(self):
        self._initialized = True
        self._set_status(AgentStatus.IDLE)

    def run(self) -> AgentReport:
        self._set_status(AgentStatus.RUNNING)
        self._ran = True
        self._set_status(AgentStatus.IDLE)
        return AgentReport(
            agent_name=self.name,
            status="ok",
            summary="stub run complete",
        )

    def report(self) -> AgentReport:
        return AgentReport(
            agent_name=self.name,
            status=self.status.value,
            summary="stub report",
        )


# --- Tests ---

class TestAgentLifecycle:

    def test_initial_state(self, audit_log, agent_config):
        agent = StubAgent(agent_config("test"), audit_log)
        assert agent.status == AgentStatus.IDLE
        assert agent.name == "test"
        assert agent.ai_enabled is False

    def test_initialize_sets_status(self, audit_log, agent_config):
        agent = StubAgent(agent_config("test"), audit_log)
        agent.initialize()
        assert agent._initialized is True
        assert agent.status == AgentStatus.IDLE

    def test_run_returns_report(self, audit_log, agent_config):
        agent = StubAgent(agent_config("chronos"), audit_log)
        agent.initialize()
        report = agent.run()
        assert report.agent_name == "chronos"
        assert report.status == "ok"
        assert agent._ran is True

    def test_report_without_side_effects(self, audit_log, agent_config):
        agent = StubAgent(agent_config("test"), audit_log)
        report = agent.report()
        assert report.summary == "stub report"
        assert agent._ran is False  # report() should not trigger run()

    def test_shutdown_resets_status_and_audits(self, audit_log, agent_config):
        agent = StubAgent(agent_config("test"), audit_log)
        agent.initialize()
        agent.run()
        agent.shutdown()
        assert agent.status == AgentStatus.IDLE
        entries = audit_log.query(agent="test")
        shutdown_entries = [e for e in entries if e.action == "shutdown"]
        assert len(shutdown_entries) == 1

    def test_full_lifecycle(self, audit_log, agent_config):
        agent = StubAgent(agent_config("chronos"), audit_log)
        agent.initialize()
        report = agent.run()
        assert report.status == "ok"
        final = agent.report()
        assert final.agent_name == "chronos"
        agent.shutdown()
        assert agent.status == AgentStatus.IDLE


class TestStatusTransitions:

    def test_set_status_updates_and_audits(self, audit_log, agent_config):
        agent = StubAgent(agent_config("test"), audit_log)
        agent._set_status(AgentStatus.RUNNING)
        assert agent.status == AgentStatus.RUNNING
        entries = audit_log.query(agent="test")
        assert any("status_change:running" in e.action for e in entries)

    @pytest.mark.parametrize("status", [
        AgentStatus.IDLE,
        AgentStatus.RUNNING,
        AgentStatus.ERROR,
        AgentStatus.DISABLED,
    ])
    def test_all_status_values(self, audit_log, agent_config, status):
        agent = StubAgent(agent_config("test"), audit_log)
        agent._set_status(status)
        assert agent.status == status


class TestAuditLogging:

    def test_log_delegates_to_audit(self, audit_log, agent_config):
        agent = StubAgent(agent_config("myagent"), audit_log)
        agent.log("test_action", severity=Severity.WARNING, details={"key": "val"})
        entries = audit_log.query(agent="myagent", severity=Severity.WARNING)
        assert len(entries) == 1
        assert entries[0].action == "test_action"
        assert entries[0].details == {"key": "val"}

    def test_log_requires_review(self, audit_log, agent_config):
        agent = StubAgent(agent_config("test"), audit_log)
        agent.log("important", requires_review=True)
        pending = audit_log.pending_reviews()
        assert len(pending) == 1
        assert pending[0].action == "important"

    def test_log_default_severity_is_info(self, audit_log, agent_config):
        agent = StubAgent(agent_config("test"), audit_log)
        agent.log("info_action")
        entries = audit_log.query(agent="test", severity=Severity.INFO)
        assert any(e.action == "info_action" for e in entries)


class TestAIIntegration:

    def test_think_without_engine_returns_fallback(self, audit_log, agent_config):
        agent = StubAgent(agent_config("test"), audit_log)
        response = agent.think("What should I do?")
        assert "not available" in response.content.lower()
        assert response.provider == "none"
        assert response.model == "none"

    def test_think_quick_without_engine_returns_fallback_message(self, audit_log, agent_config):
        """think_quick returns the fallback message when AI is unavailable."""
        agent = StubAgent(agent_config("test"), audit_log)
        result = agent.think_quick("anything")
        assert isinstance(result, str)
        assert "not available" in result.lower()

    def test_set_ai_engine(self, audit_log, agent_config):
        agent = StubAgent(agent_config("test"), audit_log)
        assert agent.ai_enabled is False
        mock_engine = MagicMock()
        mock_engine.is_available.return_value = True
        agent.set_ai_engine(mock_engine)
        assert agent.ai_enabled is True

    def test_think_with_engine_calls_reason(self, audit_log, agent_config):
        agent = StubAgent(agent_config("chronos"), audit_log)
        mock_engine = MagicMock()
        mock_engine.is_available.return_value = True
        mock_engine.reason.return_value = AIResponse(
            content="Schedule looks good",
            provider="ollama",
            model="llama3",
            tokens_used=50,
            latency_ms=120.0,
        )
        agent.set_ai_engine(mock_engine)

        response = agent.think("Analyze my schedule")
        assert response.content == "Schedule looks good"
        assert response.provider == "ollama"
        mock_engine.reason.assert_called_once()
        # Verify correct system prompt was used
        call_kwargs = mock_engine.reason.call_args
        assert call_kwargs.kwargs["system"] == AGENT_SYSTEM_PROMPTS["chronos"]

    def test_think_uses_default_prompt_for_unknown_agent(self, audit_log, agent_config):
        agent = StubAgent(agent_config("unknown_agent"), audit_log)
        mock_engine = MagicMock()
        mock_engine.is_available.return_value = True
        mock_engine.reason.return_value = AIResponse(
            content="ok", provider="test", model="test"
        )
        agent.set_ai_engine(mock_engine)
        agent.think("anything")
        call_kwargs = mock_engine.reason.call_args
        assert call_kwargs.kwargs["system"] == DEFAULT_SYSTEM_PROMPT

    def test_think_audits_ai_interaction(self, audit_log, agent_config):
        agent = StubAgent(agent_config("cfo"), audit_log)
        mock_engine = MagicMock()
        mock_engine.is_available.return_value = True
        mock_engine.reason.return_value = AIResponse(
            content="Budget analysis", provider="ollama", model="llama3",
            tokens_used=100, latency_ms=200.0,
        )
        agent.set_ai_engine(mock_engine)
        agent.think("Analyze budget")

        entries = audit_log.query(agent="cfo")
        ai_entries = [e for e in entries if e.action == "ai_reasoning"]
        assert len(ai_entries) == 1
        assert ai_entries[0].details["provider"] == "ollama"
        assert ai_entries[0].details["tokens"] == 100

    def test_shutdown_clears_ai_memory(self, audit_log, agent_config):
        agent = StubAgent(agent_config("test"), audit_log)
        mock_engine = MagicMock()
        mock_engine.is_available.return_value = True
        agent.set_ai_engine(mock_engine)
        agent.shutdown()
        mock_engine.clear_memory.assert_called_once_with("test")


class TestAgentReport:

    def test_report_defaults(self):
        r = AgentReport(agent_name="test", status="ok", summary="all good")
        assert r.actions_taken == []
        assert r.recommendations == []
        assert r.alerts == []
        assert r.data == {}
        assert r.ai_reasoning == ""
        assert r.timestamp  # non-empty

    def test_report_with_all_fields(self):
        r = AgentReport(
            agent_name="cfo",
            status="warning",
            summary="Budget alert",
            actions_taken=["checked bills"],
            recommendations=["reduce spending"],
            alerts=["overdue bill"],
            data={"net_worth": 50000},
            ai_reasoning="AI suggests cutting subscriptions",
        )
        assert r.agent_name == "cfo"
        assert len(r.alerts) == 1
        assert r.data["net_worth"] == 50000


class TestSystemPrompts:

    @pytest.mark.parametrize("agent_name", [
        "chronos", "cfo", "archivist", "gmail_agent",
        "web_architect", "doordash", "device_agent",
    ])
    def test_all_agents_have_system_prompts(self, agent_name):
        assert agent_name in AGENT_SYSTEM_PROMPTS
        assert len(AGENT_SYSTEM_PROMPTS[agent_name]) > 50

    def test_default_system_prompt_exists(self):
        assert "Guardian One" in DEFAULT_SYSTEM_PROMPT
