"""Tests for the Guardian One health check HTTP server."""

import json
import time
import urllib.request
from collections import deque
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from guardian_one.core.health import HealthServer


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _mock_guardian():
    """Build a minimal mock GuardianOne with the attributes the health
    endpoints rely on."""
    guardian = MagicMock()

    # Agents
    agent_a = MagicMock()
    agent_a.name = "chronos"
    agent_a.status.value = "idle"
    agent_a.config.enabled = True
    agent_a.ai_enabled = False

    agent_b = MagicMock()
    agent_b.name = "cfo"
    agent_b.status.value = "idle"
    agent_b.config.enabled = True
    agent_b.ai_enabled = True

    agent_map = {"chronos": agent_a, "cfo": agent_b}
    guardian.list_agents.return_value = list(agent_map.keys())
    guardian.get_agent.side_effect = lambda n: agent_map.get(n)

    # CFO report with net_worth
    cfo_report = MagicMock()
    cfo_report.data = {"net_worth": 42000.0}
    agent_b.report.return_value = cfo_report

    # Audit
    guardian.audit.pending_reviews.return_value = [MagicMock(), MagicMock()]
    guardian.audit._total_recorded = 55
    # Provide a deque with one sync entry
    sync_entry = MagicMock()
    sync_entry.action = "financial_sync"
    sync_entry.timestamp = "2026-04-01T12:00:00+00:00"
    guardian.audit._entries = deque([sync_entry])

    # Vault
    guardian.vault.health_report.return_value = {
        "total_credentials": 3,
        "due_for_rotation": 1,
    }

    # Gateway
    guardian.gateway.list_services.return_value = ["notion"]
    guardian.gateway.service_status.return_value = {"circuit_state": "closed"}

    # AI engine
    guardian.ai_engine.status.return_value = {
        "active_provider": "ollama",
        "ollama": {"available": True, "model": "llama3"},
        "anthropic": {"available": False},
        "total_requests": 10,
    }

    return guardian


def _get_json(port: int, path: str) -> tuple[int, dict]:
    """HTTP GET to localhost and return (status_code, parsed_json)."""
    url = f"http://127.0.0.1:{port}{path}"
    try:
        resp = urllib.request.urlopen(url, timeout=5)
        body = json.loads(resp.read().decode())
        return resp.status, body
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read().decode())
        return exc.code, body


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

# Use a unique port per test run to avoid collisions.  We use a class-level
# counter so parallel tests don't stomp on each other.
_PORT_COUNTER = 15200


def _next_port() -> int:
    global _PORT_COUNTER
    _PORT_COUNTER += 1
    return _PORT_COUNTER


@pytest.fixture()
def health_server():
    """Yield a running HealthServer backed by a mock Guardian."""
    guardian = _mock_guardian()
    port = _next_port()
    server = HealthServer(guardian, port=port)
    server.start()
    # Give the server thread a moment to bind
    time.sleep(0.15)
    yield server, port, guardian
    server.stop()


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


class TestHealthEndpoint:
    def test_returns_200_healthy(self, health_server):
        server, port, _ = health_server
        status, body = _get_json(port, "/health")
        assert status == 200
        assert body["status"] == "healthy"
        assert "uptime_seconds" in body
        assert body["agents_registered"] == 2
        assert "timestamp" in body

    def test_returns_503_when_agent_in_error(self, health_server):
        server, port, guardian = health_server
        # Put one agent in error state
        guardian.get_agent("chronos").status.value = "error"
        status, body = _get_json(port, "/health")
        assert status == 503
        assert body["status"] == "degraded"


class TestStatusEndpoint:
    def test_includes_agent_data(self, health_server):
        _, port, _ = health_server
        status, body = _get_json(port, "/status")
        assert status == 200
        assert "agents" in body
        agent_names = [a["name"] for a in body["agents"]]
        assert "chronos" in agent_names
        assert "cfo" in agent_names

    def test_includes_vault_data(self, health_server):
        _, port, _ = health_server
        _, body = _get_json(port, "/status")
        assert body["vault"]["total_credentials"] == 3
        assert body["vault"]["due_for_rotation"] == 1

    def test_includes_gateway_services(self, health_server):
        _, port, _ = health_server
        _, body = _get_json(port, "/status")
        assert len(body["gateway_services"]) == 1
        assert body["gateway_services"][0]["name"] == "notion"

    def test_includes_ai_engine(self, health_server):
        _, port, _ = health_server
        _, body = _get_json(port, "/status")
        assert body["ai_engine"]["active_provider"] == "ollama"
        assert body["ai_engine"]["ollama_available"] is True
        assert body["ai_engine"]["total_requests"] == 10


class TestMetricsEndpoint:
    def test_includes_key_numbers(self, health_server):
        _, port, _ = health_server
        status, body = _get_json(port, "/metrics")
        assert status == 200
        assert body["agents_healthy"] == 2
        assert body["agents_total"] == 2
        assert body["alert_count"] == 2
        assert body["audit_entry_count"] == 55
        assert body["net_worth"] == 42000.0
        assert body["last_sync_time"] == "2026-04-01T12:00:00+00:00"

    def test_net_worth_none_when_no_cfo(self, health_server):
        _, port, guardian = health_server
        # Remove CFO from the agent map
        guardian.get_agent.side_effect = lambda n: None if n == "cfo" else MagicMock()
        guardian.list_agents.return_value = ["chronos"]
        _, body = _get_json(port, "/metrics")
        assert body["net_worth"] is None


class TestServerLifecycle:
    def test_start_and_stop(self):
        guardian = _mock_guardian()
        port = _next_port()
        server = HealthServer(guardian, port=port)

        assert not server.is_running
        server.start()
        time.sleep(0.15)
        assert server.is_running
        assert server.port == port

        server.stop()
        time.sleep(0.15)
        assert not server.is_running

    def test_double_start_is_safe(self):
        guardian = _mock_guardian()
        port = _next_port()
        server = HealthServer(guardian, port=port)
        server.start()
        time.sleep(0.1)
        server.start()  # should not raise
        assert server.is_running
        server.stop()

    def test_stop_without_start_is_safe(self):
        guardian = _mock_guardian()
        server = HealthServer(guardian, port=_next_port())
        server.stop()  # should not raise

    def test_404_for_unknown_path(self, health_server):
        _, port, _ = health_server
        status, body = _get_json(port, "/unknown")
        assert status == 404
        assert body["error"] == "not found"
