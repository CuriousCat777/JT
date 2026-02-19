"""Configuration management — loads YAML config and environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass
class AgentConfig:
    """Configuration for a single agent."""
    name: str
    enabled: bool = True
    schedule_interval_minutes: int = 60
    allowed_resources: list[str] = field(default_factory=list)
    custom: dict[str, Any] = field(default_factory=dict)


@dataclass
class SecurityConfig:
    """Security-related settings."""
    encryption_enabled: bool = True
    require_2fa: bool = True
    session_timeout_minutes: int = 30
    max_failed_auth_attempts: int = 5
    audit_all_actions: bool = True


@dataclass
class GuardianConfig:
    """Top-level configuration for the Guardian One system."""
    owner: str = "Jeremy Paulo Salvino Tabernero"
    security: SecurityConfig = field(default_factory=SecurityConfig)
    agents: dict[str, AgentConfig] = field(default_factory=dict)
    data_dir: str = "data"
    log_dir: str = "logs"
    daily_summary_hour: int = 7  # 7 AM local
    timezone: str = "America/Chicago"


def load_config(config_path: Path | None = None) -> GuardianConfig:
    """Load configuration from YAML file, with env-var overrides."""
    load_dotenv()

    config_path = config_path or Path("config/guardian_config.yaml")
    raw: dict[str, Any] = {}

    if config_path.exists():
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}

    security_raw = raw.get("security", {})
    security = SecurityConfig(
        encryption_enabled=security_raw.get("encryption_enabled", True),
        require_2fa=security_raw.get("require_2fa", True),
        session_timeout_minutes=security_raw.get("session_timeout_minutes", 30),
        max_failed_auth_attempts=security_raw.get("max_failed_auth_attempts", 5),
        audit_all_actions=security_raw.get("audit_all_actions", True),
    )

    agents: dict[str, AgentConfig] = {}
    for name, agent_raw in raw.get("agents", {}).items():
        agents[name] = AgentConfig(
            name=name,
            enabled=agent_raw.get("enabled", True),
            schedule_interval_minutes=agent_raw.get("schedule_interval_minutes", 60),
            allowed_resources=agent_raw.get("allowed_resources", []),
            custom=agent_raw.get("custom", {}),
        )

    return GuardianConfig(
        owner=raw.get("owner", "Jeremy Paulo Salvino Tabernero"),
        security=security,
        agents=agents,
        data_dir=os.getenv("GUARDIAN_DATA_DIR", raw.get("data_dir", "data")),
        log_dir=os.getenv("GUARDIAN_LOG_DIR", raw.get("log_dir", "logs")),
        daily_summary_hour=raw.get("daily_summary_hour", 7),
        timezone=raw.get("timezone", "America/Chicago"),
    )
