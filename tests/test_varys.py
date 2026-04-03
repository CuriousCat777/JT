"""Tests for VARYS — cybersecurity sentinel.

Covers: models, ingestion, detection (sigma + anomaly), response, brain,
engine orchestrator, API endpoints, and agent wrapper.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Models ──────────────────────────────────────────────────────────

from guardian_one.varys.models import (
    Alert,
    AlertSeverity,
    EventCategory,
    Incident,
    IncidentStatus,
    SecurityEvent,
)


class TestModels:
    def test_security_event_defaults(self):
        evt = SecurityEvent()
        assert evt.event_id  # auto-generated
        assert evt.timestamp  # auto-generated
        assert evt.source == ""
        assert evt.tags == []

    def test_security_event_fields(self):
        evt = SecurityEvent(
            source="auth_log",
            category="authentication",
            action="login_failed",
            source_ip="10.0.0.1",
            source_user="attacker",
            tags=["ssh", "brute_force_candidate"],
        )
        assert evt.source == "auth_log"
        assert evt.source_ip == "10.0.0.1"
        assert "ssh" in evt.tags

    def test_alert_to_dict(self):
        alert = Alert(
            title="Test Alert",
            severity=AlertSeverity.HIGH,
            rule_id="VARYS-001",
            source_ip="192.168.1.1",
        )
        d = alert.to_dict()
        assert d["severity"] == "high"
        assert d["rule_id"] == "VARYS-001"
        assert d["source_ip"] == "192.168.1.1"
        assert d["event_count"] == 0

    def test_incident_to_dict(self):
        incident = Incident(
            title="Test Incident",
            status=IncidentStatus.INVESTIGATING,
            severity=AlertSeverity.CRITICAL,
            affected_hosts=["server-01"],
        )
        d = incident.to_dict()
        assert d["status"] == "investigating"
        assert d["severity"] == "critical"
        assert d["affected_hosts"] == ["server-01"]


# ── Ingestion ───────────────────────────────────────────────────────

from guardian_one.varys.ingestion.collector import (
    AuthLogCollector,
    SyslogCollector,
)
from guardian_one.varys.ingestion.wazuh_connector import WazuhConnector


class TestAuthLogCollector:
    def test_parse_ssh_failed(self):
        collector = AuthLogCollector()
        line = 'Mar 15 10:23:45 server sshd[12345]: Failed password for invalid user admin from 192.168.1.100 port 22'
        event = collector.parse_line(line)
        assert event is not None
        assert event.action == "login_failed"
        assert event.source_ip == "192.168.1.100"
        assert event.source_user == "admin"
        assert "ssh" in event.tags
        assert "brute_force_candidate" in event.tags

    def test_parse_ssh_accepted(self):
        collector = AuthLogCollector()
        line = 'Mar 15 10:25:00 server sshd[12346]: Accepted publickey for jeremy from 10.0.0.5 port 52234'
        event = collector.parse_line(line)
        assert event is not None
        assert event.action == "login_success"
        assert event.source_ip == "10.0.0.5"
        assert event.source_user == "jeremy"

    def test_parse_sudo(self):
        collector = AuthLogCollector()
        line = 'Mar 15 11:00:00 server sudo:   jeremy : TTY=pts/0 ; PWD=/home ; USER=root ; COMMAND=/bin/ls'
        event = collector.parse_line(line)
        assert event is not None
        assert event.action == "sudo_exec"
        assert event.source_user == "jeremy"

    def test_parse_sudo_dangerous(self):
        collector = AuthLogCollector()
        line = 'Mar 15 11:00:00 server sudo:   root : TTY=pts/0 ; PWD=/ ; USER=root ; COMMAND=chmod 777 /etc/shadow'
        event = collector.parse_line(line)
        assert event is not None
        assert "dangerous_command" in event.tags

    def test_parse_useradd(self):
        collector = AuthLogCollector()
        line = 'Mar 15 12:00:00 server useradd[9999]: new user: name=backdoor'
        event = collector.parse_line(line)
        assert event is not None
        assert event.action == "user_created"
        assert event.source_user == "backdoor"

    def test_parse_unrecognized(self):
        collector = AuthLogCollector()
        event = collector.parse_line("some random log line")
        assert event is None

    def test_collect_from_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write('Mar 15 10:23:45 server sshd[1]: Failed password for root from 1.2.3.4 port 22\n')
            f.write('Mar 15 10:23:46 server sshd[2]: Accepted publickey for jeremy from 10.0.0.1 port 22\n')
            f.flush()
            path = f.name

        try:
            collector = AuthLogCollector(log_path=path)
            events = collector.collect()
            assert len(events) == 2
            assert collector.events_collected == 2
        finally:
            os.unlink(path)


class TestSyslogCollector:
    def test_parse_firewall_drop(self):
        collector = SyslogCollector()
        line = 'Mar 15 10:00:00 server kernel: DROP IN=eth0 SRC=1.2.3.4 DST=10.0.0.1 DPT=445'
        event = collector.parse_line(line)
        assert event is not None
        assert event.action == "firewall_drop"
        assert event.source_ip == "1.2.3.4"
        assert event.destination_port == 445

    def test_parse_service_start(self):
        collector = SyslogCollector()
        line = 'Mar 15 10:00:00 server systemd[1]: Started Apache HTTP Server.'
        event = collector.parse_line(line)
        assert event is not None
        assert event.action == "service_start"
        assert event.process_name == "Apache HTTP Server"

    def test_parse_segfault(self):
        collector = SyslogCollector()
        line = 'Mar 15 10:00:00 server kernel: myapp[1234]: segfault at 0000 ip 00007f sp 00007f error 4 in libfoo.so'
        event = collector.parse_line(line)
        assert event is not None
        assert event.action == "segfault"
        assert "potential_exploit" in event.tags

    def test_parse_cron(self):
        collector = SyslogCollector()
        line = 'Mar 15 10:00:00 server CRON[5678]: (root) CMD (/usr/bin/backup.sh)'
        event = collector.parse_line(line)
        assert event is not None
        assert event.action == "cron_exec"
        assert event.source_user == "root"


class TestWazuhConnector:
    def test_not_available_without_credentials(self):
        connector = WazuhConnector()
        assert not connector.is_available()

    def test_available_with_credentials(self):
        connector = WazuhConnector(
            api_url="https://wazuh:55000",
            api_user="admin",
            api_password="secret",
        )
        assert connector.is_available()

    def test_normalize_alert(self):
        connector = WazuhConnector()
        raw_alert = {
            "id": 1,
            "rule": {
                "id": "5710",
                "level": 10,
                "description": "sshd: Attempt to login using a non-existent user",
                "groups": ["sshd", "authentication_failed"],
            },
            "agent": {
                "name": "server-01",
                "ip": "10.0.0.10",
            },
            "data": {
                "srcip": "1.2.3.4",
                "srcuser": "admin",
            },
        }
        event = connector._normalize_alert(raw_alert)
        assert event is not None
        assert event.source == "wazuh"
        assert event.category == "authentication"
        assert event.severity == "high"  # level 10
        assert event.source_ip == "1.2.3.4"
        assert event.host_name == "server-01"

    def test_map_category(self):
        assert WazuhConnector._map_category(["sshd", "authentication_failed"]) == "authentication"
        assert WazuhConnector._map_category(["syscheck", "fim"]) == "file"
        assert WazuhConnector._map_category(["firewall"]) == "network"
        assert WazuhConnector._map_category(["rootcheck"]) == "malware"
        assert WazuhConnector._map_category(["unknown"]) == "configuration"


# ── Detection — Sigma Engine ────────────────────────────────────────

from guardian_one.varys.detection.sigma_engine import SigmaEngine, SigmaRule


class TestSigmaEngine:
    def _make_engine(self):
        engine = SigmaEngine()
        engine.load_builtin_rules()
        return engine

    def test_load_builtin_rules(self):
        engine = self._make_engine()
        assert len(engine.rules) == 7  # 7 built-in rules

    def test_ssh_brute_force_threshold(self):
        engine = self._make_engine()
        # Needs 5 failed logins to trigger VARYS-001
        for i in range(4):
            alerts = engine.evaluate(SecurityEvent(
                category="authentication",
                action="login_failed",
                source_ip="1.2.3.4",
                tags=["ssh", "brute_force_candidate"],
            ))
            assert len(alerts) == 0

        # 5th event triggers the alert
        alerts = engine.evaluate(SecurityEvent(
            category="authentication",
            action="login_failed",
            source_ip="1.2.3.4",
            tags=["ssh", "brute_force_candidate"],
        ))
        assert len(alerts) == 1
        assert alerts[0].rule_id == "VARYS-001"
        assert alerts[0].severity == AlertSeverity.HIGH

    def test_privilege_escalation(self):
        engine = self._make_engine()
        alerts = engine.evaluate(SecurityEvent(
            category="process",
            action="sudo_exec",
            source_user="attacker",
            process_command_line="chmod 777 /etc/shadow",
            tags=["sudo", "dangerous_command"],
        ))
        assert len(alerts) == 1
        assert alerts[0].rule_id == "VARYS-002"

    def test_user_created(self):
        engine = self._make_engine()
        alerts = engine.evaluate(SecurityEvent(
            category="iam",
            action="user_created",
            source_user="backdoor",
            tags=["user_management"],
        ))
        assert len(alerts) == 1
        assert alerts[0].rule_id == "VARYS-003"

    def test_custom_rule(self):
        engine = SigmaEngine()
        engine.load_rule(SigmaRule(
            rule_id="CUSTOM-001",
            name="Test Rule",
            severity=AlertSeverity.LOW,
            conditions={"category": "web", "action": "contains:sql_injection"},
        ))
        alerts = engine.evaluate(SecurityEvent(
            category="web",
            action="sql_injection_attempt",
        ))
        assert len(alerts) == 1
        assert alerts[0].rule_id == "CUSTOM-001"

    def test_regex_condition(self):
        engine = SigmaEngine()
        engine.load_rule(SigmaRule(
            rule_id="RE-001",
            name="Regex Test",
            conditions={"process_command_line": "re:rm\\s+-rf\\s+/"},
        ))
        alerts = engine.evaluate(SecurityEvent(
            process_command_line="rm -rf /var/data",
        ))
        assert len(alerts) == 1

    def test_no_match(self):
        engine = self._make_engine()
        alerts = engine.evaluate(SecurityEvent(
            category="web",
            action="page_view",
        ))
        assert len(alerts) == 0

    def test_evaluate_batch(self):
        engine = self._make_engine()
        events = [
            SecurityEvent(category="iam", action="user_created", tags=["user_management"]),
            SecurityEvent(category="process", action="sudo_exec", tags=["sudo", "dangerous_command"]),
        ]
        alerts = engine.evaluate_batch(events)
        assert len(alerts) == 2


# ── Detection — Anomaly ─────────────────────────────────────────────

from guardian_one.varys.detection.anomaly import AnomalyDetector, BehaviorProfile


class TestAnomalyDetector:
    def test_behavior_profile_stats(self):
        profile = BehaviorProfile(entity="testuser")
        for v in [10, 12, 11, 9, 10]:
            profile.add_observation("login", float(v))
        assert profile.has_baseline
        assert 9 < profile.mean("login") < 12
        assert profile.stddev("login") > 0

    def test_z_score(self):
        profile = BehaviorProfile(entity="testuser")
        for v in [10, 10, 10, 10, 10]:
            profile.add_observation("login", float(v))
        # stddev is 0, z_score returns 0
        assert profile.z_score("login", 100) == 0.0

        # With variance
        profile2 = BehaviorProfile(entity="testuser2")
        for v in [10, 11, 9, 10, 11]:
            profile2.add_observation("login", float(v))
        z = profile2.z_score("login", 30)
        assert z > 3  # Way above normal

    def test_no_anomaly_without_baseline(self):
        detector = AnomalyDetector()
        event = SecurityEvent(
            source_user="newuser",
            action="login_success",
        )
        alert = detector.detect(event)
        assert alert is None

    def test_status(self):
        detector = AnomalyDetector(z_threshold=2.5)
        status = detector.status()
        assert status["z_threshold"] == 2.5
        assert status["total_anomalies"] == 0


# ── Response ────────────────────────────────────────────────────────

from guardian_one.varys.response.actions import (
    ActionType,
    ActionStatus,
    ResponseAction,
    ResponseEngine,
)


class TestResponseEngine:
    def test_alert_auto_dispatched(self):
        engine = ResponseEngine(dry_run=True)
        alert = Alert(
            title="Test Alert",
            severity=AlertSeverity.LOW,
            source_ip="1.2.3.4",
        )
        actions = engine.respond(alert)
        # Should have at least the ALERT action
        alert_actions = [a for a in actions if a.action_type == ActionType.ALERT]
        assert len(alert_actions) == 1
        assert alert_actions[0].status == ActionStatus.EXECUTED

    def test_high_severity_proposes_block(self):
        engine = ResponseEngine(dry_run=True)
        alert = Alert(
            title="Brute Force",
            severity=AlertSeverity.HIGH,
            source_ip="1.2.3.4",
        )
        actions = engine.respond(alert)
        block_actions = [a for a in actions if a.action_type == ActionType.BLOCK_IP]
        assert len(block_actions) == 1

    def test_critical_creates_incident(self):
        engine = ResponseEngine(dry_run=True)
        alert = Alert(
            title="Critical Threat",
            severity=AlertSeverity.CRITICAL,
            source_ip="1.2.3.4",
            source_user="attacker",
            host_name="server-01",
        )
        actions = engine.respond(alert)
        assert len(engine.incidents) == 1
        assert engine.incidents[0].severity == AlertSeverity.CRITICAL

        # Should propose session revocation
        revoke = [a for a in actions if a.action_type == ActionType.REVOKE_SESSIONS]
        assert len(revoke) == 1
        assert revoke[0].requires_approval is True

    def test_alert_callback(self):
        engine = ResponseEngine(dry_run=True)
        received = []
        engine.on_alert(lambda a: received.append(a))

        alert = Alert(title="Callback Test", severity=AlertSeverity.LOW)
        engine.respond(alert)
        assert len(received) == 1
        assert received[0].title == "Callback Test"

    def test_approve_action(self):
        engine = ResponseEngine(dry_run=True)
        alert = Alert(
            title="Block Test",
            severity=AlertSeverity.HIGH,
            source_ip="1.2.3.4",
        )
        actions = engine.respond(alert)
        pending = [a for a in actions if a.status == ActionStatus.PENDING]
        assert len(pending) > 0
        assert engine.approve_action(pending[0])
        assert pending[0].status == ActionStatus.EXECUTED

    def test_deny_action(self):
        engine = ResponseEngine(dry_run=True)
        action = ResponseAction(
            action_type=ActionType.BLOCK_IP,
            target="1.2.3.4",
            reason="test",
        )
        engine._pending_actions.append(action)
        engine.deny_action(action)
        assert action.status == ActionStatus.DENIED
        assert len(engine.pending_actions) == 0

    def test_status(self):
        engine = ResponseEngine(dry_run=True)
        status = engine.status()
        assert status["dry_run"] is True
        assert status["pending_actions"] == 0


# ── Brain — LLM Triage ──────────────────────────────────────────────

from guardian_one.varys.brain.llm_triage import LLMTriage


class TestLLMTriage:
    def test_deterministic_fallback(self):
        triage = LLMTriage(ai_engine=None)
        alert = Alert(
            title="SSH Brute Force",
            severity=AlertSeverity.HIGH,
            rule_id="VARYS-001",
            rule_name="SSH Brute Force Attempt",
        )
        result = triage.triage(alert)
        assert result["assessed_severity"] == "high"
        assert result["confidence"] == 0.5  # Lower without AI
        assert "Deterministic" in result["summary"]
        assert alert.risk_score == 0.75

    def test_parse_json_response(self):
        raw = '```json\n{"assessed_severity": "high", "confidence": 0.9}\n```'
        result = LLMTriage._parse_json_response(raw)
        assert result is not None
        assert result["assessed_severity"] == "high"

    def test_parse_plain_json(self):
        raw = '{"assessed_severity": "low", "confidence": 0.3}'
        result = LLMTriage._parse_json_response(raw)
        assert result is not None
        assert result["assessed_severity"] == "low"

    def test_parse_invalid_json(self):
        result = LLMTriage._parse_json_response("not json at all")
        assert result is None

    def test_is_available_without_engine(self):
        triage = LLMTriage()
        assert not triage.is_available


# ── Brain — Risk Scoring ────────────────────────────────────────────

from guardian_one.varys.brain.risk_scoring import RiskScorer


class TestRiskScorer:
    def test_score_low_alert(self):
        scorer = RiskScorer()
        alert = Alert(severity=AlertSeverity.LOW, rule_id="TEST")
        score = scorer.score_alert(alert)
        assert 0 < score < 0.5

    def test_score_critical_alert(self):
        scorer = RiskScorer()
        alert = Alert(
            severity=AlertSeverity.CRITICAL,
            rule_id="TEST",
            mitre_tactic="TA0004",  # High-risk tactic
        )
        alert.events = [SecurityEvent() for _ in range(15)]
        score = scorer.score_alert(alert)
        assert score > 0.5

    def test_recurrence_increases_score(self):
        scorer = RiskScorer()
        a1 = Alert(severity=AlertSeverity.MEDIUM, rule_id="REPEAT")
        s1 = scorer.score_alert(a1)

        # Score the same rule again — recurrence should increase score
        a2 = Alert(severity=AlertSeverity.MEDIUM, rule_id="REPEAT")
        s2 = scorer.score_alert(a2)
        assert s2 >= s1

    def test_entity_tracking(self):
        scorer = RiskScorer()
        alert = Alert(
            severity=AlertSeverity.HIGH,
            source_ip="1.2.3.4",
            source_user="attacker",
            host_name="victim-host",
        )
        scorer.score_alert(alert)
        assert len(scorer.entity_risks) == 3  # ip, user, host

    def test_high_risk_entities(self):
        scorer = RiskScorer()
        alert = Alert(
            severity=AlertSeverity.CRITICAL,
            source_ip="1.2.3.4",
            mitre_tactic="TA0006",
        )
        alert.events = [SecurityEvent() for _ in range(10)]
        scorer.score_alert(alert)
        high_risk = scorer.get_high_risk_entities(threshold=0.5)
        assert len(high_risk) >= 1


# ── Engine Orchestrator ─────────────────────────────────────────────

from guardian_one.varys.engine import VarysEngine


class TestVarysEngine:
    def test_init(self):
        engine = VarysEngine()
        assert len(engine.sigma.rules) == 7  # Built-in rules loaded
        assert not engine._running

    def test_ingest_events(self):
        engine = VarysEngine()
        events = [
            SecurityEvent(
                category="iam",
                action="user_created",
                source_user="backdoor",
                tags=["user_management"],
            )
        ]
        alerts = engine.ingest_events(events)
        assert len(alerts) == 1
        assert alerts[0].rule_id == "VARYS-003"

    def test_cycle_no_collectors(self):
        engine = VarysEngine()
        alerts = engine.cycle()
        assert alerts == []

    def test_status(self):
        engine = VarysEngine()
        status = engine.status()
        assert status["running"] is False
        assert status["total_events"] == 0
        assert status["detection"]["rules_loaded"] == 7
        assert "brain" in status
        assert "response" in status

    def test_full_pipeline(self):
        """End-to-end: events → detection → triage → scoring → response."""
        engine = VarysEngine(dry_run=True)
        received_alerts = []
        engine.response.on_alert(lambda a: received_alerts.append(a))

        # Inject events that trigger the privilege escalation rule
        events = [
            SecurityEvent(
                category="process",
                action="sudo_exec",
                source_user="hacker",
                process_command_line="rm -rf /",
                host_name="prod-server",
                tags=["sudo", "dangerous_command"],
            ),
        ]
        alerts = engine.ingest_events(events)
        assert len(alerts) >= 1
        assert alerts[0].rule_id == "VARYS-002"
        assert alerts[0].risk_score > 0  # Scored
        assert alerts[0].triage_result  # Triaged (deterministic)
        assert len(received_alerts) >= 1  # Alert callback fired


# ── API Endpoints ───────────────────────────────────────────────────

class TestVarysAPI:
    @pytest.fixture
    def client(self):
        from guardian_one.varys.api.main import create_varys_blueprint
        from flask import Flask

        engine = VarysEngine(dry_run=True)
        app = Flask(__name__)
        bp = create_varys_blueprint(engine)
        app.register_blueprint(bp)
        app.config["TESTING"] = True
        # Store engine on fixture for access
        self._engine = engine
        return app.test_client()

    def test_health(self, client):
        resp = client.get("/varys/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_status(self, client):
        resp = client.get("/varys/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_events" in data
        assert "detection" in data

    def test_rules(self, client):
        resp = client.get("/varys/rules")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 7

    def test_events_ingest(self, client):
        resp = client.post("/varys/events", json={
            "events": [
                {
                    "source": "api",
                    "category": "iam",
                    "action": "user_created",
                    "source_user": "backdoor",
                }
            ]
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["accepted"] == 1

    def test_events_missing_body(self, client):
        resp = client.post("/varys/events", json={})
        assert resp.status_code == 400

    def test_alerts_endpoint(self, client):
        resp = client.get("/varys/alerts")
        assert resp.status_code == 200

    def test_incidents_endpoint(self, client):
        resp = client.get("/varys/incidents")
        assert resp.status_code == 200

    def test_entities_endpoint(self, client):
        resp = client.get("/varys/entities")
        assert resp.status_code == 200


# ── Agent Wrapper ───────────────────────────────────────────────────

from guardian_one.varys.agent import VarysAgent
from guardian_one.core.audit import AuditLog
from guardian_one.core.config import AgentConfig


class TestVarysAgent:
    @pytest.fixture
    def agent(self, tmp_path):
        config = AgentConfig(
            name="varys",
            enabled=True,
            schedule_interval_minutes=5,
            allowed_resources=["security_events"],
            custom={
                "dry_run": True,
                "auth_log": False,  # Disable real log access in tests
                "syslog": False,
            },
        )
        audit = AuditLog(log_dir=tmp_path)
        return VarysAgent(config, audit)

    def test_initialize(self, agent):
        agent.initialize()
        assert agent.engine is not None
        assert len(agent.engine.sigma.rules) == 7

    def test_run(self, agent):
        agent.initialize()
        report = agent.run()
        assert report.agent_name == "varys"
        assert report.status in ("ok", "alert")

    def test_report_before_init(self, agent):
        report = agent.report()
        assert report.status == "not_initialized"

    def test_report_after_init(self, agent):
        agent.initialize()
        report = agent.report()
        assert "VARYS" in report.summary
        assert report.data  # Has status dict

    def test_shutdown(self, agent):
        agent.initialize()
        agent.shutdown()
