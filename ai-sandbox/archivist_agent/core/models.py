"""Standalone data models for the Archivist agent.

No Guardian One dependencies — fully self-contained.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class RetentionPolicy(Enum):
    KEEP_FOREVER = "keep_forever"
    KEEP_1_YEAR = "keep_1_year"
    KEEP_3_YEARS = "keep_3_years"
    KEEP_7_YEARS = "keep_7_years"
    DELETE_AFTER_USE = "delete_after_use"


@dataclass
class FileRecord:
    path: str
    category: str  # medical, financial, personal, professional, legal
    tags: list[str] = field(default_factory=list)
    retention: RetentionPolicy = RetentionPolicy.KEEP_3_YEARS
    encrypted: bool = False
    last_accessed: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    created: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "category": self.category,
            "tags": self.tags,
            "retention": self.retention.value,
            "encrypted": self.encrypted,
            "last_accessed": self.last_accessed,
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileRecord:
        return cls(
            path=data["path"],
            category=data["category"],
            tags=data.get("tags", []),
            retention=RetentionPolicy(data.get("retention", "keep_3_years")),
            encrypted=data.get("encrypted", False),
            last_accessed=data.get("last_accessed", datetime.now(timezone.utc).isoformat()),
            created=data.get("created", datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class DataSource:
    name: str
    source_type: str  # smartwatch, vpn, privacy_service, app
    data_types: list[str] = field(default_factory=list)
    sync_enabled: bool = False
    last_sync: str | None = None
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source_type": self.source_type,
            "data_types": self.data_types,
            "sync_enabled": self.sync_enabled,
            "last_sync": self.last_sync,
            "config": self.config,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DataSource:
        return cls(
            name=data["name"],
            source_type=data["source_type"],
            data_types=data.get("data_types", []),
            sync_enabled=data.get("sync_enabled", False),
            last_sync=data.get("last_sync"),
            config=data.get("config", {}),
        )


@dataclass
class PrivacyTool:
    name: str
    tool_type: str  # vpn, data_broker_removal, password_manager, encryption
    active: bool = True
    config: dict[str, Any] = field(default_factory=dict)
    last_check: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tool_type": self.tool_type,
            "active": self.active,
            "config": self.config,
            "last_check": self.last_check,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PrivacyTool:
        return cls(
            name=data["name"],
            tool_type=data["tool_type"],
            active=data.get("active", True),
            config=data.get("config", {}),
            last_check=data.get("last_check"),
        )


@dataclass
class AuditEntry:
    timestamp: str
    action: str
    details: dict[str, Any] = field(default_factory=dict)
    severity: str = "info"

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "details": self.details,
            "severity": self.severity,
        }
