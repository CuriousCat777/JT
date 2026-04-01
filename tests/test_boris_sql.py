"""Tests for Boris SQL Store — self-enriching SQLite log database."""

import json
from pathlib import Path

import pytest

from guardian_one.core.boris_sql import BorisSQLStore


@pytest.fixture
def db(tmp_path):
    store = BorisSQLStore(tmp_path / "boris_test.db")
    yield store
    store.close()


class TestEvents:
    def test_log_and_query(self, db):
        db.log_event("connectivity", "MCP check passed", severity="info")
        db.log_event("breach", "Port scan detected", severity="high")
        events = db.query_events()
        assert len(events) == 2

    def test_query_by_category(self, db):
        db.log_event("connectivity", "check 1")
        db.log_event("breach", "alert 1")
        db.log_event("connectivity", "check 2")
        events = db.query_events(category="connectivity")
        assert len(events) == 2

    def test_query_by_severity(self, db):
        db.log_event("test", "low", severity="info")
        db.log_event("test", "high", severity="critical")
        events = db.query_events(severity="critical")
        assert len(events) == 1

    def test_event_stats(self, db):
        db.log_event("a", "x", severity="info")
        db.log_event("a", "y", severity="warning")
        db.log_event("b", "z", severity="info")
        stats = db.event_stats()
        assert stats["total"] == 3
        assert stats["by_category"]["a"] == 2
        assert stats["by_severity"]["info"] == 2


class TestConnections:
    def test_log_connection(self, db):
        db.log_connection("github", "GitHub", "connected", tools_count=45)
        history = db.connection_history()
        assert len(history) == 1
        assert history[0]["server_id"] == "github"

    def test_filter_by_server(self, db):
        db.log_connection("github", "GitHub", "connected")
        db.log_connection("notion", "Notion", "connected")
        assert len(db.connection_history(server_id="github")) == 1


class TestBreaches:
    def test_log_and_query(self, db):
        db.log_breach("unexpected_port", "localhost:9999", "Unknown service on port 9999")
        breaches = db.unresolved_breaches()
        assert len(breaches) == 1
        assert breaches[0]["breach_type"] == "unexpected_port"

    def test_resolve_breach(self, db):
        db.log_breach("brute_force", "sshd", "10 failures")
        breaches = db.unresolved_breaches()
        assert len(breaches) == 1
        db.resolve_breach(breaches[0]["id"])
        assert len(db.unresolved_breaches()) == 0

    def test_breach_creates_event(self, db):
        db.log_breach("test", "target", "desc")
        events = db.query_events(category="breach")
        assert len(events) == 1


class TestHealth:
    def test_log_health(self, db):
        db.log_health(cpu_pct=25.5, memory_pct=60.0, memory_mb=4096,
                       disk_pct=45.0, py_objects=100000)
        history = db.health_history(limit=1)
        assert len(history) == 1
        assert history[0]["cpu_pct"] == 25.5
        assert history[0]["memory_pct"] == 60.0


class TestRepairs:
    def test_log_repair(self, db):
        db.log_repair("web:chat.html", "Missing ARIA")
        repairs = db.open_repairs()
        assert len(repairs) == 1

    def test_resolve_repair(self, db):
        db.log_repair("test", "issue")
        repairs = db.open_repairs()
        db.resolve_repair_sql(repairs[0]["id"], notes="fixed")
        assert len(db.open_repairs()) == 0


class TestEnrichment:
    def test_enrich_runs_without_error(self, db):
        result = db.enrich()
        assert isinstance(result, list)

    def test_repair_backlog_rule(self, db):
        for i in range(6):
            db.log_repair(f"comp-{i}", f"issue-{i}")
        enrichments = db.enrich()
        backlog = [e for e in enrichments if e["rule"] == "repair_backlog"]
        assert len(backlog) == 1
        assert "6 open repairs" in backlog[0]["conclusion"]

    def test_enrichment_dedup(self, db):
        for i in range(6):
            db.log_repair(f"comp-{i}", f"issue-{i}")
        db.enrich()
        # Second run should not create duplicates
        second = db.enrich()
        backlog = [e for e in second if e["rule"] == "repair_backlog"]
        assert len(backlog) == 0

    def test_intelligence_summary(self, db):
        db.log_event("test", "hello")
        db.log_breach("test", "target", "desc")
        db.log_health(10, 50, 2048, 30)
        summary = db.intelligence_summary()
        assert summary["events"]["total"] >= 1
        assert summary["unresolved_breaches"] >= 1
