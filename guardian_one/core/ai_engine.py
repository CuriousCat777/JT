"""AI Engine — the brain behind Guardian One.

Provides a unified interface for LLM reasoning, supporting:
- Ollama (local, self-hosted, sovereign) — PRIMARY
- Anthropic Claude API (cloud fallback)

Every agent can call `ai.reason()` to get intelligent responses.
The engine handles provider selection, failover, and conversation memory.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AIProvider(Enum):
    """Supported AI backends."""
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"


@dataclass
class AIMessage:
    """A single message in a conversation."""
    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class AIResponse:
    """Response from the AI engine."""
    content: str
    provider: str
    model: str
    tokens_used: int = 0
    latency_ms: float = 0.0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def success(self) -> bool:
        return bool(self.content)


@dataclass
class AIConfig:
    """Configuration for the AI engine."""
    primary_provider: AIProvider = AIProvider.OLLAMA
    fallback_provider: AIProvider | None = AIProvider.ANTHROPIC
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    anthropic_model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 2048
    temperature: float = 0.3  # Low temp for reliable agent reasoning
    timeout_seconds: int = 60
    enable_memory: bool = True
    max_memory_messages: int = 50


class OllamaBackend:
    """Local Ollama LLM backend."""

    def __init__(self, base_url: str, model: str, timeout: int = 60) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._available: bool | None = None
        self._available_checked_at: float = 0.0
        self._availability_ttl: float = 30.0  # Cache availability for 30s
        self._api_key = os.environ.get("OLLAMA_API_KEY", "")

    @property
    def model(self) -> str:
        return self._model

    def _headers(self) -> dict[str, str]:
        """Build request headers with optional API key."""
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def is_available(self) -> bool:
        """Check if Ollama is running and the model is pulled (cached for 30s)."""
        import time as _time

        now = _time.monotonic()
        if self._available is not None and (now - self._available_checked_at) < self._availability_ttl:
            return self._available

        try:
            import httpx
            resp = httpx.get(
                f"{self._base_url}/api/tags",
                headers=self._headers(),
                timeout=5.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "").split(":")[0] for m in data.get("models", [])]
                self._available = self._model.split(":")[0] in models
                self._available_checked_at = now
                return self._available
        except Exception:
            pass
        self._available = False
        self._available_checked_at = now
        return False

    def generate(
        self,
        messages: list[AIMessage],
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> AIResponse:
        """Send messages to Ollama and get a response."""
        import time
        import httpx

        start = time.monotonic()

        # Convert to Ollama chat format
        ollama_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
        ]

        try:
            resp = httpx.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": ollama_messages,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature,
                    },
                },
                headers=self._headers(),
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            elapsed = (time.monotonic() - start) * 1000

            content = data.get("message", {}).get("content", "")
            tokens = data.get("eval_count", 0)

            return AIResponse(
                content=content,
                provider="ollama",
                model=self._model,
                tokens_used=tokens,
                latency_ms=round(elapsed, 1),
            )
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            logger.error("Ollama error: %s", exc)
            return AIResponse(
                content="",
                provider="ollama",
                model=self._model,
                latency_ms=round(elapsed, 1),
            )


class AnthropicBackend:
    """Claude API backend (cloud fallback) with tool-use for web research."""

    # Max rounds of tool calls per single generate() invocation
    _MAX_TOOL_ROUNDS = 5

    def __init__(self, model: str = "claude-sonnet-4-20250514", timeout: int = 60,
                 enable_tools: bool = True) -> None:
        self._model = model
        self._timeout = timeout
        self._api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self._client: Any = None  # Lazy-initialized, reused across calls
        self._enable_tools = enable_tools

    @property
    def model(self) -> str:
        return self._model

    def is_available(self) -> bool:
        """Check if the Anthropic API key is set."""
        return bool(self._api_key)

    def _get_tools(self) -> list[dict[str, Any]]:
        """Return tool definitions if tools are enabled."""
        if not self._enable_tools:
            return []
        from guardian_one.core.web_tools import TOOL_DEFINITIONS
        return TOOL_DEFINITIONS

    def generate(
        self,
        messages: list[AIMessage],
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> AIResponse:
        """Send messages to Claude API, automatically handling tool calls."""
        import time

        if not self._api_key:
            return AIResponse(
                content="",
                provider="anthropic",
                model=self._model,
            )

        start = time.monotonic()

        try:
            if self._client is None:
                import anthropic
                self._client = anthropic.Anthropic(
                    api_key=self._api_key,
                    timeout=self._timeout,
                )
            client = self._client

            # Separate system message from conversation
            system_text = ""
            conv_messages: list[dict[str, Any]] = []
            for m in messages:
                if m.role == "system":
                    system_text += m.content + "\n"
                else:
                    conv_messages.append({"role": m.role, "content": m.content})

            # Ensure conversation starts with user message
            if not conv_messages or conv_messages[0]["role"] != "user":
                conv_messages.insert(0, {"role": "user", "content": "Begin."})

            kwargs: dict[str, Any] = {
                "model": self._model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": conv_messages,
            }
            if system_text.strip():
                kwargs["system"] = system_text.strip()

            tools = self._get_tools()
            if tools:
                kwargs["tools"] = tools

            total_tokens = 0

            # Agentic loop: Claude may call tools, we execute and feed results back
            for _round in range(self._MAX_TOOL_ROUNDS):
                resp = client.messages.create(**kwargs)
                total_tokens += resp.usage.input_tokens + resp.usage.output_tokens

                # Check if Claude wants to use tools
                tool_use_blocks = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]

                if not tool_use_blocks or resp.stop_reason != "tool_use":
                    # No more tool calls — extract final text
                    break

                # Execute each tool call and build tool_result messages
                from guardian_one.core.web_tools import execute_tool

                # Add assistant's response (with tool_use blocks) to messages
                kwargs["messages"].append({
                    "role": "assistant",
                    "content": [
                        {"type": b.type, **({"text": b.text} if b.type == "text" else {"id": b.id, "name": b.name, "input": b.input})}
                        for b in resp.content
                    ],
                })

                tool_results = []
                for tb in tool_use_blocks:
                    logger.info("Tool call: %s(%s)", tb.name, tb.input)
                    result_text = execute_tool(tb.name, tb.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tb.id,
                        "content": result_text,
                    })

                kwargs["messages"].append({
                    "role": "user",
                    "content": tool_results,
                })

            elapsed = (time.monotonic() - start) * 1000

            # Extract final text from response
            content = ""
            for block in resp.content:
                if hasattr(block, "text"):
                    content += block.text

            return AIResponse(
                content=content,
                provider="anthropic",
                model=self._model,
                tokens_used=total_tokens,
                latency_ms=round(elapsed, 1),
            )
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            logger.error("Anthropic error: %s", exc)
            return AIResponse(
                content="",
                provider="anthropic",
                model=self._model,
                latency_ms=round(elapsed, 1),
            )


class AgentMemory:
    """Per-agent conversation memory with sliding window."""

    def __init__(self, max_messages: int = 50) -> None:
        self._max = max_messages
        self._messages: list[AIMessage] = []

    def add(self, message: AIMessage) -> None:
        self._messages.append(message)
        # Trim but always keep the system message(s)
        if len(self._messages) > self._max:
            system_msgs = [m for m in self._messages if m.role == "system"]
            other_msgs = [m for m in self._messages if m.role != "system"]
            keep = self._max - len(system_msgs)
            self._messages = system_msgs + other_msgs[-keep:]

    def get_messages(self) -> list[AIMessage]:
        return list(self._messages)

    def clear(self) -> None:
        self._messages.clear()

    @property
    def size(self) -> int:
        return len(self._messages)


class AIEngine:
    """The sovereign AI brain for Guardian One.

    Usage:
        engine = AIEngine(config)
        response = engine.reason(
            agent_name="cfo",
            prompt="Analyze these transactions for anomalies: ...",
            system="You are the CFO agent. You manage Jeremy's finances.",
        )
    """

    def __init__(self, config: AIConfig | None = None) -> None:
        self._config = config or AIConfig()
        self._ollama = OllamaBackend(
            base_url=self._config.ollama_base_url,
            model=self._config.ollama_model,
            timeout=self._config.timeout_seconds,
        )
        self._anthropic = AnthropicBackend(
            model=self._config.anthropic_model,
            timeout=self._config.timeout_seconds,
        )
        self._memories: dict[str, AgentMemory] = {}
        self._active_provider: AIProvider | None = None
        self._total_requests: int = 0
        self._total_tokens: int = 0

    def _get_memory(self, agent_name: str) -> AgentMemory:
        if agent_name not in self._memories:
            self._memories[agent_name] = AgentMemory(
                max_messages=self._config.max_memory_messages,
            )
        return self._memories[agent_name]

    def _select_backend(self) -> OllamaBackend | AnthropicBackend | None:
        """Select the best available backend (primary, then fallback)."""
        primary = self._config.primary_provider
        fallback = self._config.fallback_provider

        if primary == AIProvider.OLLAMA and self._ollama.is_available():
            self._active_provider = AIProvider.OLLAMA
            return self._ollama
        if primary == AIProvider.ANTHROPIC and self._anthropic.is_available():
            self._active_provider = AIProvider.ANTHROPIC
            return self._anthropic

        # Try fallback
        if fallback == AIProvider.OLLAMA and self._ollama.is_available():
            self._active_provider = AIProvider.OLLAMA
            return self._ollama
        if fallback == AIProvider.ANTHROPIC and self._anthropic.is_available():
            self._active_provider = AIProvider.ANTHROPIC
            return self._anthropic

        self._active_provider = None
        return None

    def is_available(self) -> bool:
        """Check if any AI backend is available."""
        return self._select_backend() is not None

    def reason(
        self,
        agent_name: str,
        prompt: str,
        system: str | None = None,
        context: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AIResponse:
        """Send a reasoning request to the AI.

        Args:
            agent_name: Which agent is asking (for memory isolation).
            prompt: The question or task for the AI.
            system: System prompt (agent role/personality). Set once per agent.
            context: Structured data to include in the prompt.
            temperature: Override default temperature.
            max_tokens: Override default max tokens.

        Returns:
            AIResponse with the AI's reasoning.
        """
        backend = self._select_backend()
        if backend is None:
            return AIResponse(
                content="[AI ENGINE OFFLINE] No AI backend available. "
                        "Install Ollama (ollama pull llama3) or set ANTHROPIC_API_KEY.",
                provider="none",
                model="none",
            )

        memory = self._get_memory(agent_name)

        # Set system prompt if provided and not already set
        if system and not any(m.role == "system" for m in memory.get_messages()):
            memory.add(AIMessage(role="system", content=system))

        # Build the user message with optional context
        user_content = prompt
        if context:
            context_str = json.dumps(context, indent=2, default=str)
            user_content = f"{prompt}\n\nContext data:\n```json\n{context_str}\n```"

        memory.add(AIMessage(role="user", content=user_content))

        # Call the backend
        response = backend.generate(
            messages=memory.get_messages(),
            max_tokens=max_tokens or self._config.max_tokens,
            temperature=temperature or self._config.temperature,
        )

        # Store the response in memory
        if response.success:
            memory.add(AIMessage(role="assistant", content=response.content))

        self._total_requests += 1
        self._total_tokens += response.tokens_used

        return response

    def reason_stateless(
        self,
        prompt: str,
        system: str | None = None,
        context: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AIResponse:
        """One-shot reasoning without memory (for quick queries)."""
        backend = self._select_backend()
        if backend is None:
            return AIResponse(
                content="[AI ENGINE OFFLINE] No AI backend available.",
                provider="none",
                model="none",
            )

        messages: list[AIMessage] = []
        if system:
            messages.append(AIMessage(role="system", content=system))

        user_content = prompt
        if context:
            context_str = json.dumps(context, indent=2, default=str)
            user_content = f"{prompt}\n\nContext data:\n```json\n{context_str}\n```"

        messages.append(AIMessage(role="user", content=user_content))

        response = backend.generate(
            messages=messages,
            max_tokens=max_tokens or self._config.max_tokens,
            temperature=temperature or self._config.temperature,
        )

        self._total_requests += 1
        self._total_tokens += response.tokens_used

        return response

    def clear_memory(self, agent_name: str) -> None:
        """Clear conversation memory for a specific agent."""
        if agent_name in self._memories:
            self._memories[agent_name].clear()

    def clear_all_memory(self) -> None:
        """Clear all agent memories."""
        self._memories.clear()

    def status(self) -> dict[str, Any]:
        """Get the current status of the AI engine."""
        ollama_available = self._ollama.is_available()
        anthropic_available = self._anthropic.is_available()

        return {
            "active_provider": self._active_provider.value if self._active_provider else None,
            "ollama": {
                "available": ollama_available,
                "base_url": self._config.ollama_base_url,
                "model": self._config.ollama_model,
            },
            "anthropic": {
                "available": anthropic_available,
                "model": self._config.anthropic_model,
                "has_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
            },
            "primary_provider": self._config.primary_provider.value,
            "fallback_provider": (
                self._config.fallback_provider.value
                if self._config.fallback_provider else None
            ),
            "total_requests": self._total_requests,
            "total_tokens": self._total_tokens,
            "agents_with_memory": list(self._memories.keys()),
            "memory_sizes": {
                name: mem.size for name, mem in self._memories.items()
            },
        }
