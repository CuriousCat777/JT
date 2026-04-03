"""Tests for Archivist v2 — TelemetryHub, TechDetector, CloudSync, persistence."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from guardian_one.core.audit import AuditLog
from guardian_one.core.config import AgentConfig


# ── TelemetryHub ────────────────────────────────────────────────────

from guardian_one.archivist.telemetry import TelemetryHub, TelemetryEvent


class TestTelemetryHub:
    @pytest.fixture
    def hub(self, tmp_path):
        return TelemetryHub(data_dir=tmp_path)

    def test_log_event(self, hub):
        event = TelemetryEvent(
            source="github",
            source_type="service",
            action="repo_push",
            actor="jeremy",
            target="JT/main",
        )
        hub.log(event)
        assert hub.total_logged == 1

    def test_log_simple(self, hub):
        hub.log_simple(
            source="gmail",
            action="email_received",
            actor="sender@example.com",
            target="inbox",
        )
        assert hub.total_logged == 1

    def test_query_by_source(self, hub):
        hub.log_simple(source="github", action="push")
        hub.log_simple(source="gmail", action="email")
        hub.log_simple(source="github", action="pr_created")

        results = hub.query(source="github")
        assert len(results) == 2

    def test_query_by_category(self, hub):
        hub.log_simple(source="archivist", action="init", category="config_change")
        hub.log_simple(source="cfo", action="transaction", category="interaction")

        results = hub.query(category="config_change")
        assert len(results) == 1

    def test_sources_count(self, hub):
        hub.log_simple(source="github", action="push")
        hub.log_simple(source="github", action="push")
        hub.log_simple(source="gmail", action="email")

        sources = hub.sources()
        assert sources["github"] == 2
        assert sources["gmail"] == 1

    def test_persistence_jsonl(self, hub, tmp_path):
        hub.log_simple(source="test", action="event1")
        hub.log_simple(source="test", action="event2")

        # Verify JSONL file exists
        log_file = tmp_path / "telemetry.jsonl"
        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_load_from_disk(self, tmp_path):
        # Write events to disk
        hub1 = TelemetryHub(data_dir=tmp_path)
        hub1.log_simple(source="github", action="push")
        hub1.log_simple(source="gmail", action="email")

        # Load from disk in new instance
        hub2 = TelemetryHub(data_dir=tmp_path)
        hub2.load_from_disk()
        assert hub2.total_logged == 2

    def test_status(self, hub):
        hub.log_simple(source="test", action="event")
        status = hub.status()
        assert status["total_logged"] == 1
        assert "test" in status["sources"]


# ── TechDetector ────────────────────────────────────────────────────

from guardian_one.archivist.techdetect import TechDetector, TechRecord


class TestTechDetector:
    @pytest.fixture
    def detector(self, tmp_path):
        return TechDetector(data_dir=tmp_path)

    def test_first_detection(self, detector):
        record = detector.check("ollama", source_type="ai_model", action="model_loaded")
        assert record is not None
        assert record.name == "ollama"
        assert record.tech_type == "ai_model"

    def test_known_tech_returns_none(self, detector):
        detector.check("ollama", source_type="ai_model")
        result = detector.check("ollama", source_type="ai_model")
        assert result is None

    def test_interaction_count_increments(self, detector):
        detector.check("github", source_type="service")
        detector.check("github", source_type="service")
        detector.check("github", source_type="service")
        record = detector.registry["service:github"]
        assert record.interaction_count == 3

    def test_new_detections_queue(self, detector):
        detector.check("slack", source_type="service")
        detector.check("discord", source_type="service")
        detections = detector.new_detections
        assert len(detections) == 2
        # Queue cleared after read
        assert len(detector.new_detections) == 0

    def test_persistence(self, tmp_path):
        d1 = TechDetector(data_dir=tmp_path)
        d1.check("notion", source_type="service")
        d1.check("ollama", source_type="ai_model")
        d1.save()

        d2 = TechDetector(data_dir=tmp_path)
        d2.load()
        assert len(d2.registry) == 2
        assert "service:notion" in d2.registry

    def test_unreviewed(self, detector):
        detector.check("new_tool", source_type="tool")
        assert len(detector.get_unreviewed()) == 1
        detector.mark_reviewed("new_tool", "tool")
        assert len(detector.get_unreviewed()) == 0

    def test_unbacked_up(self, detector):
        detector.check("new_api", source_type="api")
        assert len(detector.get_unbacked_up()) == 1
        detector.mark_backed_up("new_api", "api")
        assert len(detector.get_unbacked_up()) == 0

    def test_status(self, detector):
        detector.check("tool_a", source_type="tool")
        detector.check("service_b", source_type="service")
        status = detector.status()
        assert status["total_tracked"] == 2
        assert status["by_type"]["tool"] == 1
        assert status["by_type"]["service"] == 1


# ── CloudSync ───────────────────────────────────────────────────────

from guardian_one.archivist.cloudsync import CloudSync, CloudTarget


class TestCloudSync:
    @pytest.fixture
    def sync(self, tmp_path):
        cs = CloudSync(data_dir=tmp_path)
        cs.setup_defaults()
        return cs

    def test_setup_defaults(self, sync):
        assert "local_backup" in sync.targets
        assert "cloudflare_r2" in sync.targets
        assert "github_backup" in sync.targets

    def test_add_remove_target(self, tmp_path):
        cs = CloudSync(data_dir=tmp_path)
        cs.add_target(CloudTarget(name="test", provider="local", bucket=str(tmp_path / "test")))
        assert "test" in cs.targets
        cs.remove_target("test")
        assert "test" not in cs.targets

    def test_backup_local(self, sync, tmp_path):
        # Create a test file
        test_file = tmp_path / "test_data.json"
        test_file.write_text('{"key": "value"}')

        records = sync.backup_file(str(test_file), target_name="local_backup")
        assert len(records) == 1
        assert records[0].success is True

    def test_backup_missing_file(self, sync):
        records = sync.backup_file("/nonexistent/file.txt")
        assert len(records) == 1
        assert records[0].success is False
        assert "not found" in records[0].error

    def test_persistence(self, tmp_path):
        cs1 = CloudSync(data_dir=tmp_path)
        cs1.add_target(CloudTarget(name="custom", provider="local", bucket="/tmp/test"))
        cs1.save_config()

        cs2 = CloudSync(data_dir=tmp_path)
        cs2.load_config()
        assert "custom" in cs2.targets

    def test_status(self, sync):
        status = sync.status()
        assert "targets" in status
        assert "local_backup" in status["targets"]
        assert status["total_backups"] == 0


# ── Archivist Agent (integrated) ────────────────────────────────────

from guardian_one.agents.archivist import Archivist, FileRecord, RetentionPolicy


class TestArchivistV2:
    @pytest.fixture
    def agent(self, tmp_path):
        config = AgentConfig(
            name="archivist",
            enabled=True,
            schedule_interval_minutes=60,
            allowed_resources=["file_index", "data_sources", "privacy_tools"],
            custom={"data_dir": str(tmp_path)},
        )
        audit = AuditLog(log_dir=tmp_path / "logs")
        return Archivist(config, audit)

    def test_initialize(self, agent):
        agent.initialize()
        assert agent.telemetry is not None
        assert agent.tech_detector is not None
        assert agent.cloud_sync is not None

    def test_record_interaction(self, agent):
        agent.initialize()
        agent.record_interaction(
            source="github",
            action="repo_push",
            source_type="service",
            actor="jeremy",
            target="JT/main",
        )
        assert agent.telemetry.total_logged >= 2  # init + this interaction

    def test_new_tech_detection_via_interaction(self, agent):
        agent.initialize()
        agent.record_interaction(
            source="new_llm_tool",
            source_type="ai_model",
            action="first_use",
        )
        # Should be in tech registry
        assert "ai_model:new_llm_tool" in agent.tech_detector.registry

    def test_persistence_round_trip(self, agent, tmp_path):
        agent.initialize()
        agent.register_file(FileRecord(
            path="/docs/resume.pdf",
            category="professional",
            tags=["cv", "career"],
        ))
        agent.set_profile_field("email", "jeremy@example.com")

        # Run triggers save
        agent.run()

        # New agent instance loads state
        config2 = AgentConfig(
            name="archivist",
            enabled=True,
            schedule_interval_minutes=60,
            allowed_resources=["file_index"],
            custom={"data_dir": str(tmp_path)},
        )
        audit2 = AuditLog(log_dir=tmp_path / "logs2")
        agent2 = Archivist(config2, audit2)
        agent2.initialize()

        assert len(agent2.search_files()) == 1
        assert agent2.get_profile()["email"] == "jeremy@example.com"

    def test_run_report(self, agent):
        agent.initialize()
        report = agent.run()
        assert report.agent_name == "archivist"
        assert "telemetry" in report.data
        assert "tech_detector" in report.data
        assert "cloud_sync" in report.data

    def test_report(self, agent):
        agent.initialize()
        report = agent.report()
        assert "telemetry" in report.data

    def test_shutdown_persists(self, agent, tmp_path):
        agent.initialize()
        agent.register_file(FileRecord(path="/test.txt", category="personal"))
        agent.shutdown()

        # Verify state file exists
        state_file = tmp_path / "archivist_state.json"
        assert state_file.exists()

    def test_sync_source_logs_telemetry(self, agent):
        agent.initialize()
        initial = agent.telemetry.total_logged
        agent.sync_source("smartwatch")
        assert agent.telemetry.total_logged > initial
