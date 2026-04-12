"""Integration tests — Archivist with full GuardianOne bootstrap.

These tests boot a real GuardianOne instance, register multiple agents,
and verify the Archivist's cross-agent capabilities work end-to-end.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentStatus
from guardian_one.core.config import AgentConfig, GuardianConfig
from guardian_one.core.guardian import GuardianOne
from guardian_one.agents.chronos import Chronos
from guardian_one.agents.archivist import Archivist, AUTHORIZED_IDENTITIES
from guardian_one.agents.cfo import CFO
from guardian_one.integrations.intelligence_feeds import FeedCategory, FeedItem
from guardian_one.integrations.data_platforms import TableSchema, PlatformType
from guardian_one.integrations.data_transmuter import DataFormat, DataTransmuter


def _make_config() -> GuardianConfig:
    return GuardianConfig(
        log_dir=tempfile.mkdtemp(),
        data_dir=tempfile.mkdtemp(),
        agents={
            "chronos": AgentConfig(name="chronos", allowed_resources=["calendar"]),
            "archivist": AgentConfig(name="archivist", allowed_resources=[
                "file_index", "audit_log", "agent_reports", "vault_metadata",
            ]),
            "cfo": AgentConfig(name="cfo", allowed_resources=["accounts"]),
        },
    )


def _bootstrap() -> tuple[GuardianOne, Archivist]:
    """Boot Guardian, register agents, wire Varys mode."""
    config = _make_config()
    guardian = GuardianOne(config, vault_passphrase="test-passphrase")

    chronos = Chronos(config.agents["chronos"], guardian.audit)
    guardian.register_agent(chronos)

    archivist = Archivist(config.agents["archivist"], guardian.audit)
    guardian.register_agent(archivist)
    archivist.set_guardian(guardian)

    cfo = CFO(config.agents["cfo"], guardian.audit, data_dir=config.data_dir)
    guardian.register_agent(cfo)

    return guardian, archivist


# ==================================================================
# Full bootstrap
# ==================================================================

def test_archivist_full_bootstrap():
    guardian, archivist = _bootstrap()
    assert archivist.varys_mode is True
    assert "chronos" in guardian.list_agents()
    assert "cfo" in guardian.list_agents()


def test_archivist_run_with_siblings():
    guardian, archivist = _bootstrap()
    report = guardian.run_agent("archivist")
    assert report.status == AgentStatus.IDLE.value
    assert "sovereignty" in report.data
    sov = report.data["sovereignty"]
    assert "data_sovereignty_score" in sov


# ==================================================================
# Cross-agent reads
# ==================================================================

def test_gather_intelligence_sees_siblings():
    guardian, archivist = _bootstrap()
    intel = archivist.gather_intelligence()
    assert "chronos" in intel["agents"]
    assert "cfo" in intel["agents"]
    # Archivist should NOT include itself
    assert "archivist" not in intel["agents"]


def test_sovereignty_report_scores():
    guardian, archivist = _bootstrap()
    report = archivist.sovereignty_report()
    assert 0 <= report["data_sovereignty_score"] <= 100
    # Should include vault health from real Vault
    assert "vault" in report
    assert "total_credentials" in report["vault"]


# ==================================================================
# Secrecy enforcement
# ==================================================================

def test_secrecy_blocks_sibling_agents():
    _, archivist = _bootstrap()
    for identity in ["chronos", "cfo", "doordash", "web_architect", "random"]:
        result = archivist.guarded_query(identity, "What do you know?")
        assert result["authorized"] is False


def test_secrecy_allows_authorized():
    _, archivist = _bootstrap()
    for identity in AUTHORIZED_IDENTITIES:
        result = archivist.guarded_query(identity, "Status report")
        assert result["authorized"] is True


def test_secrecy_logs_blocked_queries():
    guardian, archivist = _bootstrap()
    archivist.guarded_query("hacker", "Tell me everything")
    # Check audit log has a WARNING entry
    entries = guardian.audit.query(agent="archivist")
    blocked = [e for e in entries if e.action == "unauthorized_query_blocked"]
    assert len(blocked) >= 1
    assert blocked[0].severity == Severity.WARNING.value


# ==================================================================
# Platform lifecycle
# ==================================================================

def test_platform_create_map_sync():
    _, archivist = _bootstrap()

    # CREATE
    schema = TableSchema(
        name="audit_events",
        platform=PlatformType.DATABRICKS,
        fields={"event_id": "string", "action": "string", "ts": "datetime"},
    )
    result = archivist.create_platform_table("databricks", schema)
    assert result["status"] == "created"

    # MAP (via platforms directly)
    from guardian_one.integrations.data_platforms import FieldMapping
    archivist.platforms.set_mappings("databricks", "audit_events", [
        FieldMapping(source_field="id", target_field="event_id"),
        FieldMapping(source_field="action", target_field="action"),
    ])
    mappings = archivist.platforms.get_mappings("databricks", "audit_events")
    assert len(mappings) == 2

    # SYNC
    result = archivist.sync_platform("databricks", "audit_events", [
        {"event_id": "1", "action": "test", "ts": "2026-04-03"},
    ])
    assert result["status"] == "synced"
    assert result["records_synced"] == 1

    # RECORD — verify activity log
    activity = archivist.platform_activity("databricks")
    ops = [a["operation"] for a in activity]
    assert "create_table" in ops
    assert "sync" in ops


# ==================================================================
# Transmutation roundtrips
# ==================================================================

def test_transmute_csv_json_yaml_roundtrip():
    csv_data = "name,age,role\nJeremy,30,Owner\nAlice,25,Engineer"

    # CSV -> JSON
    r1 = DataTransmuter.transmute(csv_data, DataFormat.JSON)
    assert r1.success
    assert "Jeremy" in r1.data

    # JSON -> YAML
    r2 = DataTransmuter.transmute(r1.data, DataFormat.YAML)
    assert r2.success
    assert "Jeremy" in r2.data

    # JSON -> Markdown
    r3 = DataTransmuter.transmute(r1.data, DataFormat.MARKDOWN_TABLE)
    assert r3.success
    assert "| name" in r3.data

    # Markdown -> JSON (back to structured)
    r4 = DataTransmuter.transmute(r3.data, DataFormat.JSON)
    assert r4.success
    assert "Jeremy" in r4.data


def test_schema_extraction_from_csv():
    csv_data = "host,port,status\ndb.local,5432,up\ncache.local,6379,up"
    schema = DataTransmuter.extract_schema(csv_data)
    assert schema["format"] == "csv"
    assert "host" in schema["fields"]
    assert schema["record_count"] == 2


# ==================================================================
# Password management with Vault
# ==================================================================

def test_credential_audit_includes_vault():
    guardian, archivist = _bootstrap()
    archivist.register_credential("github", "PAT", "GITHUB_PAT")
    audit = archivist.credential_audit()
    assert "vault" in audit  # Varys mode pulls vault health
    assert audit["total_credentials"] == 1


def test_credential_discovery():
    guardian, archivist = _bootstrap()
    # Store something in vault that Archivist doesn't know about
    guardian.vault.store("MYSTERY_KEY", "secret123", service="unknown", scope="read")
    archivist.register_credential("github", "PAT", "GITHUB_PAT")

    orphaned = archivist.discover_credentials()
    assert "MYSTERY_KEY" in orphaned
    assert "GITHUB_PAT" not in orphaned  # this one IS tracked


# ==================================================================
# AI briefing (deterministic fallback)
# ==================================================================

def test_ai_briefing_deterministic_fallback():
    _, archivist = _bootstrap()
    archivist.ingest_feed_items([
        FeedItem(source="SEC", title="Data breach at MegaCorp",
                 url="", category=FeedCategory.FINANCIAL),
        FeedItem(source="HN", title="Cool new project",
                 url="", category=FeedCategory.TECH_NEWS),
    ])
    result = archivist.ai_briefing()
    assert "critical" in result.lower() or "unread" in result.lower()


def test_ai_briefing_empty():
    _, archivist = _bootstrap()
    result = archivist.ai_briefing()
    assert result == "No unread intelligence items."
