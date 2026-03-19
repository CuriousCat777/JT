"""Tests for Ollama integration — sovereign LLM management.

All tests use mocks — no actual Ollama instance required.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from guardian_one.core.audit import AuditLog
from guardian_one.integrations.ollama_sync import (
    BenchmarkResult,
    OllamaHealth,
    OllamaModel,
    OllamaSync,
)


@pytest.fixture
def audit():
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


@pytest.fixture
def ollama(audit):
    return OllamaSync(audit=audit, base_url="http://localhost:11434")


# ---------------------------------------------------------------
# OllamaModel
# ---------------------------------------------------------------

def test_model_size_gb():
    model = OllamaModel(name="llama3", size_bytes=4_700_000_000)
    assert model.size_gb == 4.4


def test_model_size_zero():
    model = OllamaModel(name="tiny")
    assert model.size_gb == 0.0


# ---------------------------------------------------------------
# OllamaHealth
# ---------------------------------------------------------------

def test_health_healthy():
    health = OllamaHealth(
        reachable=True,
        models_count=3,
        models=[OllamaModel(name="llama3")],
    )
    assert health.healthy is True


def test_health_unhealthy_not_reachable():
    health = OllamaHealth(reachable=False, models_count=0)
    assert health.healthy is False


def test_health_unhealthy_no_models():
    health = OllamaHealth(reachable=True, models_count=0)
    assert health.healthy is False


# ---------------------------------------------------------------
# BenchmarkResult
# ---------------------------------------------------------------

def test_benchmark_result_defaults():
    result = BenchmarkResult(model="llama3", prompt="test")
    assert result.success is False
    assert result.tokens_per_second == 0.0


# ---------------------------------------------------------------
# OllamaSync — health check
# ---------------------------------------------------------------

def test_health_check_online(ollama):
    """Mock a healthy Ollama response."""
    mock_tags = MagicMock()
    mock_tags.status_code = 200
    mock_tags.json.return_value = {
        "models": [
            {
                "name": "llama3:latest",
                "size": 4_700_000_000,
                "modified_at": "2026-03-01T00:00:00Z",
                "digest": "365c0bd3c000abcdef",
                "details": {
                    "family": "llama",
                    "parameter_size": "8B",
                    "quantization_level": "Q4_0",
                },
            },
            {
                "name": "mistral:latest",
                "size": 4_400_000_000,
                "modified_at": "2026-03-01T00:00:00Z",
                "digest": "6577803aa9a0abcdef",
                "details": {
                    "family": "mistral",
                    "parameter_size": "7B",
                    "quantization_level": "Q4_0",
                },
            },
        ]
    }

    mock_version = MagicMock()
    mock_version.status_code = 200
    mock_version.json.return_value = {"version": "0.5.4"}

    with patch("guardian_one.integrations.ollama_sync.httpx") as mock_httpx:
        mock_httpx.get.side_effect = [mock_tags, mock_version]
        mock_httpx.ConnectError = ConnectionError
        mock_httpx.TimeoutException = TimeoutError

        health = ollama.health_check()

    assert health.reachable is True
    assert health.models_count == 2
    assert health.version == "0.5.4"
    assert health.models[0].name == "llama3:latest"
    assert health.models[0].family == "llama"
    assert health.total_size_gb > 0


def test_health_check_offline(ollama):
    """Ollama not running — should fail gracefully."""
    with patch("guardian_one.integrations.ollama_sync.httpx") as mock_httpx:
        mock_httpx.ConnectError = ConnectionError
        mock_httpx.TimeoutException = TimeoutError
        mock_httpx.get.side_effect = ConnectionError("refused")

        health = ollama.health_check()

    assert health.reachable is False
    assert "refused" in health.error.lower() or "Connection" in health.error


def test_health_check_timeout(ollama):
    """Ollama timeout — should fail gracefully."""
    with patch("guardian_one.integrations.ollama_sync.httpx") as mock_httpx:
        mock_httpx.ConnectError = ConnectionError
        mock_httpx.TimeoutException = TimeoutError
        mock_httpx.get.side_effect = TimeoutError("timed out")

        health = ollama.health_check()

    assert health.reachable is False
    assert "timeout" in health.error.lower() or "timed out" in health.error.lower()


# ---------------------------------------------------------------
# OllamaSync — is_running
# ---------------------------------------------------------------

def test_is_running_true(ollama):
    with patch("guardian_one.integrations.ollama_sync.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.get.return_value = mock_resp
        assert ollama.is_running() is True


def test_is_running_false(ollama):
    with patch("guardian_one.integrations.ollama_sync.httpx") as mock_httpx:
        mock_httpx.get.side_effect = ConnectionError("refused")
        assert ollama.is_running() is False


# ---------------------------------------------------------------
# OllamaSync — model management
# ---------------------------------------------------------------

def test_has_model(ollama):
    mock_tags = MagicMock()
    mock_tags.status_code = 200
    mock_tags.json.return_value = {
        "models": [{"name": "llama3:latest", "size": 4_700_000_000, "details": {}}]
    }
    mock_version = MagicMock()
    mock_version.status_code = 200
    mock_version.json.return_value = {"version": "0.5.4"}

    with patch("guardian_one.integrations.ollama_sync.httpx") as mock_httpx:
        mock_httpx.get.side_effect = [mock_tags, mock_version]
        mock_httpx.ConnectError = ConnectionError
        mock_httpx.TimeoutException = TimeoutError
        assert ollama.has_model("llama3") is True


def test_pull_model_success(ollama):
    with patch("guardian_one.integrations.ollama_sync.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.post.return_value = mock_resp

        result = ollama.pull_model("phi3:mini")

    assert result["success"] is True
    assert result["model"] == "phi3:mini"


def test_pull_model_failure(ollama):
    with patch("guardian_one.integrations.ollama_sync.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "model not found"
        mock_httpx.post.return_value = mock_resp

        result = ollama.pull_model("nonexistent:model")

    assert result["success"] is False
    assert "404" in result["error"]


def test_delete_model_success(ollama):
    with patch("guardian_one.integrations.ollama_sync.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.delete.return_value = mock_resp

        result = ollama.delete_model("old-model:latest")

    assert result["success"] is True


# ---------------------------------------------------------------
# OllamaSync — benchmark
# ---------------------------------------------------------------

def test_benchmark_success(ollama):
    with patch("guardian_one.integrations.ollama_sync.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "eval_count": 42,
            "load_duration": 500_000_000,   # 500ms in nanoseconds
            "eval_duration": 2_000_000_000,  # 2s in nanoseconds
        }
        mock_httpx.post.return_value = mock_resp

        result = ollama.benchmark("llama3")

    assert result.success is True
    assert result.tokens_generated == 42
    assert result.tokens_per_second == 21.0  # 42 tokens / 2s


def test_benchmark_offline(ollama):
    with patch("guardian_one.integrations.ollama_sync.httpx") as mock_httpx:
        mock_httpx.post.side_effect = ConnectionError("refused")

        result = ollama.benchmark("llama3")

    assert result.success is False
    assert result.error


# ---------------------------------------------------------------
# OllamaSync — output
# ---------------------------------------------------------------

def test_status_text_online(ollama):
    mock_tags = MagicMock()
    mock_tags.status_code = 200
    mock_tags.json.return_value = {
        "models": [{"name": "llama3:latest", "size": 4_700_000_000, "details": {"family": "llama", "quantization_level": "Q4_0"}}]
    }
    mock_version = MagicMock()
    mock_version.status_code = 200
    mock_version.json.return_value = {"version": "0.5.4"}

    with patch("guardian_one.integrations.ollama_sync.httpx") as mock_httpx:
        mock_httpx.get.side_effect = [mock_tags, mock_version]
        mock_httpx.ConnectError = ConnectionError
        mock_httpx.TimeoutException = TimeoutError

        text = ollama.status_text()

    assert "ONLINE" in text
    assert "llama3" in text
    assert "SOVEREIGN" in text


def test_status_text_offline(ollama):
    with patch("guardian_one.integrations.ollama_sync.httpx") as mock_httpx:
        mock_httpx.ConnectError = ConnectionError
        mock_httpx.TimeoutException = TimeoutError
        mock_httpx.get.side_effect = ConnectionError("refused")

        text = ollama.status_text()

    assert "OFFLINE" in text
    assert "ollama serve" in text


def test_dashboard_data(ollama):
    mock_tags = MagicMock()
    mock_tags.status_code = 200
    mock_tags.json.return_value = {
        "models": [{"name": "llama3:latest", "size": 4_700_000_000, "details": {}}]
    }
    mock_version = MagicMock()
    mock_version.status_code = 200
    mock_version.json.return_value = {"version": "0.5.4"}

    with patch("guardian_one.integrations.ollama_sync.httpx") as mock_httpx:
        mock_httpx.get.side_effect = [mock_tags, mock_version]
        mock_httpx.ConnectError = ConnectionError
        mock_httpx.TimeoutException = TimeoutError

        data = ollama.dashboard_data()

    assert data["status"] == "online"
    assert data["models_count"] == 1
    assert len(data["models"]) == 1
    assert data["models"][0]["name"] == "llama3:latest"


# ---------------------------------------------------------------
# OllamaSync — API key headers
# ---------------------------------------------------------------

def test_headers_with_api_key(audit):
    with patch.dict("os.environ", {"OLLAMA_API_KEY": "test-key-123"}):
        sync = OllamaSync(audit=audit)
        headers = sync._headers()
    assert headers["Authorization"] == "Bearer test-key-123"


def test_headers_without_api_key(audit):
    with patch.dict("os.environ", {}, clear=True):
        sync = OllamaSync(audit=audit)
        headers = sync._headers()
    assert "Authorization" not in headers


# ---------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------

def test_ollama_in_registry():
    from guardian_one.homelink.registry import IntegrationRegistry
    registry = IntegrationRegistry()
    registry.load_defaults()
    record = registry.get("ollama")
    assert record is not None
    assert record.owner_agent == "guardian_one"
    assert len(record.threat_model) == 5
    assert any("prompt injection" in t.risk.lower() for t in record.threat_model)
