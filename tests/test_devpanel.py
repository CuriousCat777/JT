"""Tests for the Guardian One web-based dev panel."""

import json
import os
import pytest
import guardian_one.web.app as web_app
from guardian_one.web.app import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GUARDIAN_MASTER_PASSPHRASE", "test-pass")
    web_app._guardian = None  # reset singleton for test isolation
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_index_returns_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"GUARDIAN ONE" in resp.data


def test_api_status(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "owner" in data
    assert "agents" in data
    assert isinstance(data["agents"], list)
    assert len(data["agents"]) > 0


def test_api_agents(client):
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    agents = resp.get_json()
    assert isinstance(agents, list)
    names = [a["name"] for a in agents]
    assert "chronos" in names
    assert "cfo" in names


def test_api_run_agent(client):
    resp = client.post("/api/agents/chronos/run")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "agent_name" in data
    assert data["agent_name"] == "chronos"


def test_api_run_unknown_agent(client):
    resp = client.post("/api/agents/nonexistent/run")
    assert resp.status_code == 404


def test_api_run_all(client):
    resp = client.post("/api/agents/run-all")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_api_audit(client):
    resp = client.get("/api/audit?limit=10")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)


def test_api_audit_pending(client):
    resp = client.get("/api/audit/pending")
    assert resp.status_code == 200


def test_api_audit_summary(client):
    resp = client.get("/api/audit/summary")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "summary" in data


def test_api_homelink_services(client):
    resp = client.get("/api/homelink/services")
    assert resp.status_code == 200


def test_api_homelink_health(client):
    resp = client.get("/api/homelink/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)


def test_api_homelink_anomalies(client):
    resp = client.get("/api/homelink/anomalies")
    assert resp.status_code == 200


def test_api_vault(client):
    resp = client.get("/api/vault")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "health" in data
    assert "credentials" in data


def test_api_registry(client):
    resp = client.get("/api/registry")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_api_registry_threats(client):
    resp = client.get("/api/registry/doordash_drive/threats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "threats" in data
    assert len(data["threats"]) > 0


def test_api_registry_unknown(client):
    resp = client.get("/api/registry/fake_service/threats")
    assert resp.status_code == 404


def test_api_config(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "owner" in data
    assert "agents" in data


def test_api_summary(client):
    resp = client.get("/api/summary")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "summary" in data
