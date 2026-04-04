"""Standalone Archivist agent — thread-safe with persistent JSON state.

No Guardian One dependencies. Designed to run independently in the
ai-sandbox temporary environment.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import (
    AuditEntry,
    DataSource,
    FileRecord,
    PrivacyTool,
    RetentionPolicy,
)

STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "state.json"


class Archivist:
    """Thread-safe, standalone Archivist with persistent JSON state."""

    def __init__(self, state_path: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._state_path = state_path or STATE_FILE
        self._file_index: dict[str, FileRecord] = {}
        self._data_sources: dict[str, DataSource] = {}
        self._privacy_tools: dict[str, PrivacyTool] = {}
        self._master_profile: dict[str, Any] = {}
        self._audit_log: list[AuditEntry] = []
        self._backup_schedule: dict[str, str] = {
            "medical": "weekly",
            "financial": "daily",
            "personal": "weekly",
            "professional": "daily",
            "legal": "monthly",
        }
        self._load_state()
        self._setup_defaults()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> None:
        if not self._state_path.exists():
            return
        try:
            raw = json.loads(self._state_path.read_text())
            for path, data in raw.get("files", {}).items():
                self._file_index[path] = FileRecord.from_dict(data)
            for key, data in raw.get("sources", {}).items():
                self._data_sources[key] = DataSource.from_dict(data)
            for key, data in raw.get("privacy_tools", {}).items():
                self._privacy_tools[key] = PrivacyTool.from_dict(data)
            self._master_profile = raw.get("profile", {})
            for entry in raw.get("audit_log", [])[-500:]:
                self._audit_log.append(AuditEntry(**entry))
        except (json.JSONDecodeError, KeyError):
            pass  # Start fresh on corrupt state

    def _save_state(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "files": {p: r.to_dict() for p, r in self._file_index.items()},
            "sources": {k: s.to_dict() for k, s in self._data_sources.items()},
            "privacy_tools": {k: t.to_dict() for k, t in self._privacy_tools.items()},
            "profile": self._master_profile,
            "audit_log": [e.to_dict() for e in self._audit_log[-500:]],
        }
        self._state_path.write_text(json.dumps(state, indent=2))

    def _log(self, action: str, details: dict[str, Any] | None = None, severity: str = "info") -> None:
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            action=action,
            details=details or {},
            severity=severity,
        )
        self._audit_log.append(entry)

    # ------------------------------------------------------------------
    # Default setup
    # ------------------------------------------------------------------

    def _setup_defaults(self) -> None:
        if not self._data_sources:
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
        if not self._privacy_tools:
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
        self._save_state()

    # ------------------------------------------------------------------
    # File management
    # ------------------------------------------------------------------

    def register_file(self, record: FileRecord) -> FileRecord:
        with self._lock:
            self._file_index[record.path] = record
            self._log("file_registered", {"path": record.path, "category": record.category})
            self._save_state()
            return record

    def get_file(self, path: str) -> FileRecord | None:
        with self._lock:
            return self._file_index.get(path)

    def delete_file(self, path: str) -> bool:
        with self._lock:
            if path in self._file_index:
                del self._file_index[path]
                self._log("file_deleted", {"path": path})
                self._save_state()
                return True
            return False

    def list_files(self) -> list[FileRecord]:
        with self._lock:
            return list(self._file_index.values())

    def search_files(
        self,
        query: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
    ) -> list[FileRecord]:
        with self._lock:
            results = list(self._file_index.values())
            if category:
                results = [f for f in results if f.category == category]
            if tags:
                tag_set = set(tags)
                results = [f for f in results if tag_set.intersection(f.tags)]
            if query:
                q = query.lower()
                results = [
                    f for f in results
                    if q in f.path.lower() or any(q in t.lower() for t in f.tags)
                ]
            return results

    def files_due_for_deletion(self) -> list[FileRecord]:
        now = datetime.now(timezone.utc)
        retention_days = {
            RetentionPolicy.DELETE_AFTER_USE: 0,
            RetentionPolicy.KEEP_1_YEAR: 365,
            RetentionPolicy.KEEP_3_YEARS: 1095,
            RetentionPolicy.KEEP_7_YEARS: 2555,
            RetentionPolicy.KEEP_FOREVER: None,
        }
        due: list[FileRecord] = []
        with self._lock:
            for record in self._file_index.values():
                max_days = retention_days.get(record.retention)
                if max_days is None:
                    continue
                try:
                    created_dt = datetime.fromisoformat(record.created)
                except (ValueError, TypeError):
                    continue
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=timezone.utc)
                if (now - created_dt).days > max_days:
                    due.append(record)
        return due

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------

    def set_profile_field(self, key: str, value: Any) -> None:
        with self._lock:
            self._master_profile[key] = value
            self._log("profile_updated", {"field": key})
            self._save_state()

    def get_profile(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._master_profile)

    # ------------------------------------------------------------------
    # Data sources
    # ------------------------------------------------------------------

    def list_sources(self) -> list[DataSource]:
        with self._lock:
            return list(self._data_sources.values())

    def add_source(self, key: str, source: DataSource) -> DataSource:
        with self._lock:
            self._data_sources[key] = source
            self._log("source_added", {"key": key, "name": source.name})
            self._save_state()
            return source

    def sync_source(self, name: str) -> dict[str, Any]:
        with self._lock:
            source = self._data_sources.get(name)
            if source is None:
                return {"error": f"Unknown source: {name}"}
            source.last_sync = datetime.now(timezone.utc).isoformat()
            self._log("source_synced", {"source": name})
            self._save_state()
            return {"source": name, "synced_at": source.last_sync, "data_types": source.data_types}

    # ------------------------------------------------------------------
    # Privacy tools
    # ------------------------------------------------------------------

    def list_privacy_tools(self) -> list[PrivacyTool]:
        with self._lock:
            return list(self._privacy_tools.values())

    def privacy_audit(self) -> dict[str, Any]:
        with self._lock:
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
            self._log("privacy_audit_run")
            return {
                "issues": issues,
                "recommendations": recommendations,
                "tools_active": sum(1 for t in self._privacy_tools.values() if t.active),
                "tools_total": len(self._privacy_tools),
            }

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    def get_audit_log(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return [e.to_dict() for e in self._audit_log[-limit:]]

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "files_tracked": len(self._file_index),
                "data_sources": len(self._data_sources),
                "privacy_tools": len(self._privacy_tools),
                "profile_fields": len(self._master_profile),
                "audit_entries": len(self._audit_log),
                "backup_schedule": self._backup_schedule,
            }
