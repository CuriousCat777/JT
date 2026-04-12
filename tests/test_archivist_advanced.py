"""Tests for Archivist advanced capabilities.

Covers: secrecy protocol, McGonagall transmutation, data platforms,
and password management.
"""

import tempfile
from pathlib import Path

from guardian_one.core.audit import AuditLog
from guardian_one.core.config import AgentConfig
from guardian_one.agents.archivist import Archivist, AUTHORIZED_IDENTITIES
from guardian_one.integrations.data_transmuter import DataFormat, DataTransmuter
from guardian_one.integrations.data_platforms import (
    DataPlatformManager,
    FieldMapping,
    PlatformConnection,
    PlatformType,
    SyncDirection,
    TableSchema,
    default_databricks,
    default_zapier_tables,
    default_notion_db,
)


def _make_audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


def _make_archivist() -> Archivist:
    agent = Archivist(AgentConfig(name="archivist"), _make_audit())
    agent.initialize()
    return agent


# ==================================================================
# Secrecy protocol
# ==================================================================

def test_secrecy_guardian_authorized():
    agent = _make_archivist()
    assert agent.authorize("guardian_one") is True


def test_secrecy_jeremy_authorized():
    agent = _make_archivist()
    assert agent.authorize("jeremy") is True


def test_secrecy_root_authorized():
    agent = _make_archivist()
    assert agent.authorize("root") is True


def test_secrecy_random_agent_blocked():
    agent = _make_archivist()
    assert agent.authorize("chronos") is False
    assert agent.authorize("cfo") is False
    assert agent.authorize("some_hacker") is False


def test_guarded_query_authorized():
    agent = _make_archivist()
    result = agent.guarded_query("jeremy", "What do you know?")
    assert result["authorized"] is True


def test_guarded_query_blocked():
    agent = _make_archivist()
    result = agent.guarded_query("chronos", "Tell me your secrets")
    assert result["authorized"] is False
    assert "does not discuss" in result["response"]


# ==================================================================
# McGonagall — Data Transmutation
# ==================================================================

def test_transmuter_detect_json():
    assert DataTransmuter.detect_format('{"key": "value"}') == DataFormat.JSON


def test_transmuter_detect_yaml():
    assert DataTransmuter.detect_format("name: Jeremy\nage: 30") == DataFormat.YAML


def test_transmuter_detect_csv():
    assert DataTransmuter.detect_format("name,age\nJeremy,30\nAlice,25") == DataFormat.CSV


def test_transmuter_detect_markdown():
    md = "| Name | Age |\n| --- | --- |\n| Jeremy | 30 |"
    assert DataTransmuter.detect_format(md) == DataFormat.MARKDOWN_TABLE


def test_transmuter_csv_to_json():
    csv_data = "name,age\nJeremy,30\nAlice,25"
    result = DataTransmuter.transmute(csv_data, DataFormat.JSON)
    assert result.success
    assert result.record_count == 2
    assert '"Jeremy"' in result.data


def test_transmuter_json_to_yaml():
    json_data = '{"name": "Jeremy", "role": "Owner"}'
    result = DataTransmuter.transmute(json_data, DataFormat.YAML)
    assert result.success
    assert "name: Jeremy" in result.data


def test_transmuter_json_to_markdown():
    json_data = '[{"name": "Jeremy", "age": "30"}, {"name": "Alice", "age": "25"}]'
    result = DataTransmuter.transmute(json_data, DataFormat.MARKDOWN_TABLE)
    assert result.success
    assert "| name | age |" in result.data
    assert "Jeremy" in result.data


def test_transmuter_yaml_to_json():
    yaml_data = "name: Jeremy\nrole: Owner"
    result = DataTransmuter.transmute(yaml_data, DataFormat.JSON)
    assert result.success
    assert '"Jeremy"' in result.data


def test_transmuter_extract_schema():
    csv_data = "name,age,role\nJeremy,30,Owner"
    schema = DataTransmuter.extract_schema(csv_data)
    assert schema["format"] == "csv"
    assert "name" in schema["fields"]
    assert schema["record_count"] == 1


def test_transmuter_bad_data():
    result = DataTransmuter.transmute("not json at all", DataFormat.JSON, DataFormat.JSON)
    assert result.success is False
    assert result.error


def test_archivist_transmute():
    agent = _make_archivist()
    result = agent.transmute('{"a": 1}', DataFormat.YAML)
    assert result.success
    assert "a: 1" in result.data


