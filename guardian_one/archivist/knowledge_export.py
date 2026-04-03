"""Knowledge Exporter — prepare Archivist data for Open WebUI RAG.

Converts Guardian One's internal state into plain-text knowledge
documents that Open WebUI can index for RAG retrieval. This gives
the local AI full context about:

- All tracked accounts and their health status
- Technology registry (every tool/service detected)
- Telemetry summary (recent cross-system activity)
- File index and retention status
- Cloud sync status

Output: Markdown files written to a knowledge directory that
Open WebUI mounts as a RAG source.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class KnowledgeExporter:
    """Export Archivist state as RAG-friendly knowledge documents."""

    def __init__(self, data_dir: Path | None = None, output_dir: Path | None = None) -> None:
        self._data_dir = data_dir or Path("data")
        self._output_dir = output_dir or self._data_dir / "knowledge"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def export_all(self) -> dict[str, bool]:
        """Export all knowledge documents. Returns {filename: success}."""
        results: dict[str, bool] = {}
        exporters = [
            ("guardian_system_overview.md", self._export_overview),
            ("accounts_and_storage.md", self._export_accounts),
            ("technology_registry.md", self._export_tech_registry),
            ("recent_activity.md", self._export_recent_activity),
            ("file_index.md", self._export_file_index),
        ]
        for filename, exporter in exporters:
            try:
                content = exporter()
                (self._output_dir / filename).write_text(content)
                results[filename] = True
            except Exception as exc:
                logger.error("Failed to export %s: %s", filename, exc)
                results[filename] = False
        return results

    def _export_overview(self) -> str:
        """System overview document."""
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Guardian One — System Overview",
            f"\nLast updated: {now}",
            "\nGuardian One is Jeremy Paulo Salvino Tabernero's multi-agent AI orchestration platform.",
            "It manages finances, scheduling, email, websites, data sovereignty, and security.",
            "\n## Active Agents",
            "- **Archivist**: Central telemetry, file management, data sovereignty",
            "- **CFO**: Financial intelligence (Plaid, Empower, Rocket Money)",
            "- **Chronos**: Schedule & calendar management",
            "- **VARYS**: Security monitoring (Wazuh SIEM, threat detection)",
            "- **Web Architect**: Website management (drjeremytabernero.org, jtmdai.com)",
            "- **Gmail Agent**: Email inbox monitoring",
            "- **DoorDash Agent**: Meal delivery coordination",
            "\n## Key Principles",
            "- Data sovereignty: Jeremy owns all data, encrypted at rest and in transit",
            "- Zero data exploitation: no data leaves without explicit consent",
            "- Audit everything: immutable log of all agent actions",
            "- Content gate: PHI/PII patterns blocked before any external sync",
        ]
        return "\n".join(lines)

    def _export_accounts(self) -> str:
        """Accounts and storage summary."""
        registry_file = self._data_dir / "account_registry.json"
        lines = [
            "# Accounts & Storage Summary",
            f"\nLast updated: {datetime.now(timezone.utc).isoformat()}",
        ]

        if not registry_file.exists():
            lines.append("\nNo accounts registered yet.")
            return "\n".join(lines)

        try:
            with open(registry_file) as f:
                accounts = json.load(f)
        except (json.JSONDecodeError, OSError):
            lines.append("\nFailed to load account registry.")
            return "\n".join(lines)

        # Group by type
        by_type: dict[str, list] = {}
        for key, acct in accounts.items():
            atype = acct.get("account_type", "other")
            by_type.setdefault(atype, []).append(acct)

        for atype, accts in sorted(by_type.items()):
            lines.append(f"\n## {atype.replace('_', ' ').title()} ({len(accts)})")
            for acct in accts:
                name = acct.get("name", "Unknown")
                provider = acct.get("provider", "")
                has_2fa = "2FA" if acct.get("has_2fa") else "No 2FA"
                strength = acct.get("password_strength", "unknown")
                lines.append(f"- **{name}** ({provider}) — {has_2fa}, password: {strength}")

                # Storage info
                quota = acct.get("storage_quota_mb", 0)
                if quota > 0:
                    used = acct.get("storage_used_mb", 0)
                    pct = round(used / quota * 100, 1)
                    lines.append(f"  - Storage: {round(used/1024, 1)} GB / {round(quota/1024, 1)} GB ({pct}%)")

        return "\n".join(lines)

    def _export_tech_registry(self) -> str:
        """Technology registry document."""
        registry_file = self._data_dir / "tech_registry.json"
        lines = [
            "# Technology Registry",
            f"\nLast updated: {datetime.now(timezone.utc).isoformat()}",
            "\nEvery technology, service, tool, and device detected by Guardian One:",
        ]

        if not registry_file.exists():
            lines.append("\nNo technologies tracked yet.")
            return "\n".join(lines)

        try:
            with open(registry_file) as f:
                registry = json.load(f)
        except (json.JSONDecodeError, OSError):
            lines.append("\nFailed to load tech registry.")
            return "\n".join(lines)

        # Group by type
        by_type: dict[str, list] = {}
        for key, record in registry.items():
            ttype = record.get("tech_type", "other")
            by_type.setdefault(ttype, []).append(record)

        for ttype, records in sorted(by_type.items()):
            lines.append(f"\n## {ttype.replace('_', ' ').title()} ({len(records)})")
            for rec in records:
                name = rec.get("name", "Unknown")
                first = rec.get("first_seen", "")[:10]
                count = rec.get("interaction_count", 0)
                reviewed = "Reviewed" if rec.get("reviewed") else "Pending review"
                lines.append(f"- **{name}** — first seen {first}, {count} interactions, {reviewed}")

        return "\n".join(lines)

    def _export_recent_activity(self) -> str:
        """Recent telemetry activity summary."""
        telemetry_file = self._data_dir / "telemetry.jsonl"
        lines = [
            "# Recent Activity",
            f"\nLast updated: {datetime.now(timezone.utc).isoformat()}",
        ]

        if not telemetry_file.exists():
            lines.append("\nNo telemetry data yet.")
            return "\n".join(lines)

        # Read last 100 events
        events: list[dict] = []
        try:
            with open(telemetry_file) as f:
                all_lines = f.readlines()
            for line in all_lines[-100:]:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            lines.append("\nFailed to read telemetry log.")
            return "\n".join(lines)

        # Source summary
        source_counts: dict[str, int] = {}
        for event in events:
            src = event.get("source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1

        lines.append(f"\n## Summary (last {len(events)} events)")
        for src, count in sorted(source_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- **{src}**: {count} events")

        # Last 20 events
        lines.append("\n## Recent Events")
        for event in events[-20:]:
            ts = event.get("timestamp", "")[:19]
            src = event.get("source", "?")
            action = event.get("action", "?")
            target = event.get("target", "")
            target_str = f" → {target}" if target else ""
            lines.append(f"- [{ts}] {src}.{action}{target_str}")

        return "\n".join(lines)

    def _export_file_index(self) -> str:
        """File index and retention status."""
        state_file = self._data_dir / "archivist_state.json"
        lines = [
            "# File Index & Retention",
            f"\nLast updated: {datetime.now(timezone.utc).isoformat()}",
        ]

        if not state_file.exists():
            lines.append("\nNo files tracked yet.")
            return "\n".join(lines)

        try:
            with open(state_file) as f:
                state = json.load(f)
        except (json.JSONDecodeError, OSError):
            lines.append("\nFailed to load state file.")
            return "\n".join(lines)

        file_index = state.get("file_index", {})
        if not file_index:
            lines.append("\nNo files indexed.")
            return "\n".join(lines)

        # Group by category
        by_cat: dict[str, list] = {}
        for path, record in file_index.items():
            cat = record.get("category", "other")
            by_cat.setdefault(cat, []).append(record)

        for cat, records in sorted(by_cat.items()):
            lines.append(f"\n## {cat.title()} ({len(records)} files)")
            for rec in records:
                path = rec.get("path", "?")
                retention = rec.get("retention", "?")
                encrypted = "Encrypted" if rec.get("encrypted") else "Unencrypted"
                lines.append(f"- `{path}` — {retention}, {encrypted}")

        return "\n".join(lines)
