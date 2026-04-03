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
    """Chief of Staff for libraries and file organisation.

    The Archivist owns every file, every data source, every retention clock.
    Six jobs: catalogue it, index it, encrypt the sensitive stuff, sync the
    sources, audit the privacy posture, schedule the backups. That's it.
    No scope creep — if it's not about data sovereignty, it's not our problem.
    """

    def __init__(self, config: AgentConfig, audit: AuditLog) -> None:
        super().__init__(config, audit)
        self._file_index: dict[str, FileRecord] = {}
        self._data_sources: dict[str, DataSource] = {}
        self._privacy_tools: dict[str, PrivacyTool] = {}
        self._master_profile: dict[str, Any] = {}
        self._backup_schedule: dict[str, str] = {}
        self._guardian: Any = None  # Injected post-registration for Varys mode

    def initialize(self) -> None:
        self._set_status(AgentStatus.IDLE)
        self._setup_default_sources()
        self._setup_privacy_tools()
        self._setup_file_categories()
        self.log("initialized", details={
            "sources": len(self._data_sources),
            "privacy_tools": len(self._privacy_tools),
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
            },
        )

    def report(self) -> AgentReport:
        return AgentReport(
            agent_name=self.name,
            status=self.status.value,
            summary=f"Managing {len(self._file_index)} files, {len(self._data_sources)} sources, {len(self._privacy_tools)} privacy tools.",
            data={
                "files": len(self._file_index),
                "sources": list(self._data_sources.keys()),
                "privacy_tools": list(self._privacy_tools.keys()),
                "profile_fields": len(self._master_profile),
            },
        )
