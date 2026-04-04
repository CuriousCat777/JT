"""Tests for core/config.py — configuration loading and defaults."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from guardian_one.core.config import (
    AgentConfig,
    GuardianConfig,
    SecurityConfig,
    load_config,
)


class TestDataclassDefaults:
    """Verify default values on config dataclasses."""

    def test_agent_config_defaults(self):
        cfg = AgentConfig(name="test")
        assert cfg.name == "test"
        assert cfg.enabled is True
        assert cfg.schedule_interval_minutes == 60
        assert cfg.allowed_resources == []
        assert cfg.custom == {}

    def test_security_config_defaults(self):
        cfg = SecurityConfig()
        assert cfg.encryption_enabled is True
        assert cfg.require_2fa is True
        assert cfg.session_timeout_minutes == 30
        assert cfg.max_failed_auth_attempts == 5
        assert cfg.audit_all_actions is True

    def test_guardian_config_defaults(self):
        cfg = GuardianConfig()
        assert cfg.owner == "Jeremy Paulo Salvino Tabernero"
        assert cfg.timezone == "America/Chicago"
        assert cfg.daily_summary_hour == 7
        assert cfg.data_dir == "data"
        assert cfg.log_dir == "logs"
        assert isinstance(cfg.security, SecurityConfig)
        assert cfg.agents == {}


class TestLoadConfig:
    """Tests for load_config() function."""

    def test_missing_config_file_returns_defaults(self, tmp_path, monkeypatch):
        """When config file doesn't exist, all defaults are used."""
        monkeypatch.delenv("GUARDIAN_DATA_DIR", raising=False)
        monkeypatch.delenv("GUARDIAN_LOG_DIR", raising=False)
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.owner == "Jeremy Paulo Salvino Tabernero"
        assert cfg.timezone == "America/Chicago"
        assert cfg.security.encryption_enabled is True
        assert cfg.agents == {}

    def test_load_from_yaml(self, sample_yaml_config):
        """Load a full YAML config and verify all fields are parsed."""
        cfg = load_config(sample_yaml_config)
        assert cfg.owner == "Test Owner"
        assert cfg.timezone == "America/Chicago"
        assert cfg.daily_summary_hour == 8
        assert cfg.data_dir == "test_data"
        assert cfg.log_dir == "test_logs"

    def test_security_section_parsed(self, sample_yaml_config):
        cfg = load_config(sample_yaml_config)
        assert cfg.security.encryption_enabled is False
        assert cfg.security.require_2fa is False
        assert cfg.security.session_timeout_minutes == 15
        assert cfg.security.max_failed_auth_attempts == 3
        assert cfg.security.audit_all_actions is False

    def test_agents_section_parsed(self, sample_yaml_config):
        cfg = load_config(sample_yaml_config)
        assert "chronos" in cfg.agents
        assert "cfo" in cfg.agents

        chronos = cfg.agents["chronos"]
        assert chronos.name == "chronos"
        assert chronos.enabled is True
        assert chronos.schedule_interval_minutes == 30
        assert "calendar" in chronos.allowed_resources
        assert chronos.custom["wake_alert_minutes_before"] == 15

        cfo = cfg.agents["cfo"]
        assert cfo.enabled is False
        assert cfo.schedule_interval_minutes == 120

    def test_env_var_overrides_data_dir(self, sample_yaml_config):
        """GUARDIAN_DATA_DIR env var takes precedence over YAML."""
        with patch.dict(os.environ, {"GUARDIAN_DATA_DIR": "custom_data"}):
            cfg = load_config(sample_yaml_config)
            assert cfg.data_dir == "custom_data"

    def test_env_var_overrides_log_dir(self, sample_yaml_config):
        """GUARDIAN_LOG_DIR env var takes precedence over YAML."""
        with patch.dict(os.environ, {"GUARDIAN_LOG_DIR": "custom_logs"}):
            cfg = load_config(sample_yaml_config)
            assert cfg.log_dir == "custom_logs"

    def test_empty_yaml_file_returns_defaults(self, tmp_path):
        """An empty YAML file should still produce valid defaults."""
        config_path = tmp_path / "empty.yaml"
        config_path.write_text("")
        cfg = load_config(config_path)
        assert cfg.owner == "Jeremy Paulo Salvino Tabernero"
        assert cfg.agents == {}

    def test_partial_yaml_fills_missing_with_defaults(self, tmp_path):
        """A YAML with only some fields fills in defaults for the rest."""
        config_path = tmp_path / "partial.yaml"
        config_path.write_text('owner: "Custom Owner"\ntimezone: "UTC"\n')
        cfg = load_config(config_path)
        assert cfg.owner == "Custom Owner"
        assert cfg.timezone == "UTC"
        assert cfg.daily_summary_hour == 7  # default
        assert cfg.security.encryption_enabled is True  # default

    def test_agent_with_no_custom_section(self, tmp_path):
        """Agent config without 'custom' key defaults to empty dict."""
        config_path = tmp_path / "minimal_agent.yaml"
        config_path.write_text("""\
agents:
  simple:
    enabled: true
""")
        cfg = load_config(config_path)
        assert "simple" in cfg.agents
        assert cfg.agents["simple"].custom == {}
        assert cfg.agents["simple"].allowed_resources == []
