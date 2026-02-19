"""Audit logging — all agent decisions are recorded and reviewable."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEntry:
    """A single auditable event."""
    timestamp: str
    agent: str
    action: str
    severity: str
    details: dict[str, Any] = field(default_factory=dict)
    requires_review: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditLog:
    """Thread-safe, append-only audit log.

    Writes to a JSONL (JSON Lines) file so entries can be streamed and
    searched without loading the entire log into memory.
    """

    def __init__(self, log_dir: Path | None = None) -> None:
        self._log_dir = log_dir or Path("logs")
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._log_dir / "audit.jsonl"
        self._lock = threading.Lock()
        self._entries: list[AuditEntry] = []

    def record(
        self,
        agent: str,
        action: str,
        severity: Severity = Severity.INFO,
        details: dict[str, Any] | None = None,
        requires_review: bool = False,
    ) -> AuditEntry:
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent=agent,
            action=action,
            severity=severity.value,
            details=details or {},
            requires_review=requires_review,
        )
        with self._lock:
            self._entries.append(entry)
            with open(self._log_file, "a") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        return entry

    def query(
        self,
        agent: str | None = None,
        severity: Severity | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Filter log entries in memory."""
        results: list[AuditEntry] = []
        for entry in reversed(self._entries):
            if agent and entry.agent != agent:
                continue
            if severity and entry.severity != severity.value:
                continue
            if since and entry.timestamp < since:
                break
            results.append(entry)
            if len(results) >= limit:
                break
        return results

    def pending_reviews(self) -> list[AuditEntry]:
        return [e for e in self._entries if e.requires_review]

    def summary(self, last_n: int = 20) -> str:
        """Human-readable summary of recent activity."""
        recent = self._entries[-last_n:]
        if not recent:
            return "No audit entries recorded yet."
        lines = [f"=== Audit Summary (last {len(recent)} entries) ==="]
        for e in recent:
            lines.append(
                f"[{e.timestamp}] {e.agent:>12} | {e.severity:>8} | {e.action}"
            )
        pending = self.pending_reviews()
        if pending:
            lines.append(f"\n** {len(pending)} entries require Jeremy's review **")
        return "\n".join(lines)

    def load_from_disk(self) -> None:
        """Reload entries from the JSONL file (for recovery or restart)."""
        if not self._log_file.exists():
            return
        with open(self._log_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    self._entries.append(AuditEntry(**data))
