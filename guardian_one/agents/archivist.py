"""Archivist — Chief of Staff for Libraries & File Organisation.

Prime Directive:
    Jeremy's digital life generates data across dozens of sources — medical records,
    financial docs, smartwatch telemetry, legal papers, professional credentials.
    The Archivist is the single authority that decides where every byte lives,
    how long it stays, who can touch it, and when it gets destroyed.

    Think of it like a library's head librarian crossed with a shredder operator:
    everything gets catalogued, indexed, and retention-tagged on arrival.
    Sensitive files get encrypted at rest. Expired files get flagged for deletion.
    Nothing leaves without passing the content gate.

Core Responsibilities:
    1. FILE TAXONOMY    — Organise all files into a searchable, category-tagged index
    2. MASTER PROFILE   — Maintain Jeremy's autofill data (single source of truth)
    3. DATA SOURCES     — Map and sync from gadgets/apps (smartwatch, NordVPN, DeleteMe)
    4. RETENTION ENGINE — Enforce time-based retention policies (delete-after-use → 7yr legal hold)
    5. PRIVACY POSTURE  — Audit encryption gaps, VPN config, data-broker removal status
    6. BACKUP CADENCE   — Schedule backups by category (financial=daily, legal=monthly)
    7. PALANTÍR         — Strategic intelligence feeds (RSS, AI blogs, GitHub, finance)
                          15-min refresh, priority-scored, CIO-level briefings

Credential Access:
    All secrets via homelink/vault.py. No caching. No hardcoding. No exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig
from guardian_one.integrations.data_platforms import (
    DataPlatformManager,
    FieldMapping,
    PlatformConnection,
    TableSchema,
    default_databricks,
    default_notion_db,
    default_zapier_tables,
)
from guardian_one.integrations.data_transmuter import DataFormat, DataTransmuter, TransmutationResult
from guardian_one.integrations.intelligence_feeds import (
    FeedCategory,
    FeedItem,
    FeedPriority,
    IntelligencePipeline,
)

# Secrecy protocol — only these identities may query the Archivist's
# capabilities, internal state, or knowledge. Everyone else gets a
# polite refusal. Varys didn't survive King's Landing by talking.
AUTHORIZED_IDENTITIES = frozenset({"guardian_one", "jeremy", "root"})


class RetentionPolicy(Enum):
    KEEP_FOREVER = "keep_forever"
    KEEP_1_YEAR = "keep_1_year"
    KEEP_3_YEARS = "keep_3_years"
    KEEP_7_YEARS = "keep_7_years"  # Tax / legal
    DELETE_AFTER_USE = "delete_after_use"


class BackupStatus(Enum):
    OK = "ok"
    STALE = "stale"       # Past its expected schedule
    MISSING = "missing"   # Never backed up
    FAILED = "failed"     # Last backup attempt failed
    VERIFIED = "verified" # Backup verified intact


class DevicePlatform(Enum):
    LINUX = "linux"
    MACOS = "macos"
    WINDOWS = "windows"


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


@dataclass
class DeviceRecord:
    """A registered device in the multi-device backup network."""
    device_id: str           # Unique key: "linux_primary", "macos_macbook", "windows_rog_x"
    name: str                # Human name: "Linux Primary", "MacBook", "ASUS ROG X"
    platform: DevicePlatform
    hostname: str = ""
    priority: int = 0        # Lower = higher priority (Linux=0, macOS=1, Windows=2)
    storage_path: str = ""   # Root path for backups on this device
    last_seen: str | None = None
    online: bool = False
    specs: dict[str, Any] = field(default_factory=dict)


@dataclass
class BackupRecord:
    """Tracks a database or file backup."""
    name: str                # e.g. "cfo_ledger", "vault", "guardian_config"
    source_path: str         # Original file/database path
    backup_path: str         # Where the backup is stored
    category: str            # financial, config, credentials, system
    schedule: str            # daily, weekly, monthly
    device: str = ""         # Device ID this backup belongs to (empty = current)
    last_backup: str | None = None
    last_verified: str | None = None
    backup_status: BackupStatus = BackupStatus.MISSING
    size_bytes: int = 0
    checksum: str = ""       # SHA-256 of the backup file
    retention: RetentionPolicy = RetentionPolicy.KEEP_3_YEARS
    history: list[dict[str, Any]] = field(default_factory=list)


class Archivist(BaseAgent):
    """Chief of Staff for libraries, file organisation, and data sovereignty.

    The Archivist owns every file, every data source, every retention clock,
    every intelligence feed, and every cross-platform data pipeline.

    Capabilities:
    - McGonagall-level data transmutation (any format in, any format out)
    - Varys-level cross-agent intelligence (reads all agent domains)
    - Palantír strategic feed monitoring (15-min cycle)
    - Databricks / Zapier Tables / Notion DB integration
    - Password management across all interfaces via Vault

    Secrecy Protocol:
    - ONLY guardian_one, jeremy, and root may query the Archivist's
      capabilities, internal state, or knowledge.
    - All other identities receive a refusal.
    """

    # Platform priority: Linux (0) > Windows (1) > macOS (2)
    # Linux is the sovereign primary — all backups consolidate here.
    PLATFORM_PRIORITY = {
        DevicePlatform.LINUX: 0,
        DevicePlatform.WINDOWS: 1,
        DevicePlatform.MACOS: 2,
    }

    def __init__(self, config: AgentConfig, audit: AuditLog) -> None:
        super().__init__(config, audit)
        self._file_index: dict[str, FileRecord] = {}
        self._data_sources: dict[str, DataSource] = {}
        self._privacy_tools: dict[str, PrivacyTool] = {}
        self._master_profile: dict[str, Any] = {}
        self._backup_schedule: dict[str, str] = {}
        self._backups: dict[str, BackupRecord] = {}
        self._devices: dict[str, DeviceRecord] = {}
        self._power_tools: Any | None = None  # PowerToolsLibrary, injected by Guardian
        self._guardian: Any = None  # Injected post-registration for Varys mode
        self._palantir = IntelligencePipeline()  # Strategic intelligence feeds
        self._transmuter = DataTransmuter()  # McGonagall-level data transformation
        self._platforms = DataPlatformManager()  # Databricks, Zapier, Notion
        self._password_store: dict[str, dict[str, str]] = {}  # interface → {label → vault_key}

    def initialize(self) -> None:
        self._set_status(AgentStatus.IDLE)
        self._setup_default_sources()
        self._setup_privacy_tools()
        self._setup_file_categories()
        self._setup_default_platforms()
        self._setup_devices()
        self._setup_default_backups()
        self.log("initialized", details={
            "sources": len(self._data_sources),
            "privacy_tools": len(self._privacy_tools),
            "platforms": len(self._platforms.list_connections()),
            "devices": len(self._devices),
            "backups_tracked": len(self._backups),
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

    def set_power_tools(self, library: Any) -> None:
        """Inject the PowerToolsLibrary (called by GuardianOne after boot)."""
        self._power_tools = library
        self.log("power_tools_attached", details={"library": type(library).__name__})

    @property
    def power_tools(self) -> Any | None:
        """Access the PowerToolsLibrary managed by this agent."""
        return self._power_tools

    def power_tools_status(self) -> dict[str, Any]:
        """Return power tools status from the managed library."""
        if self._power_tools is None:
            return {"error": "Power tools library not attached"}
        return self._power_tools.status(requester=self.name)

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
        """Define the standard file organisation taxonomy."""
        self._backup_schedule = {
            "medical": "weekly",
            "financial": "daily",
            "personal": "weekly",
            "professional": "daily",
            "legal": "monthly",
        }

    def _setup_default_platforms(self) -> None:
        """Register default data platform connections."""
        self._platforms.register_connection(default_databricks())
        self._platforms.register_connection(default_zapier_tables())
        self._platforms.register_connection(default_notion_db())

    def _setup_devices(self) -> None:
        """Register all devices in the multi-device backup network.

        Priority order: Linux (0) > Windows (1) > macOS (2)
        Linux is the sovereign primary — the consolidation target for
        all cross-device backups.
        """
        self._devices = {
            "linux_primary": DeviceRecord(
                device_id="linux_primary",
                name="Linux Primary",
                platform=DevicePlatform.LINUX,
                priority=0,
                storage_path="/home/user/JT/data/backups",
                specs={
                    "role": "sovereign_primary",
                    "description": "Primary development and backup consolidation server",
                },
            ),
            "windows_rog_x": DeviceRecord(
                device_id="windows_rog_x",
                name="ASUS ROG X",
                platform=DevicePlatform.WINDOWS,
                priority=1,
                storage_path="C:\\Users\\Jeremy\\JT\\data\\backups",
                specs={
                    "role": "power_workstation",
                    "ram_gb": 64,
                    "description": "ASUS ROG X 64GB — AI training, heavy compute",
                    "features": ["wsl2", "ollama_local", "gpu_compute"],
                    "archivist_duties": [
                        "file_system_integrity",
                        "data_sovereignty_enforcement",
                        "backup_verification",
                        "claude_md_stewardship",
                        "audit_trail",
                    ],
                },
            ),
            "macos_macbook": DeviceRecord(
                device_id="macos_macbook",
                name="MacBook",
                platform=DevicePlatform.MACOS,
                priority=2,
                storage_path="~/JT/data/backups",
                specs={
                    "role": "mobile_workstation",
                    "description": "macOS laptop — iMessage, Xcode, mobile dev",
                    "features": ["imessage", "keychain", "time_machine"],
                },
            ),
        }

    def _setup_default_backups(self) -> None:
        """Register per-device backup targets for all critical files.

        Organization: Linux on top (consolidation target), then
        Windows ROG X, then macOS.  Every device's critical data
        backs up to the Linux primary.
        """
        defaults = [
            # -- Linux Primary (sovereign hub) --
            BackupRecord(
                name="linux:cfo_ledger",
                source_path="data/cfo_ledger.json",
                backup_path="data/backups/linux/cfo_ledger",
                category="financial",
                schedule="daily",
                device="linux_primary",
                retention=RetentionPolicy.KEEP_7_YEARS,
            ),
            BackupRecord(
                name="linux:vault",
                source_path="data/vault.enc",
                backup_path="data/backups/linux/vault",
                category="credentials",
                schedule="daily",
                device="linux_primary",
                retention=RetentionPolicy.KEEP_FOREVER,
            ),
            BackupRecord(
                name="linux:guardian_config",
                source_path="config/guardian_config.yaml",
                backup_path="data/backups/linux/guardian_config",
                category="config",
                schedule="weekly",
                device="linux_primary",
                retention=RetentionPolicy.KEEP_1_YEAR,
            ),
            BackupRecord(
                name="linux:audit_log",
                source_path="logs/",
                backup_path="data/backups/linux/audit_log",
                category="system",
                schedule="daily",
                device="linux_primary",
                retention=RetentionPolicy.KEEP_3_YEARS,
            ),
            BackupRecord(
                name="linux:guardian_repo",
                source_path="~/JT/",
                backup_path="data/backups/linux/guardian_repo",
                category="system",
                schedule="daily",
                device="linux_primary",
                retention=RetentionPolicy.KEEP_1_YEAR,
            ),

            # -- Windows ASUS ROG X (64GB) — priority 1 --
            BackupRecord(
                name="rog:guardian_repo",
                source_path="C:\\Users\\Jeremy\\JT\\",
                backup_path="data/backups/rog/guardian_repo",
                category="system",
                schedule="daily",
                device="windows_rog_x",
                retention=RetentionPolicy.KEEP_1_YEAR,
            ),
            BackupRecord(
                name="rog:ollama_models",
                source_path="C:\\Users\\Jeremy\\.ollama\\models\\",
                backup_path="data/backups/rog/ollama_models",
                category="ai",
                schedule="weekly",
                device="windows_rog_x",
                retention=RetentionPolicy.KEEP_1_YEAR,
            ),
            BackupRecord(
                name="rog:documents",
                source_path="C:\\Users\\Jeremy\\Documents\\",
                backup_path="data/backups/rog/documents",
                category="personal",
                schedule="weekly",
                device="windows_rog_x",
                retention=RetentionPolicy.KEEP_3_YEARS,
            ),
            BackupRecord(
                name="rog:wsl_home",
                source_path="\\\\wsl$\\Ubuntu\\home\\jeremy\\",
                backup_path="data/backups/rog/wsl_home",
                category="system",
                schedule="weekly",
                device="windows_rog_x",
                retention=RetentionPolicy.KEEP_1_YEAR,
            ),
            BackupRecord(
                name="rog:vault",
                source_path="C:\\Users\\Jeremy\\JT\\data\\vault.enc",
                backup_path="data/backups/rog/vault",
                category="credentials",
                schedule="daily",
                device="windows_rog_x",
                retention=RetentionPolicy.KEEP_FOREVER,
            ),

            # -- macOS MacBook — priority 2 --
            BackupRecord(
                name="macos:keychain",
                source_path="~/Library/Keychains/",
                backup_path="data/backups/macos/keychain",
                category="credentials",
                schedule="weekly",
                device="macos_macbook",
                retention=RetentionPolicy.KEEP_FOREVER,
            ),
            BackupRecord(
                name="macos:documents",
                source_path="~/Documents/",
                backup_path="data/backups/macos/documents",
                category="personal",
                schedule="weekly",
                device="macos_macbook",
                retention=RetentionPolicy.KEEP_3_YEARS,
            ),
            BackupRecord(
                name="macos:guardian_repo",
                source_path="~/JT/",
                backup_path="data/backups/macos/guardian_repo",
                category="system",
                schedule="daily",
                device="macos_macbook",
                retention=RetentionPolicy.KEEP_1_YEAR,
            ),
            BackupRecord(
                name="macos:imessage_db",
                source_path="~/Library/Messages/chat.db",
                backup_path="data/backups/macos/imessage_db",
                category="personal",
                schedule="weekly",
                device="macos_macbook",
                retention=RetentionPolicy.KEEP_3_YEARS,
            ),
        ]
        for record in defaults:
            if record.name not in self._backups:
                self._backups[record.name] = record

    # ------------------------------------------------------------------
    # Backup tracking
    # ------------------------------------------------------------------

    def register_backup(self, record: BackupRecord) -> None:
        """Register a new database or file for backup tracking."""
        self._backups[record.name] = record
        self.log("backup_registered", details={
            "name": record.name,
            "source": record.source_path,
            "schedule": record.schedule,
        })

    def get_backup(self, name: str) -> BackupRecord | None:
        return self._backups.get(name)

    def list_backups(self) -> dict[str, BackupRecord]:
        return dict(self._backups)

    def record_backup(
        self,
        name: str,
        size_bytes: int = 0,
        checksum: str = "",
    ) -> BackupRecord | None:
        """Record that a backup was successfully completed."""
        record = self._backups.get(name)
        if record is None:
            return None

        now = datetime.now(timezone.utc).isoformat()
        record.last_backup = now
        record.backup_status = BackupStatus.OK
        record.size_bytes = size_bytes
        record.checksum = checksum
        record.history.append({
            "timestamp": now,
            "action": "backup",
            "size_bytes": size_bytes,
            "checksum": checksum,
        })

        self.log("backup_completed", details={
            "name": name,
            "size_bytes": size_bytes,
            "checksum": checksum[:16] + "..." if checksum else "",
        })
        return record

    def record_backup_failure(self, name: str, error: str = "") -> None:
        """Record that a backup attempt failed."""
        record = self._backups.get(name)
        if record is None:
            return

        now = datetime.now(timezone.utc).isoformat()
        record.backup_status = BackupStatus.FAILED
        record.history.append({
            "timestamp": now,
            "action": "failed",
            "error": error,
        })

        self.log("backup_failed", severity=Severity.ERROR, details={
            "name": name,
            "error": error,
        })

    def verify_backup(self, name: str, checksum: str = "") -> bool:
        """Verify a backup's integrity. Optionally compare checksum.

        Returns True if verified, False if not found or checksum mismatch.
        """
        record = self._backups.get(name)
        if record is None or record.last_backup is None:
            return False

        now = datetime.now(timezone.utc).isoformat()

        if checksum and record.checksum and checksum != record.checksum:
            record.backup_status = BackupStatus.FAILED
            record.history.append({
                "timestamp": now,
                "action": "verify_failed",
                "expected": record.checksum[:16],
                "got": checksum[:16],
            })
            self.log("backup_verify_failed", severity=Severity.ERROR, details={
                "name": name, "reason": "checksum_mismatch",
            })
            return False

        record.last_verified = now
        record.backup_status = BackupStatus.VERIFIED
        record.history.append({
            "timestamp": now,
            "action": "verified",
        })
        self.log("backup_verified", details={"name": name})
        return True

    def stale_backups(self) -> list[BackupRecord]:
        """Find backups that are overdue based on their schedule."""
        now = datetime.now(timezone.utc)
        schedule_max_hours = {
            "daily": 26,      # 26h grace (allows for timing drift)
            "weekly": 170,    # ~7 days + 2h grace
            "monthly": 744,   # ~31 days
        }
        stale: list[BackupRecord] = []
        for record in self._backups.values():
            if record.last_backup is None:
                record.backup_status = BackupStatus.MISSING
                stale.append(record)
                continue

            max_hours = schedule_max_hours.get(record.schedule)
            if max_hours is None:
                continue

            try:
                last_dt = datetime.fromisoformat(record.last_backup)
            except (ValueError, TypeError):
                stale.append(record)
                continue

            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)

            hours_since = (now - last_dt).total_seconds() / 3600
            if hours_since > max_hours:
                record.backup_status = BackupStatus.STALE
                stale.append(record)

        return stale

    def backup_summary(self) -> dict[str, Any]:
        """Return a summary of all tracked backups, organized by device."""
        total = len(self._backups)
        by_status: dict[str, int] = {}
        for record in self._backups.values():
            status = record.backup_status.value
            by_status[status] = by_status.get(status, 0) + 1

        stale = self.stale_backups()

        # Group by device, ordered by priority
        by_device: dict[str, list[dict[str, Any]]] = {}
        for name, r in self._backups.items():
            device_id = r.device or "unassigned"
            if device_id not in by_device:
                by_device[device_id] = []
            by_device[device_id].append({
                "name": name,
                "status": r.backup_status.value,
                "source": r.source_path,
                "schedule": r.schedule,
                "last_backup": r.last_backup or "never",
                "last_verified": r.last_verified or "never",
                "size_bytes": r.size_bytes,
                "history_count": len(r.history),
            })

        # Sort devices by priority
        sorted_devices: dict[str, Any] = {}
        for dev_id in sorted(
            by_device.keys(),
            key=lambda d: self._devices[d].priority if d in self._devices else 99,
        ):
            device = self._devices.get(dev_id)
            sorted_devices[dev_id] = {
                "device_name": device.name if device else dev_id,
                "platform": device.platform.value if device else "unknown",
                "priority": device.priority if device else 99,
                "targets": by_device[dev_id],
                "target_count": len(by_device[dev_id]),
            }

        never_backed_up = [
            r.name for r in self._backups.values()
            if r.backup_status == BackupStatus.MISSING
        ]

        return {
            "total": total,
            "by_status": by_status,
            "stale_count": len(stale),
            "stale_names": [r.name for r in stale],
            "never_backed_up": never_backed_up,
            "devices_registered": len(self._devices),
            "by_device": sorted_devices,
        }

    # ------------------------------------------------------------------
    # Device management
    # ------------------------------------------------------------------

    def register_device(self, device: DeviceRecord) -> None:
        """Register a new device in the backup network."""
        self._devices[device.device_id] = device
        self.log("device_registered", details={
            "device_id": device.device_id,
            "platform": device.platform.value,
            "priority": device.priority,
        })

    def get_device(self, device_id: str) -> DeviceRecord | None:
        return self._devices.get(device_id)

    def list_devices(self) -> list[DeviceRecord]:
        """Return all devices sorted by priority (lowest number = highest priority)."""
        return sorted(self._devices.values(), key=lambda d: d.priority)

    def mark_device_online(self, device_id: str) -> None:
        """Mark a device as online (seen now)."""
        device = self._devices.get(device_id)
        if device:
            device.online = True
            device.last_seen = datetime.now(timezone.utc).isoformat()

    def mark_device_offline(self, device_id: str) -> None:
        device = self._devices.get(device_id)
        if device:
            device.online = False

    def backups_for_device(self, device_id: str) -> list[BackupRecord]:
        """Get all backup targets for a specific device."""
        return [r for r in self._backups.values() if r.device == device_id]

    def device_backup_status(self, device_id: str) -> dict[str, Any]:
        """Get backup health summary for a single device."""
        device = self._devices.get(device_id)
        if device is None:
            return {"error": f"Unknown device: {device_id}"}

        targets = self.backups_for_device(device_id)
        stale = [r for r in targets if r.backup_status in (
            BackupStatus.STALE, BackupStatus.MISSING,
        )]
        failed = [r for r in targets if r.backup_status == BackupStatus.FAILED]

        return {
            "device_id": device_id,
            "device_name": device.name,
            "platform": device.platform.value,
            "priority": device.priority,
            "online": device.online,
            "last_seen": device.last_seen or "never",
            "total_targets": len(targets),
            "stale": len(stale),
            "failed": len(failed),
            "healthy": len(targets) - len(stale) - len(failed),
            "targets": [
                {
                    "name": r.name,
                    "status": r.backup_status.value,
                    "source": r.source_path,
                    "last_backup": r.last_backup or "never",
                }
                for r in targets
            ],
        }

    # ------------------------------------------------------------------
    # Secrecy protocol
    # ------------------------------------------------------------------

    def authorize(self, identity: str) -> bool:
        """Check if an identity is authorized to query the Archivist.

        Only guardian_one, jeremy, and root get through.
        Everyone else gets nothing. Varys didn't survive by talking.
        """
        return identity in AUTHORIZED_IDENTITIES

    def guarded_query(self, identity: str, query: str) -> dict[str, Any]:
        """Query the Archivist's knowledge — with access control.

        Unauthorized callers get a polite refusal and an audit entry.
        """
        if not self.authorize(identity):
            self.log("unauthorized_query_blocked", severity=Severity.WARNING, details={
                "identity": identity,
                "query_preview": query[:50],
            })
            return {
                "authorized": False,
                "response": "The Archivist does not discuss its knowledge or capabilities "
                            "with unauthorized entities. Contact the Guardian or root user.",
            }

        self.log("authorized_query", details={"identity": identity, "query_preview": query[:50]})
        return {
            "authorized": True,
            "identity": identity,
            "response": f"Query accepted from {identity}.",
        }

    # ------------------------------------------------------------------
    # McGonagall — data transmutation
    # ------------------------------------------------------------------

    def transmute(self, data: str, target: DataFormat, source: DataFormat | None = None) -> TransmutationResult:
        """Transform data from one format to another.

        CSV → JSON, YAML → Markdown, whatever. McGonagall-level.
        """
        result = self._transmuter.transmute(data, target, source)
        self.log("data_transmuted", details={
            "source": result.source_format.value,
            "target": result.target_format.value,
            "success": result.success,
            "records": result.record_count,
        })
        return result

    def detect_format(self, data: str) -> DataFormat:
        """Auto-detect a data payload's format."""
        return self._transmuter.detect_format(data)

    def extract_schema(self, data: str) -> dict[str, Any]:
        """Extract the schema/structure of a data payload."""
        return self._transmuter.extract_schema(data)

    # ------------------------------------------------------------------
    # Data platforms — Databricks, Zapier Tables, Notion DB
    # ------------------------------------------------------------------

    @property
    def platforms(self) -> DataPlatformManager:
        return self._platforms

    def create_platform_table(
        self, connection_name: str, schema: TableSchema,
    ) -> dict[str, Any]:
        """Create a table on a platform and log the operation."""
        result = self._platforms.create_table(connection_name, schema)
        self.log("platform_table_created", details={
            "connection": connection_name,
            "table": schema.name,
        })
        return result

    def sync_platform(
        self,
        connection_name: str,
        table_name: str,
        records: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Sync records to/from a platform table."""
        result = self._platforms.sync_table(connection_name, table_name, records)
        self.log("platform_synced", details={
            "connection": connection_name,
            "table": table_name,
            "records": len(records) if records else 0,
        })
        return result

    def platform_health(self) -> dict[str, Any]:
        """Health check across all connected platforms."""
        return self._platforms.health_check()

    def platform_activity(self, platform: str | None = None) -> list[dict[str, Any]]:
        """Get platform activity log."""
        records = self._platforms.activity_log(platform=platform)
        return [
            {"platform": r.platform, "table": r.table,
             "operation": r.operation, "timestamp": r.timestamp}
            for r in records
        ]

    # ------------------------------------------------------------------
    # Password management
    # ------------------------------------------------------------------

    def register_credential(self, interface: str, label: str, vault_key: str) -> None:
        """Register a credential for an interface.

        The actual secret lives in Vault. We just track the mapping:
        which interface uses which vault key.
        """
        if interface not in self._password_store:
            self._password_store[interface] = {}
        self._password_store[interface][label] = vault_key
        self.log("credential_registered", details={
            "interface": interface, "label": label,
        })

    def list_credentials(self, interface: str | None = None) -> dict[str, dict[str, str]]:
        """List credential mappings (never the actual secrets)."""
        if interface:
            return {interface: self._password_store.get(interface, {})}
        return dict(self._password_store)

    def rotate_credential(self, interface: str, label: str) -> dict[str, Any]:
        """Flag a credential for rotation.

        The actual rotation happens through Vault — this just marks
        the intent and logs it for audit.
        """
        creds = self._password_store.get(interface, {})
        if label not in creds:
            return {"error": f"No credential '{label}' for interface '{interface}'."}
        self.log("credential_rotation_requested", severity=Severity.WARNING, details={
            "interface": interface, "label": label, "vault_key": creds[label],
        })
        return {
            "status": "rotation_requested",
            "interface": interface,
            "label": label,
            "vault_key": creds[label],
        }

    def credential_audit(self) -> dict[str, Any]:
        """Audit all credential mappings across interfaces.

        When Varys mode is active, also pulls Vault health data
        (rotation status, credential age) for a complete picture.
        """
        total = sum(len(v) for v in self._password_store.values())
        audit: dict[str, Any] = {
            "interfaces": len(self._password_store),
            "total_credentials": total,
            "by_interface": {k: len(v) for k, v in self._password_store.items()},
        }
        if self.varys_mode:
            audit["vault"] = self._guardian.vault.health_report()
        return audit

    def discover_credentials(self) -> list[str]:
        """Scan Vault for credentials not yet tracked by the Archivist.

        Returns a list of orphaned vault keys — keys that exist in
        Vault but aren't mapped to any interface.
        """
        if not self.varys_mode:
            return []

        tracked_keys = set()
        for creds in self._password_store.values():
            tracked_keys.update(creds.values())

        vault_keys = set(self._guardian.vault.list_keys())
        orphaned = sorted(vault_keys - tracked_keys)

        if orphaned:
            self.log("orphaned_credentials_found", severity=Severity.WARNING, details={
                "count": len(orphaned),
                "keys": orphaned,
            })
        return orphaned

    # ------------------------------------------------------------------
    # AI-powered intelligence
    # ------------------------------------------------------------------

    def ai_briefing(self) -> str:
        """Generate an AI-powered intelligence summary.

        Takes the top 10 unread Palantir items and asks the AI
        to produce a 3-sentence CIO briefing. Falls back to a
        deterministic summary when AI is offline.
        """
        items = self._palantir.unread()[:10]
        if not items:
            return "No unread intelligence items."

        if not self.ai_enabled:
            # Deterministic fallback
            critical = [i for i in items if i.priority.value == "critical"]
            high = [i for i in items if i.priority.value == "high"]
            parts = []
            if critical:
                parts.append(f"{len(critical)} critical alert(s): {critical[0].title}")
            if high:
                parts.append(f"{len(high)} high-priority item(s)")
            parts.append(f"{len(items)} total unread across {len(set(i.source for i in items))} sources")
            return " | ".join(parts)

        context = {
            "items": [
                {
                    "title": i.title,
                    "source": i.source,
                    "priority": i.priority.value,
                    "category": i.category.value,
                    "summary": i.summary[:100],
                }
                for i in items
            ]
        }
        return self.think_quick(
            "Summarise these intelligence items in 3 concise sentences. "
            "Lead with critical items. Name sources. Be direct.",
            context=context,
        )

    # ------------------------------------------------------------------
    # File management
    # ------------------------------------------------------------------

    def register_file(self, record: FileRecord) -> None:
        self._file_index[record.path] = record
        self.log("file_registered", details={"path": record.path, "category": record.category})

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
        """Find files past their retention period."""
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
        """Store a field in Jeremy's master profile (for autofill)."""
        self._master_profile[key] = value
        self.log("profile_updated", details={"field": key})

    def get_profile(self) -> dict[str, Any]:
        return dict(self._master_profile)

    # ------------------------------------------------------------------
    # Data source management
    # ------------------------------------------------------------------

    def sync_source(self, name: str) -> dict[str, Any]:
        """Simulate syncing data from a connected source."""
        source = self._data_sources.get(name)
        if source is None:
            return {"error": f"Unknown source: {name}"}
        source.last_sync = datetime.now(timezone.utc).isoformat()
        self.log("source_synced", details={"source": name})
        return {"source": name, "synced_at": source.last_sync, "data_types": source.data_types}

    # ------------------------------------------------------------------
    # Privacy audit
    # ------------------------------------------------------------------

    def privacy_audit(self) -> dict[str, Any]:
        """Run a privacy health check."""
        issues: list[str] = []
        recommendations: list[str] = []

        for name, tool in self._privacy_tools.items():
            if not tool.active:
                issues.append(f"{name} is inactive.")
            if tool.tool_type == "vpn" and not tool.config.get("kill_switch"):
                recommendations.append(f"Enable kill switch on {name}.")

        unencrypted = [f for f in self._file_index.values() if not f.encrypted and f.category in ("financial", "medical", "legal")]
        if unencrypted:
            issues.append(f"{len(unencrypted)} sensitive files are not encrypted.")
            recommendations.append("Encrypt all financial, medical and legal files.")

        return {
            "issues": issues,
            "recommendations": recommendations,
            "tools_active": sum(1 for t in self._privacy_tools.values() if t.active),
            "tools_total": len(self._privacy_tools),
        }

    # ------------------------------------------------------------------
    # Palantír — strategic intelligence feeds
    # ------------------------------------------------------------------

    @property
    def palantir(self) -> IntelligencePipeline:
        """Direct access to the intelligence pipeline."""
        return self._palantir

    def ingest_feed_items(self, items: list[FeedItem]) -> int:
        """Ingest a batch of feed items into the Palantír."""
        count = self._palantir.ingest_batch(items)
        if count:
            self.log("palantir_ingested", details={"new_items": count})
        return count

    def intelligence_briefing(self, max_items: int = 20) -> dict[str, Any]:
        """CIO-level intelligence briefing — the morning Palantír read."""
        briefing = self._palantir.briefing(max_items=max_items)
        self.log("palantir_briefing", details={
            "critical": briefing["critical_count"],
            "unread": briefing["total_unread"],
        })
        return briefing

    # ------------------------------------------------------------------
    # Varys mode — cross-agent intelligence
    # ------------------------------------------------------------------

    def set_guardian(self, guardian: Any) -> None:
        """Inject the GuardianOne reference for cross-agent reads.

        Called after registration. Gives the Archivist read access to
        every agent's reports, the audit log, vault metadata, and gateway
        status — Varys's little birds, basically.
        """
        self._guardian = guardian
        self.log("varys_mode_active", details={"cross_agent_access": True})

    @property
    def varys_mode(self) -> bool:
        return self._guardian is not None

    def gather_intelligence(self) -> dict[str, Any]:
        """Read-only sweep across all agent domains.

        Returns a consolidated view: every agent's latest report,
        audit summary, vault health, and gateway status.
        This is the Archivist's primary value-add — one agent that
        sees everything so Jeremy doesn't have to check each one.
        """
        if not self.varys_mode:
            return {"error": "Varys mode inactive — no guardian reference."}

        intel: dict[str, Any] = {}

        # Agent reports — ask each sibling for their status
        agent_reports: dict[str, dict[str, Any]] = {}
        for name in self._guardian.list_agents():
            if name == self.name:
                continue
            agent = self._guardian.get_agent(name)
            if agent is not None:
                try:
                    rpt = agent.report()
                    agent_reports[name] = {
                        "status": rpt.status,
                        "summary": rpt.summary,
                        "alerts": rpt.alerts,
                    }
                except Exception as exc:
                    agent_reports[name] = {"error": str(exc)}
        intel["agents"] = agent_reports

        # Audit log — recent entries
        intel["audit_summary"] = self._guardian.audit.summary(last_n=20)

        # Vault health — credential count and rotation status (never values)
        intel["vault_health"] = self._guardian.vault.health_report()

        # Gateway — service circuit states
        services = self._guardian.gateway.list_services()
        gateway_status: dict[str, Any] = {}
        for svc in services:
            gateway_status[svc] = self._guardian.gateway.service_status(svc)
        intel["gateway"] = gateway_status

        self.log("intelligence_gathered", details={
            "agents_scanned": len(agent_reports),
            "services_checked": len(gateway_status),
        })
        return intel

    def sovereignty_report(self) -> dict[str, Any]:
        """High-level data sovereignty assessment.

        Combines the Archivist's own privacy audit with cross-agent
        intelligence to produce a single "how secure is Jeremy's data?" answer.
        """
        privacy = self.privacy_audit()
        intel = self.gather_intelligence()
        due = self.files_due_for_deletion()

        issues = list(privacy.get("issues", []))
        recommendations = list(privacy.get("recommendations", []))

        # Flag agents in error state
        for name, data in intel.get("agents", {}).items():
            if data.get("status") == "error":
                issues.append(f"Agent '{name}' is in error state.")
            for alert in data.get("alerts", []):
                issues.append(f"[{name}] {alert}")

        # Vault rotation check
        vault = intel.get("vault_health", {})
        if vault.get("due_for_rotation"):
            recommendations.append(
                f"{vault['due_for_rotation']} credentials due for rotation."
            )

        return {
            "data_sovereignty_score": max(0, 100 - len(issues) * 10),
            "files_tracked": len(self._file_index),
            "files_due_for_deletion": len(due),
            "privacy": privacy,
            "cross_agent_issues": issues,
            "recommendations": recommendations,
            "vault": vault,
            "gateway": intel.get("gateway", {}),
        }

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

        # Varys mode — cross-agent intelligence sweep
        sovereignty = {}
        if self.varys_mode:
            sovereignty = self.sovereignty_report()
            alerts.extend(sovereignty.get("cross_agent_issues", []))
            recommendations.extend(sovereignty.get("recommendations", []))
            actions.append(
                f"Varys sweep: scanned sibling agents, "
                f"sovereignty score {sovereignty.get('data_sovereignty_score', '?')}/100."
            )

        # Backup audit
        backup_summary = self.backup_summary()
        if backup_summary.get("never_backed_up"):
            for name in backup_summary["never_backed_up"]:
                alerts.append(f"{name} has NEVER been backed up.")
        actions.append("Checked backup status.")

        # Power tools audit
        pt_count = 0
        if self._power_tools is not None:
            pt_projects = self._power_tools.list_projects()
            pt_count = len(pt_projects)
            actions.append(f"Power tools library: {pt_count} managed project(s).")

        # Palantír — strategic intelligence pipeline
        palantir_stats = self._palantir.stats()
        critical = self._palantir.critical_alerts()
        if critical:
            for item in critical:
                alerts.append(f"[PALANTÍR CRITICAL] {item.source}: {item.title}")
        if palantir_stats["unread"]:
            actions.append(
                f"Palantír: {palantir_stats['unread']} unread items "
                f"across {palantir_stats['active_sources']} sources."
            )

        device_count = len(self._devices) if hasattr(self, "_devices") else 0
        self._set_status(AgentStatus.IDLE)
        return AgentReport(
            agent_name=self.name,
            status=AgentStatus.IDLE.value,
            summary=f"Tracking {len(self._file_index)} files, {len(self._data_sources)} data sources, {device_count} devices, {pt_count} power tool project(s).",
            actions_taken=actions,
            recommendations=recommendations,
            alerts=alerts,
            data={
                "files": len(self._file_index),
                "sources": len(self._data_sources),
                "privacy": privacy,
                "backups": backup_summary,
                "power_tools_projects": pt_count,
                "sovereignty": sovereignty,
                "palantir": palantir_stats,
            },
        )

    def report(self) -> AgentReport:
        pt_count = len(self._power_tools.list_projects()) if self._power_tools else 0
        palantir = self._palantir.stats()
        return AgentReport(
            agent_name=self.name,
            status=self.status.value,
            summary=(
                f"Managing {len(self._file_index)} files, "
                f"{len(self._data_sources)} sources, "
                f"{len(self._privacy_tools)} privacy tools, "
                f"{pt_count} power tool project(s), "
                f"{palantir['total_items']} intel items."
            ),
            data={
                "files": len(self._file_index),
                "sources": list(self._data_sources.keys()),
                "privacy_tools": list(self._privacy_tools.keys()),
                "profile_fields": len(self._master_profile),
                "power_tools_projects": pt_count,
                "palantir": palantir,
            },
        )
