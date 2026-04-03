"""Tests for the AI Engine — Guardian One's sovereign brain.

These tests use mock backends so they run without Ollama or API keys.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from guardian_one.core.ai_engine import (
    AIConfig,
    AIEngine,
    AIMessage,
    AIProvider,
    AIResponse,
    AgentMemory,
    AnthropicBackend,
    OllamaBackend,
)
from guardian_one.core.audit import AuditLog
from guardian_one.core.base_agent import (
    AGENT_SYSTEM_PROMPTS,
    AgentReport,
    AgentStatus,
    BaseAgent,
    DEFAULT_SYSTEM_PROMPT,
)
from guardian_one.core.config import AgentConfig, GuardianConfig
from guardian_one.core.guardian import GuardianOne


# ---------------------------------------------------------------
# AIMessage / AIResponse
# ---------------------------------------------------------------

def test_ai_message():
    msg = AIMessage(role="user", content="Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"


def test_ai_response_success():
    resp = AIResponse(content="Answer", provider="ollama", model="llama3")
    assert resp.success is True
    assert resp.content == "Answer"


def test_ai_response_failure():
    resp = AIResponse(content="", provider="ollama", model="llama3")
    assert resp.success is False


# ---------------------------------------------------------------
# AgentMemory
# ---------------------------------------------------------------

def test_memory_basic():
    mem = AgentMemory(max_messages=5)
    mem.add(AIMessage(role="system", content="You are helpful."))
    mem.add(AIMessage(role="user", content="Hi"))
    mem.add(AIMessage(role="assistant", content="Hello!"))
    assert mem.size == 3
    msgs = mem.get_messages()
    assert msgs[0].role == "system"
    assert msgs[1].role == "user"


def test_memory_sliding_window():
    mem = AgentMemory(max_messages=4)
    mem.add(AIMessage(role="system", content="System prompt"))
    for i in range(6):
        mem.add(AIMessage(role="user", content=f"msg {i}"))
    # Should keep system + last 3 user messages
    msgs = mem.get_messages()
    assert msgs[0].role == "system"
    assert mem.size == 4


def test_memory_clear():
    mem = AgentMemory()
    mem.add(AIMessage(role="user", content="test"))
    mem.clear()
    assert mem.size == 0


# ---------------------------------------------------------------
# OllamaBackend
# ---------------------------------------------------------------

def test_ollama_not_available_when_offline():
    backend = OllamaBackend(
        base_url="http://localhost:99999",
        model="llama3",
        timeout=1,
    )
    assert backend.is_available() is False


def test_ollama_generate_returns_empty_on_error():
    pytest.importorskip("httpx", reason="httpx not installed")
    backend = OllamaBackend(
        base_url="http://localhost:99999",
        model="llama3",
        timeout=1,
    )
    resp = backend.generate([AIMessage(role="user", content="test")])
    assert resp.content == ""
    assert resp.provider == "ollama"


# ---------------------------------------------------------------
# AnthropicBackend
# ---------------------------------------------------------------

def test_anthropic_not_available_without_key():
    with patch.dict("os.environ", {}, clear=True):
        backend = AnthropicBackend()
        assert backend.is_available() is False


def test_anthropic_generate_returns_empty_without_key():
    with patch.dict("os.environ", {}, clear=True):
        backend = AnthropicBackend()
        resp = backend.generate([AIMessage(role="user", content="test")])
        assert resp.content == ""
        assert resp.provider == "anthropic"


# ---------------------------------------------------------------
# AIEngine
# ---------------------------------------------------------------

def test_engine_offline_response():
    """When no backend is available, engine returns a helpful offline message."""
    config = AIConfig(
        primary_provider=AIProvider.OLLAMA,
        fallback_provider=None,
    )
    engine = AIEngine(config)
    # Force ollama to be unavailable
    engine._ollama._available = False

    resp = engine.reason(agent_name="test", prompt="Hello")
    assert "OFFLINE" in resp.content
    assert resp.provider == "none"


def test_engine_status():
    engine = AIEngine()
    status = engine.status()
    assert "ollama" in status
    assert "anthropic" in status
    assert "total_requests" in status
    assert status["total_requests"] == 0


def test_engine_memory_isolation():
    """Each agent should have separate memory."""
    engine = AIEngine()
    mem_a = engine._get_memory("agent_a")
    mem_b = engine._get_memory("agent_b")
    mem_a.add(AIMessage(role="user", content="only for A"))
    assert mem_a.size == 1
    assert mem_b.size == 0


def test_engine_clear_memory():
    engine = AIEngine()
    engine._get_memory("agent_a").add(AIMessage(role="user", content="test"))
    engine.clear_memory("agent_a")
    assert engine._get_memory("agent_a").size == 0


def test_engine_clear_all_memory():
    engine = AIEngine()
    engine._get_memory("a").add(AIMessage(role="user", content="test"))
    engine._get_memory("b").add(AIMessage(role="user", content="test"))
    engine.clear_all_memory()
    assert len(engine._memories) == 0


def test_engine_with_mock_ollama():
    """Test full reasoning flow with a mocked Ollama backend."""
    engine = AIEngine()

    mock_response = AIResponse(
        content="Analysis complete: no anomalies found.",
        provider="ollama",
        model="llama3",
        tokens_used=42,
        latency_ms=150.0,
    )

    with patch.object(engine._ollama, "is_available", return_value=True), \
         patch.object(engine._ollama, "generate", return_value=mock_response):

        resp = engine.reason(
            agent_name="cfo",
            prompt="Analyze these transactions",
            context={"transactions": [{"amount": -50, "desc": "groceries"}]},
        )

        assert resp.success
        assert resp.content == "Analysis complete: no anomalies found."
        assert resp.provider == "ollama"
        assert engine._total_requests == 1
        assert engine._total_tokens == 42


def test_engine_stateless_reasoning():
    """Stateless reasoning should not persist memory."""
    engine = AIEngine()

    mock_response = AIResponse(
        content="Quick answer",
        provider="ollama",
        model="llama3",
    )

    with patch.object(engine._ollama, "is_available", return_value=True), \
         patch.object(engine._ollama, "generate", return_value=mock_response):

        resp = engine.reason_stateless(prompt="What is 2+2?")
        assert resp.content == "Quick answer"
        assert len(engine._memories) == 0


def test_engine_fallback():
    """If primary (Ollama) is down, should fall back to Anthropic."""
    config = AIConfig(
        primary_provider=AIProvider.OLLAMA,
        fallback_provider=AIProvider.ANTHROPIC,
    )
    engine = AIEngine(config)

    mock_response = AIResponse(
        content="Claude fallback response",
        provider="anthropic",
        model="claude-sonnet-4-20250514",
    )

    with patch.object(engine._ollama, "is_available", return_value=False), \
         patch.object(engine._anthropic, "is_available", return_value=True), \
         patch.object(engine._anthropic, "generate", return_value=mock_response):

        resp = engine.reason(agent_name="cfo", prompt="test")
        assert resp.provider == "anthropic"
        assert resp.content == "Claude fallback response"


# ---------------------------------------------------------------
# BaseAgent AI integration
# ---------------------------------------------------------------

class _DummyAgent(BaseAgent):
    def initialize(self):
        self._set_status(AgentStatus.IDLE)

    def run(self):
        return AgentReport(
            agent_name=self.name, status="idle", summary="test"
        )

    def report(self):
        return self.run()


def test_base_agent_ai_disabled_by_default():
    audit = AuditLog(log_dir=Path(tempfile.mkdtemp()))
    agent = _DummyAgent(AgentConfig(name="test"), audit)
    assert agent.ai_enabled is False


def test_base_agent_think_without_engine():
    audit = AuditLog(log_dir=Path(tempfile.mkdtemp()))
    agent = _DummyAgent(AgentConfig(name="test"), audit)
    resp = agent.think("What should I do?")
    assert "not available" in resp.content.lower()


def test_base_agent_think_with_engine():
    audit = AuditLog(log_dir=Path(tempfile.mkdtemp()))
    agent = _DummyAgent(AgentConfig(name="cfo"), audit)
    engine = AIEngine()

    mock_response = AIResponse(
        content="You should save more.",
        provider="ollama",
        model="llama3",
    )

    with patch.object(engine, "is_available", return_value=True), \
         patch.object(engine, "reason", return_value=mock_response):
        agent.set_ai_engine(engine)
        assert agent.ai_enabled is True

        resp = agent.think("Should I save more?")
        assert resp.content == "You should save more."


def test_base_agent_think_quick():
    audit = AuditLog(log_dir=Path(tempfile.mkdtemp()))
    agent = _DummyAgent(AgentConfig(name="chronos"), audit)
    engine = AIEngine()

    mock_response = AIResponse(
        content="Reschedule the 3pm meeting.",
        provider="ollama",
        model="llama3",
    )

    with patch.object(engine, "is_available", return_value=True), \
         patch.object(engine, "reason", return_value=mock_response):
        agent.set_ai_engine(engine)
        result = agent.think_quick("Any scheduling conflicts today?")
        assert result == "Reschedule the 3pm meeting."


def test_agent_system_prompts_defined():
    """Every known agent should have a system prompt."""
    expected = ["chronos", "cfo", "archivist", "gmail_agent", "web_architect", "doordash", "device_agent"]
    for name in expected:
        assert name in AGENT_SYSTEM_PROMPTS, f"Missing system prompt for {name}"


def test_default_system_prompt():
    assert "Guardian One" in DEFAULT_SYSTEM_PROMPT


# ---------------------------------------------------------------
# GuardianOne AI integration
# ---------------------------------------------------------------

def _make_config() -> GuardianConfig:
    return GuardianConfig(
        log_dir=tempfile.mkdtemp(),
        data_dir=tempfile.mkdtemp(),
        agents={
            "test": AgentConfig(name="test", allowed_resources=["stuff"]),
        },
    )


def test_guardian_has_ai_engine():
    guardian = GuardianOne(_make_config(), vault_passphrase="test-passphrase")
    assert guardian.ai_engine is not None
    status = guardian.ai_status()
    assert "ollama" in status
    assert "anthropic" in status


def test_guardian_injects_ai_into_agents():
    config = _make_config()
    guardian = GuardianOne(config, vault_passphrase="test-passphrase")

    agent = _DummyAgent(config.agents["test"], guardian.audit)
    guardian.register_agent(agent)

    # The agent should now have the AI engine injected
    assert agent._ai is guardian.ai_engine


def test_guardian_think():
    config = _make_config()
    guardian = GuardianOne(config, vault_passphrase="test-passphrase")

    mock_response = AIResponse(
        content="All agents healthy.",
        provider="ollama",
        model="llama3",
    )

    with patch.object(guardian.ai_engine, "reason", return_value=mock_response):
        result = guardian.think("How are all agents doing?")
        assert result == "All agents healthy."


def test_guardian_daily_summary_includes_ai():
    config = _make_config()
    guardian = GuardianOne(config, vault_passphrase="test-passphrase")
    summary = guardian.daily_summary()
    assert "AI Engine" in summary
    assert "Ollama" in summary or "ollama" in summary.lower()


def test_agent_report_has_ai_reasoning_field():
    report = AgentReport(
        agent_name="cfo",
        status="idle",
        summary="test",
        ai_reasoning="Budget looks good based on AI analysis.",
    )
    assert report.ai_reasoning == "Budget looks good based on AI analysis."
