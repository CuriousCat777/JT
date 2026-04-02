"""Tests for the health check API server."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from guardian_one.core.health import HealthServer


@pytest.fixture
def mock_guardian():
    """Create a mock GuardianOne instance for health server testing."""
    guardian = MagicMock()
    guardian.list_agents.return_value = ["chronos", "cfo", "archivist"]
    guardian.config.owner = "Test Owner"

    # Mock agents
    mock_agent = MagicMock()
    mock_agent.status.value = "idle"
    mock_agent.ai_enabled = True
    guardian.get_agent.return_value = mock_agent

    # Mock AI status
    guardian.ai_status.return_value = {
        "active_provider": "ollama",
        "total_requests": 42,
    }

    # Mock gateway
    guardian.gateway.list_services.return_value = ["notion", "gmail"]

    # Mock vault
    guardian.vault.health_report.return_value = {
        "total_credentials": 3,
        "due_for_rotation": 0,
    }

    return guardian


@pytest.fixture
def health_app(mock_guardian):
    """Create a Flask test client for the health server."""
    server = HealthServer(mock_guardian, port=0)
    server._app.testing = True
    return server._app.test_client()


class TestHealthEndpoint:
    """Tests for /health liveness probe."""

    def test_returns_200(self, health_app):
        resp = health_app.get("/health")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "ok"
        assert "timestamp" in data


class TestReadyEndpoint:
    """Tests for /ready readiness probe."""

    def test_ready_with_agents(self, health_app):
        resp = health_app.get("/ready")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "ready"
        assert data["agents"] == 3

    def test_not_ready_without_agents(self, mock_guardian):
        mock_guardian.list_agents.return_value = []
        server = HealthServer(mock_guardian, port=0)
        server._app.testing = True
        client = server._app.test_client()
        resp = client.get("/ready")
        assert resp.status_code == 503
        data = json.loads(resp.data)
        assert data["status"] == "not_ready"


class TestStatusEndpoint:
    """Tests for /status full system status."""

    def test_status_payload(self, health_app):
        resp = health_app.get("/status")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "operational"
        assert "uptime_seconds" in data
        assert "agents" in data
        assert "ai_engine" in data
        assert "homelink" in data
        assert data["owner"] == "Test Owner"

    def test_agent_statuses_included(self, health_app):
        resp = health_app.get("/status")
        data = json.loads(resp.data)
        assert "chronos" in data["agents"]
        assert "cfo" in data["agents"]


class TestMetricsEndpoint:
    """Tests for /metrics Prometheus-compatible output."""

    def test_metrics_format(self, health_app):
        resp = health_app.get("/metrics")
        assert resp.status_code == 200
        assert resp.content_type == "text/plain"
        text = resp.data.decode()
        assert "guardian_uptime_seconds" in text
        assert "guardian_agents_total 3" in text
        assert "guardian_ai_requests_total 42" in text
        assert "guardian_vault_credentials_total 3" in text

    def test_per_agent_metrics(self, health_app):
        resp = health_app.get("/metrics")
        text = resp.data.decode()
        assert 'guardian_agent_running{agent="chronos"}' in text
        assert 'guardian_agent_running{agent="cfo"}' in text
