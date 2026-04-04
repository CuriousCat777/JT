"""Archivist — Central Telemetry & Data Sovereignty Agent.

The Archivist is the librarian and manifestation of memory for Guardian One.
It is the central nervous system that remembers, logs, and protects all data
across every system, service, and account.

Responsibilities:
- Central telemetry: log all interactions across all systems
- Tech detection: auto-detect new technology/services entering the ecosystem
- Cloud sync: multi-cloud backup portals to online copies
- File management: searchable index with retention policies
- Privacy audit: encryption, VPN, data broker removal
- Vault integration: auto-backup new interactions to encrypted storage
- Persistence: all state survives restarts via JSON on disk
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig

from guardian_one.archivist.telemetry import TelemetryHub, TelemetryEvent
from guardian_one.archivist.techdetect import TechDetector
from guardian_one.archivist.cloudsync import CloudSync


class RetentionPolicy(Enum):
    KEEP_FOREVER = "keep_forever"
    KEEP_1_YEAR = "keep_1_year"
    KEEP_3_YEARS = "keep_3_years"
    KEEP_7_YEARS = "keep_7_years"  # Tax / legal
    DELETE_AFTER_USE = "delete_after_use"


@dataclass
class FileRecord:
    """Metadata for a tracked file."""
    path: str
    category: str        # medical, financial, personal, professional, legal
    tags: list[str] = field(default_factory=list)
    retention: RetentionPolicy = RetentionPolicy.KEEP_3_YEARS
    encrypted: bool = False
    last_accessed: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    created: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class DataSource:
    """A connected data source (gadget, app, service)."""
    name: str
    source_type: str   # smartwatch, vpn, privacy_service, app
    data_types: list[str] = field(default_factory=list)
    sync_enabled: bool = False
    last_sync: str | None = None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class PrivacyTool:
    """Configuration for a privacy/security tool."""
    name: str
    tool_type: str   # vpn, data_broker_removal, password_manager, encryption
    active: bool = True
    config: dict[str, Any] = field(default_factory=dict)
    last_check: str | None = None


class Archivist(BaseAgent):
    """Central telemetry & data sovereignty agent.

    The Archivist is three systems in one:
    1. TelemetryHub — central cross-system event logging
    2. TechDetector — auto-detect new technology entering the ecosystem
    3. CloudSync — multi-cloud backup portals

    Plus the original capabilities:
    - File indexing with retention policies
    - Privacy audit (encryption, VPN, data broker removal)
    - Master profile (autofill data)
    """

    def __init__(self, config: AgentConfig, audit: AuditLog) -> None:
        super().__init__(config, audit)
        self._file_index: dict[str, FileRecord] = {}
        self._data_sources: dict[str, DataSource] = {}
        self._privacy_tools: dict[str, PrivacyTool] = {}
        self._master_profile: dict[str, Any] = {}
        self._backup_schedule: dict[str, str] = {}

        # Data directory for persistence
        data_dir = Path(config.custom.get("data_dir", "data")) if config.custom else Path("data")

        # New subsystems
        self.telemetry = TelemetryHub(data_dir=data_dir)
        self.tech_detector = TechDetector(data_dir=data_dir)
        self.cloud_sync = CloudSync(data_dir=data_dir)

        # Persistence path
        self._state_file = data_dir / "archivist_state.json"

    def initialize(self) -> None:
        self._set_status(AgentStatus.IDLE)
        self._setup_default_sources()
        self._setup_privacy_tools()
        self._setup_file_categories()
        self.cloud_sync.setup_defaults()

        # Load persisted state
        self._load_state()
        self.telemetry.load_from_disk()
        self.tech_detector.load()
        self.cloud_sync.load_config()

        # Register self in telemetry
        self.telemetry.log_simple(
            source="archivist",
            source_type="agent",
            category="config_change",
            action="initialized",
            actor="guardian_one",
            details={
                "sources": len(self._data_sources),
                "privacy_tools": len(self._privacy_tools),
                "files_tracked": len(self._file_index),
            },
        )

        self.log("initialized", details={
            "sources": len(self._data_sources),
            "privacy_tools": len(self._privacy_tools),
            "telemetry_events": self.telemetry.total_logged,
            "tech_tracked": len(self.tech_detector.registry),
        })

    def _setup_default_sources(self) -> None:
        self._data_sources = {
            "smartwatch": DataSource(
                name="Smartwatch",
                source_type="smartwatch",
                data_types=["heart_rate", "steps", "sleep", "stress"],
            ),
            "nordvpn": DataSource(
                name="NordVPN",
                source_type="vpn",
                data_types=["connection_log", "bandwidth"],
            ),
            "deleteme": DataSource(
                name="DeleteMe",
                source_type="privacy_service",
                data_types=["broker_removal_status", "exposure_report"],
            ),
        }

    def _setup_privacy_tools(self) -> None:
        self._privacy_tools = {
            "nordvpn": PrivacyTool(
                name="NordVPN",
                tool_type="vpn",
                config={"auto_connect": True, "kill_switch": True, "protocol": "NordLynx"},
            ),
            "deleteme": PrivacyTool(
                name="DeleteMe",
                tool_type="data_broker_removal",
                config={"scan_frequency": "quarterly", "auto_remove": True},
            ),
        }

    def _setup_file_categories(self) -> None:
        self._backup_schedule = {
            "medical": "weekly",
            "financial": "daily",
            "personal": "weekly",
            "professional": "daily",
            "legal": "monthly",
        }

    # ------------------------------------------------------------------
    # Telemetry integration — all systems feed here
    # ------------------------------------------------------------------

    def record_interaction(
        self,
        source: str,
        action: str,
        *,
        source_type: str = "service",
        category: str = "interaction",
        actor: str = "",
        target: str = "",
        details: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Record a cross-system interaction.

        This is the primary entry point for all other agents and
        integrations to log activity into the central telemetry.
        """
        # Log to telemetry
        self.telemetry.log_simple(
            source=source,
            source_type=source_type,
            category=category,
            action=action,
            actor=actor,
            target=target,
            details=details,
            tags=tags,
        )

        # Check if this is new tech
        new_tech = self.tech_detector.check(
            source=source,
            source_type=source_type,
            action=action,
            details=details,
        )

        if new_tech:
            self.log(
                "new_tech_detected",
                severity=Severity.INFO,
                details=new_tech.to_dict(),
                requires_review=True,
            )
            # Auto-save tech registry on new detection
            self.tech_detector.save()

    # ------------------------------------------------------------------
    # File management
    # ------------------------------------------------------------------

    def register_file(self, record: FileRecord) -> None:
        self._file_index[record.path] = record
        self.log("file_registered", details={"path": record.path, "category": record.category})
        # Log to telemetry
        self.telemetry.log_simple(
            source="archivist",
            source_type="agent",
            category="interaction",
            action="file_registered",
            target=record.path,
            details={"category": record.category, "encrypted": record.encrypted},
        )

    def search_files(
        self,
        query: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
    ) -> list[FileRecord]:
        results = list(self._file_index.values())
        if category:
            results = [f for f in results if f.category == category]
        if tags:
            tag_set = set(tags)
            results = [f for f in results if tag_set.intersection(f.tags)]
        if query:
            q = query.lower()
            results = [f for f in results if q in f.path.lower() or any(q in t.lower() for t in f.tags)]
        return results

    def files_due_for_deletion(self) -> list[FileRecord]:
        now = datetime.now(timezone.utc)
        due: list[FileRecord] = []
        retention_days = {
            RetentionPolicy.DELETE_AFTER_USE: 0,
            RetentionPolicy.KEEP_1_YEAR: 365,
            RetentionPolicy.KEEP_3_YEARS: 1095,
            RetentionPolicy.KEEP_7_YEARS: 2555,
            RetentionPolicy.KEEP_FOREVER: None,
        }
        for record in self._file_index.values():
            max_days = retention_days.get(record.retention)
            if max_days is None:
                continue
            try:
                created_dt = datetime.fromisoformat(record.created)
            except (ValueError, TypeError):
                self.log(
                    "invalid_file_timestamp",
                    severity=Severity.WARNING,
                    details={"path": record.path, "timestamp": record.created},
                )
                continue
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            age = (now - created_dt).days
            if age > max_days:
                due.append(record)
        return due

    # ------------------------------------------------------------------
    # Master profile (autofill data)
    # ------------------------------------------------------------------

    def set_profile_field(self, key: str, value: Any) -> None:
        self._master_profile[key] = value
        self.log("profile_updated", details={"field": key})

    def get_profile(self) -> dict[str, Any]:
        return dict(self._master_profile)

    # ------------------------------------------------------------------
    # Data source management
    # ------------------------------------------------------------------

    def sync_source(self, name: str) -> dict[str, Any]:
        source = self._data_sources.get(name)
        if source is None:
            return {"error": f"Unknown source: {name}"}
        source.last_sync = datetime.now(timezone.utc).isoformat()
        self.log("source_synced", details={"source": name})
        # Track in telemetry
        self.record_interaction(
            source=name,
            source_type=source.source_type,
            action="data_sync",
            actor="archivist",
            details={"data_types": source.data_types},
        )
        return {"source": name, "synced_at": source.last_sync, "data_types": source.data_types}

    # ------------------------------------------------------------------
    # Privacy audit
    # ------------------------------------------------------------------

    def privacy_audit(self) -> dict[str, Any]:
        issues: list[str] = []
        recommendations: list[str] = []

        for name, tool in self._privacy_tools.items():
            if not tool.active:
                issues.append(f"{name} is inactive.")
            if tool.tool_type == "vpn" and not tool.config.get("kill_switch"):
                recommendations.append(f"Enable kill switch on {name}.")

        unencrypted = [
            f for f in self._file_index.values()
            if not f.encrypted and f.category in ("financial", "medical", "legal")
        ]
        if unencrypted:
            issues.append(f"{len(unencrypted)} sensitive files are not encrypted.")
            recommendations.append("Encrypt all financial, medical and legal files.")

        # Check for unreviewed tech
        unreviewed = self.tech_detector.get_unreviewed()
        if unreviewed:
            recommendations.append(
                f"{len(unreviewed)} new technologies detected — review and approve."
            )

        # Check for unbacked-up tech
        unbacked = self.tech_detector.get_unbacked_up()
        if unbacked:
            recommendations.append(
                f"{len(unbacked)} technology records not yet backed up to Vault."
            )

        return {
            "issues": issues,
            "recommendations": recommendations,
            "tools_active": sum(1 for t in self._privacy_tools.values() if t.active),
            "tools_total": len(self._privacy_tools),
        }

    # ------------------------------------------------------------------
    # Persistence — survive restarts
    # ------------------------------------------------------------------

    def _save_state(self) -> None:
        """Persist all Archivist state to disk."""
        state = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "file_index": {
                path: {
                    "path": r.path,
                    "category": r.category,
                    "tags": r.tags,
                    "retention": r.retention.value,
                    "encrypted": r.encrypted,
                    "last_accessed": r.last_accessed,
                    "created": r.created,
                }
                for path, r in self._file_index.items()
            },
            "master_profile": self._master_profile,
        }
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_file, "w") as f:
                json.dump(state, f, indent=2)
        except OSError as exc:
            self.log("state_save_failed", severity=Severity.ERROR, details={"error": str(exc)})

    def _load_state(self) -> None:
        """Load persisted state from disk."""
        if not self._state_file.exists():
            return
        try:
            with open(self._state_file) as f:
                state = json.load(f)

            # Restore file index
            retention_map = {p.value: p for p in RetentionPolicy}
            for path, data in state.get("file_index", {}).items():
                self._file_index[path] = FileRecord(
                    path=data["path"],
                    category=data["category"],
                    tags=data.get("tags", []),
                    retention=retention_map.get(data.get("retention", ""), RetentionPolicy.KEEP_3_YEARS),
                    encrypted=data.get("encrypted", False),
                    last_accessed=data.get("last_accessed", ""),
                    created=data.get("created", ""),
                )

            # Restore master profile
            self._master_profile = state.get("master_profile", {})

        except (OSError, json.JSONDecodeError, TypeError) as exc:
            self.log("state_load_failed", severity=Severity.WARNING, details={"error": str(exc)})

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def run(self) -> AgentReport:
        self._set_status(AgentStatus.RUNNING)
        alerts: list[str] = []
        recommendations: list[str] = []
        actions: list[str] = []

        # Check retention
        due = self.files_due_for_deletion()
        if due:
            alerts.append(f"{len(due)} files past retention policy — review and delete.")

        # Privacy audit
        privacy = self.privacy_audit()
        alerts.extend(privacy.get("issues", []))
        recommendations.extend(privacy.get("recommendations", []))
        actions.append("Ran privacy audit.")

        # Check for new tech detections
        new_tech = self.tech_detector.new_detections
        if new_tech:
            for tech in new_tech:
                alerts.append(f"New tech detected: {tech.name} ({tech.tech_type})")
            actions.append(f"Detected {len(new_tech)} new technologies.")

        # Persist state
        self._save_state()
        self.tech_detector.save()
        self.cloud_sync.save_config()
        actions.append("State persisted to disk.")

        self._set_status(AgentStatus.IDLE)
        return AgentReport(
            agent_name=self.name,
            status=AgentStatus.IDLE.value,
            summary=(
                f"Tracking {len(self._file_index)} files, "
                f"{len(self._data_sources)} sources, "
                f"{self.telemetry.total_logged} telemetry events, "
                f"{len(self.tech_detector.registry)} technologies."
            ),
            actions_taken=actions,
            recommendations=recommendations,
            alerts=alerts,
            data={
                "files": len(self._file_index),
                "sources": len(self._data_sources),
                "privacy": privacy,
                "telemetry": self.telemetry.status(),
                "tech_detector": self.tech_detector.status(),
                "cloud_sync": self.cloud_sync.status(),
            },
        )

    def report(self) -> AgentReport:
        return AgentReport(
            agent_name=self.name,
            status=self.status.value,
            summary=(
                f"Managing {len(self._file_index)} files, "
                f"{len(self._data_sources)} sources, "
                f"{len(self._privacy_tools)} privacy tools, "
                f"{self.telemetry.total_logged} telemetry events."
            ),
            data={
                "files": len(self._file_index),
                "sources": list(self._data_sources.keys()),
                "privacy_tools": list(self._privacy_tools.keys()),
                "profile_fields": len(self._master_profile),
                "telemetry": self.telemetry.status(),
                "tech_detector": self.tech_detector.status(),
                "cloud_sync": self.cloud_sync.status(),
            },
        )

    def shutdown(self) -> None:
        """Persist all state before shutdown."""
        self._save_state()
        self.tech_detector.save()
        self.cloud_sync.save_config()
        super().shutdown()
