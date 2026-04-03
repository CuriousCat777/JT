"""Tests for the OpenAI-compatible chat completions bridge."""

import json
import tempfile
from unittest.mock import MagicMock, patch

from guardian_one.core.config import AgentConfig, GuardianConfig
from guardian_one.core.ai_engine import AIConfig, AIEngine, AIProvider, AIResponse


def _make_config():
    return GuardianConfig(
        log_dir=tempfile.mkdtemp(),
        data_dir=tempfile.mkdtemp(),
        agents={
            "chronos": AgentConfig(name="chronos"),
        },
    )


def _make_app():
    """Create a Flask test client with a mocked Guardian."""
    from guardian_one.web.app import create_app, _get_guardian
    import guardian_one.web.app as app_module

    config = _make_config()
    from guardian_one.core.guardian import GuardianOne
    guardian = GuardianOne(config, vault_passphrase="test")
    app_module._guardian = guardian
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client(), guardian


# ------------------------------------------------------------------
# /v1/models
# ------------------------------------------------------------------

def test_models_endpoint_returns_guardian_one():
    client, _ = _make_app()
    resp = client.get("/v1/models")
    data = json.loads(resp.data)
    assert data["object"] == "list"
    model_ids = [m["id"] for m in data["data"]]
    assert "guardian-one" in model_ids


def test_models_endpoint_lists_available_backends():
    client, guardian = _make_app()
    # Mock ollama as available via is_available
    with patch.object(guardian.ai_engine._ollama, "is_available", return_value=True):
        resp = client.get("/v1/models")
    data = json.loads(resp.data)
    model_ids = [m["id"] for m in data["data"]]
    # Model ID includes the configured model name
    assert any(m.startswith("ollama/") for m in model_ids)


# ------------------------------------------------------------------
# /v1/chat/completions — non-streaming
# ------------------------------------------------------------------

def test_chat_completions_empty_messages():
    client, _ = _make_app()
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "guardian-one", "messages": []},
    )
    assert resp.status_code == 400


def test_chat_completions_no_backend():
    client, guardian = _make_app()
    # Force all backends offline
    guardian.ai_engine._ollama._available = False

    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "guardian-one",
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )
    assert resp.status_code == 503


def test_chat_completions_success():
    client, guardian = _make_app()

    mock_response = AIResponse(
        content="Hello from Guardian One!",
        provider="ollama",
        model="llama3",
        tokens_used=42,
        latency_ms=100.0,
    )

    with patch.object(guardian.ai_engine, "_select_backend") as mock_select:
        mock_backend = MagicMock()
        mock_backend.is_available.return_value = True
        mock_backend.generate.return_value = mock_response
        mock_select.return_value = mock_backend

        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "guardian-one",
                "messages": [{"role": "user", "content": "Hi"}],
            },
        )

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"]["content"] == "Hello from Guardian One!"
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert data["choices"][0]["finish_reason"] == "stop"
    assert data["usage"]["completion_tokens"] == 42
    assert data["id"].startswith("chatcmpl-")


def test_chat_completions_with_system_message():
    client, guardian = _make_app()

    mock_response = AIResponse(
        content="I am a helpful assistant.",
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        tokens_used=10,
    )

    with patch.object(guardian.ai_engine, "_select_backend") as mock_select:
        mock_backend = MagicMock()
        mock_backend.is_available.return_value = True
        mock_backend.generate.return_value = mock_response
        mock_select.return_value = mock_backend

        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "guardian-one",
                "messages": [
                    {"role": "system", "content": "You are helpful."},
                    {"role": "user", "content": "Hello"},
                ],
            },
        )

    assert resp.status_code == 200
    # Verify system message was passed through
    call_args = mock_backend.generate.call_args
    # generate() is called as generate(messages=..., max_tokens=..., temperature=...)
    ai_messages = call_args.kwargs.get("messages", call_args.args[0] if call_args.args else [])
    assert ai_messages[0].role == "system"
    assert ai_messages[0].content == "You are helpful."


def test_chat_completions_specific_ollama_model():
    client, guardian = _make_app()

    mock_response = AIResponse(
        content="Ollama response",
        provider="ollama",
        model="llama3",
        tokens_used=5,
    )

    with patch.object(guardian.ai_engine._ollama, "is_available", return_value=True), \
         patch.object(guardian.ai_engine._ollama, "generate", return_value=mock_response):

        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "ollama/llama3",
                "messages": [{"role": "user", "content": "test"}],
            },
        )

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["choices"][0]["message"]["content"] == "Ollama response"


# ------------------------------------------------------------------
# /v1/chat/completions — streaming
# ------------------------------------------------------------------

def test_chat_completions_stream():
    client, guardian = _make_app()

    mock_response = AIResponse(
        content="Streamed content",
        provider="ollama",
        model="llama3",
        tokens_used=8,
    )

    with patch.object(guardian.ai_engine, "_select_backend") as mock_select:
        mock_backend = MagicMock()
        mock_backend.is_available.return_value = True
        mock_backend.generate.return_value = mock_response
        mock_select.return_value = mock_backend

        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "guardian-one",
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": True,
            },
        )

    assert resp.status_code == 200
    assert resp.content_type.startswith("text/event-stream")

    raw = resp.data.decode()
    assert "data: " in raw
    assert "Streamed content" in raw
    assert "[DONE]" in raw

    # Parse the first SSE chunk
    lines = [l for l in raw.split("\n") if l.startswith("data: ") and l != "data: [DONE]"]
    first_chunk = json.loads(lines[0].replace("data: ", ""))
    assert first_chunk["object"] == "chat.completion.chunk"
    assert first_chunk["choices"][0]["delta"]["content"] == "Streamed content"
