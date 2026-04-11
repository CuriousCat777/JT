"""Audit logging — all agent decisions are recorded and reviewable.

The in-memory entry list is capped at ``max_memory_entries`` (default 10 000).
The JSONL file on disk is append-only and keeps the full history.  When the
log file exceeds ``max_file_bytes`` (default 10 MB) it is rotated:
    audit.jsonl → audit.jsonl.1 (then audit.jsonl.2, etc.)
"""

from __future__ import annotations

import json
import os
import threading
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from guardian_one.database.bridge import DatabaseBridge


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


# Default limits
_DEFAULT_MAX_MEMORY = 10_000
_DEFAULT_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
_DEFAULT_MAX_ROTATED = 5  # keep up to audit.jsonl.5


class AuditLog:
    """Thread-safe, append-only audit log with memory cap and file rotation.

    Writes to a JSONL (JSON Lines) file so entries can be streamed and
    searched without loading the entire log into memory.

    Memory cap:
        Only the most recent ``max_memory_entries`` are kept in RAM.
        Older entries are still preserved on disk.

    File rotation:
        When the JSONL file exceeds ``max_file_bytes``, it is rotated
        (audit.jsonl → audit.jsonl.1 → audit.jsonl.2 …).
    """

    def __init__(
        self,
        log_dir: Path | None = None,
        max_memory_entries: int = _DEFAULT_MAX_MEMORY,
        max_file_bytes: int = _DEFAULT_MAX_FILE_BYTES,
        max_rotated_files: int = _DEFAULT_MAX_ROTATED,
        db_bridge: "DatabaseBridge | None" = None,
    ) -> None:
        self._log_dir = log_dir or Path("logs")
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._log_dir / "audit.jsonl"
        self._lock = threading.Lock()
        self._max_memory = max_memory_entries
        self._max_file_bytes = max_file_bytes
        self._max_rotated = max_rotated_files
        self._entries: deque[AuditEntry] = deque(maxlen=max_memory_entries)
        self._total_recorded: int = 0
        # Optional database bridge — when set, every record() call
        # also writes the entry to ``system_logs``. Best-effort:
        # failures are caught so an unavailable DB never blocks the
        # canonical JSONL write.
        self._db_bridge = db_bridge

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
            self._total_recorded += 1
            with open(self._log_file, "a") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
            self._maybe_rotate()
        # Mirror to the database outside the lock so a slow DB write
        # can't block concurrent JSONL writers. Any failure is
        # swallowed — the canonical JSONL file is still authoritative.
        if self._db_bridge is not None:
            try:
                self._db_bridge.log_audit_entry(
                    agent=agent,
                    action=action,
                    severity=severity.value,
                    details=details,
                    component="audit",
                    source="audit_runtime",
                )
            except Exception:  # noqa: BLE001
                pass
        return entry

    def _maybe_rotate(self) -> None:
        """Rotate the JSONL file if it exceeds the size limit.

        Must be called while holding ``self._lock``.
        """
        try:
            if self._log_file.stat().st_size < self._max_file_bytes:
                return
        except OSError:
            return

        # Shift existing rotated files: .5 → delete, .4 → .5, … .1 → .2
        for i in range(self._max_rotated, 0, -1):
            src = self._log_dir / f"audit.jsonl.{i}"
            if i == self._max_rotated:
                src.unlink(missing_ok=True)
            elif src.exists():
                src.rename(self._log_dir / f"audit.jsonl.{i + 1}")

        # Current → .1
        if self._log_file.exists():
            self._log_file.rename(self._log_dir / "audit.jsonl.1")

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
        entries = list(self._entries)
        recent = entries[-last_n:]
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
        if self._total_recorded > self._max_memory:
            lines.append(
                f"(showing {len(self._entries)} of {self._total_recorded} total entries — "
                f"older entries available on disk)"
            )
        return "\n".join(lines)

    def load_from_disk(self) -> None:
        """Reload entries from the JSONL file (for recovery or restart).

        Only the last ``max_memory_entries`` are loaded into RAM.
        """
        if not self._log_file.exists():
            return
        entries: list[AuditEntry] = []
        with open(self._log_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entries.append(AuditEntry(**data))
                except (json.JSONDecodeError, TypeError):
                    continue
        # Only keep the most recent entries in memory
        for entry in entries[-self._max_memory:]:
            self._entries.append(entry)
        self._total_recorded = len(entries)

    @property
    def total_recorded(self) -> int:
        """Total entries ever recorded (may exceed in-memory count)."""
        return self._total_recorded