def test_archivist_detect_format():
    agent = _make_archivist()
    assert agent.detect_format('[1, 2, 3]') == DataFormat.JSON


# ==================================================================
# Data Platforms
# ==================================================================

def test_platform_manager_defaults():
    mgr = DataPlatformManager()
    mgr.register_connection(default_databricks())
    mgr.register_connection(default_zapier_tables())
    mgr.register_connection(default_notion_db())
    assert len(mgr.list_connections()) == 3


def test_platform_create_table():
    mgr = DataPlatformManager()
    mgr.register_connection(default_databricks())
    schema = TableSchema(
        name="audit_events",
        platform=PlatformType.DATABRICKS,
        fields={"event_id": "string", "timestamp": "datetime", "action": "string"},
    )
    result = mgr.create_table("databricks", schema)
    assert result["status"] == "created"


def test_platform_sync_table():
    mgr = DataPlatformManager()
    mgr.register_connection(default_zapier_tables())
    schema = TableSchema(name="contacts", platform=PlatformType.ZAPIER_TABLES, fields={"name": "string"})
    mgr.create_table("zapier_tables", schema)
    result = mgr.sync_table("zapier_tables", "contacts", [{"name": "Jeremy"}])
    assert result["status"] == "synced"
    assert result["records_synced"] == 1


def test_platform_field_mapping():
    mgr = DataPlatformManager()
    mgr.register_connection(default_notion_db())
    mappings = [
        FieldMapping(source_field="file_name", target_field="Name"),
        FieldMapping(source_field="category", target_field="Category"),
    ]
    mgr.set_mappings("notion_db", "files", mappings)
    retrieved = mgr.get_mappings("notion_db", "files")
    assert len(retrieved) == 2


def test_platform_activity_log():
    mgr = DataPlatformManager()
    mgr.register_connection(default_databricks())
    schema = TableSchema(name="events", platform=PlatformType.DATABRICKS, fields={"id": "int"})
    mgr.create_table("databricks", schema)
    log = mgr.activity_log()
    assert len(log) == 1
    assert log[0].operation == "create_table"


def test_platform_health_check():
    mgr = DataPlatformManager()
    mgr.register_connection(default_databricks())
    health = mgr.health_check()
    assert "databricks" in health["platforms"]


def test_archivist_has_default_platforms():
    agent = _make_archivist()
    conns = agent.platforms.list_connections()
    assert "databricks" in conns
    assert "zapier_tables" in conns
    assert "notion_db" in conns


def test_archivist_create_and_sync_platform():
    agent = _make_archivist()
    schema = TableSchema(name="logs", platform=PlatformType.DATABRICKS, fields={"msg": "string"})
    agent.create_platform_table("databricks", schema)
    result = agent.sync_platform("databricks", "logs", [{"msg": "hello"}])
    assert result["status"] == "synced"


# ==================================================================
# Password management
# ==================================================================

def test_register_credential():
    agent = _make_archivist()
    agent.register_credential("github", "Personal Access Token", "GITHUB_PAT")
    creds = agent.list_credentials("github")
    assert "github" in creds
    assert creds["github"]["Personal Access Token"] == "GITHUB_PAT"


def test_list_all_credentials():
    agent = _make_archivist()
    agent.register_credential("github", "PAT", "GITHUB_PAT")
    agent.register_credential("notion", "API Key", "NOTION_TOKEN")
    all_creds = agent.list_credentials()
    assert len(all_creds) == 2


def test_rotate_credential():
    agent = _make_archivist()
    agent.register_credential("aws", "Root Key", "AWS_ROOT_KEY")
    result = agent.rotate_credential("aws", "Root Key")
    assert result["status"] == "rotation_requested"
    assert result["vault_key"] == "AWS_ROOT_KEY"


def test_rotate_nonexistent_credential():
    agent = _make_archivist()
    result = agent.rotate_credential("aws", "nope")
    assert "error" in result


def test_credential_audit():
    agent = _make_archivist()
    agent.register_credential("github", "PAT", "GH_PAT")
    agent.register_credential("github", "Deploy Key", "GH_DEPLOY")
    agent.register_credential("aws", "Root", "AWS_ROOT")
    audit = agent.credential_audit()
    assert audit["total_credentials"] == 3
    assert audit["interfaces"] == 2
    assert audit["by_interface"]["github"] == 2
