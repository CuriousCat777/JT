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

    def __init__(self, config: AgentConfig, audit: AuditLog) -> None:
        super().__init__(config, audit)
        self._file_index: dict[str, FileRecord] = {}
        self._data_sources: dict[str, DataSource] = {}
        self._privacy_tools: dict[str, PrivacyTool] = {}
        self._master_profile: dict[str, Any] = {}
        self._backup_schedule: dict[str, str] = {}
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
        self.log("initialized", details={
            "sources": len(self._data_sources),
            "privacy_tools": len(self._privacy_tools),
            "platforms": len(self._platforms.list_connections()),
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
        """Audit all credential mappings across interfaces."""
        total = sum(len(v) for v in self._password_store.values())
        return {
            "interfaces": len(self._password_store),
            "total_credentials": total,
            "by_interface": {k: len(v) for k, v in self._password_store.items()},
        }

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

        self._set_status(AgentStatus.IDLE)
        return AgentReport(
            agent_name=self.name,
            status=AgentStatus.IDLE.value,
            summary=f"Tracking {len(self._file_index)} files, {len(self._data_sources)} data sources.",
            actions_taken=actions,
            recommendations=recommendations,
            alerts=alerts,
            data={
                "files": len(self._file_index),
                "sources": len(self._data_sources),
                "privacy": privacy,
                "sovereignty": sovereignty,
                "palantir": palantir_stats,
            },
        )

    def report(self) -> AgentReport:
        palantir = self._palantir.stats()
        return AgentReport(
            agent_name=self.name,
            status=self.status.value,
            summary=(
                f"Managing {len(self._file_index)} files, "
                f"{len(self._data_sources)} sources, "
                f"{len(self._privacy_tools)} privacy tools, "
                f"{palantir['total_items']} intel items."
            ),
            data={
                "files": len(self._file_index),
                "sources": list(self._data_sources.keys()),
                "privacy_tools": list(self._privacy_tools.keys()),
                "profile_fields": len(self._master_profile),
                "palantir": palantir,
            },
        )
