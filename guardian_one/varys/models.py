"""VARYS data models — SecurityEvent, Alert, Incident.

Uses Elastic Common Schema (ECS) field naming where applicable
for compatibility with Wazuh/OpenSearch pipelines.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AlertSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


class EventCategory(Enum):
    """ECS-aligned event categories."""
    AUTHENTICATION = "authentication"
    PROCESS = "process"
    NETWORK = "network"
    FILE = "file"
    REGISTRY = "registry"
    IAM = "iam"
    WEB = "web"
    MALWARE = "malware"
    INTRUSION_DETECTION = "intrusion_detection"
    CONFIGURATION = "configuration"


@dataclass
class SecurityEvent:
    """A normalized security event from any ingestion source.

    Follows Elastic Common Schema conventions for interoperability.
    """
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source: str = ""              # e.g. "wazuh", "auth_log", "cloudtrail"
    category: str = ""            # ECS category (authentication, process, etc.)
    action: str = ""              # e.g. "login_failed", "process_created"
    outcome: str = ""             # "success", "failure", "unknown"

    # Source/destination context
    source_ip: str = ""
    source_user: str = ""
    destination_ip: str = ""
    destination_port: int = 0

    # Host context
    host_name: str = ""
    host_ip: str = ""
    host_os: str = ""

    # Process context
    process_name: str = ""
    process_command_line: str = ""
    process_pid: int = 0
    parent_process_name: str = ""

    # File context
    file_path: str = ""
    file_hash: str = ""

    # Raw data
    raw: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    # Severity assigned by detection
    severity: str = ""
    rule_id: str = ""


@dataclass
class Alert:
    """A detection-generated alert tied to one or more events."""
    alert_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    title: str = ""
    description: str = ""
    severity: AlertSeverity = AlertSeverity.LOW
    rule_id: str = ""
    rule_name: str = ""
    mitre_tactic: str = ""        # e.g. "TA0001" (Initial Access)
    mitre_technique: str = ""     # e.g. "T1078" (Valid Accounts)

    events: list[SecurityEvent] = field(default_factory=list)
    source_ip: str = ""
    source_user: str = ""
    host_name: str = ""

    # Triage
    triage_result: str = ""       # LLM triage output
    risk_score: float = 0.0       # 0.0–1.0
    acknowledged: bool = False
    false_positive: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "timestamp": self.timestamp,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "mitre_tactic": self.mitre_tactic,
            "mitre_technique": self.mitre_technique,
            "source_ip": self.source_ip,
            "source_user": self.source_user,
            "host_name": self.host_name,
            "risk_score": self.risk_score,
            "triage_result": self.triage_result,
            "acknowledged": self.acknowledged,
            "false_positive": self.false_positive,
            "event_count": len(self.events),
        }


@dataclass
class Incident:
    """A correlated group of alerts representing a security incident."""
    incident_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    title: str = ""
    summary: str = ""
    status: IncidentStatus = IncidentStatus.OPEN
    severity: AlertSeverity = AlertSeverity.LOW

    alerts: list[Alert] = field(default_factory=list)
    affected_hosts: list[str] = field(default_factory=list)
    affected_users: list[str] = field(default_factory=list)

    # Response tracking
    actions_taken: list[str] = field(default_factory=list)
    llm_summary: str = ""
    resolved_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "timestamp": self.timestamp,
            "title": self.title,
            "summary": self.summary,
            "status": self.status.value,
            "severity": self.severity.value,
            "alert_count": len(self.alerts),
            "affected_hosts": self.affected_hosts,
            "affected_users": self.affected_users,
            "actions_taken": self.actions_taken,
            "llm_summary": self.llm_summary,
            "resolved_at": self.resolved_at,
        }
