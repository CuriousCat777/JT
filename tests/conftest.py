"""Shared pytest fixtures for Guardian One test suite."""

from pathlib import Path

import pytest

from guardian_one.core.audit import AuditLog
from guardian_one.core.config import AgentConfig, GuardianConfig, SecurityConfig


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temporary directory (pytest built-in, cleaner than tempfile)."""
    return tmp_path


@pytest.fixture
def audit_log(tmp_path):
    """Fresh AuditLog writing to a temporary directory."""
    return AuditLog(log_dir=tmp_path / "audit")


@pytest.fixture
def agent_config():
    """Minimal AgentConfig for testing."""
    def _make(name="test_agent", **kwargs):
        return AgentConfig(name=name, **kwargs)
    return _make


@pytest.fixture
def guardian_config():
    """Default GuardianConfig for testing."""
    return GuardianConfig(
        owner="Test Owner",
        security=SecurityConfig(),
        agents={},
        data_dir="data",
        log_dir="logs",
    )


@pytest.fixture
def sample_yaml_config(tmp_path):
    """Write a sample YAML config file and return its path."""
    config_path = tmp_path / "guardian_config.yaml"
    config_path.write_text("""\
owner: "Test Owner"
timezone: "America/Chicago"
daily_summary_hour: 8
data_dir: "test_data"
log_dir: "test_logs"

security:
  encryption_enabled: false
  require_2fa: false
  session_timeout_minutes: 15
  max_failed_auth_attempts: 3
  audit_all_actions: false

agents:
  chronos:
    enabled: true
    schedule_interval_minutes: 30
    allowed_resources:
      - calendar
      - sleep_data
    custom:
      wake_alert_minutes_before: 15
  cfo:
    enabled: false
    schedule_interval_minutes: 120
    allowed_resources:
      - accounts
""")
    return config_path
