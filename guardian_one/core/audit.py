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


# ---------------------------------------------------------------------------
# Change types for the ChangeLogger
# ---------------------------------------------------------------------------


class ChangeType(Enum):
    """Categories of system changes tracked by the ChangeLogger."""
    FEATURE = "feature"
    BUGFIX = "bugfix"
    CONFIG = "config"
    SECURITY = "security"
    AGENT = "agent"
    INTEGRATION = "integration"
    DEPLOYMENT = "deployment"
    DATA = "data"
    REFACTOR = "refactor"


@dataclass
class ChangeEntry:
    """A documented change to the Guardian One system."""
    timestamp: str
    agent: str
    change_type: str
    title: str
    description: str
    files_affected: list[str] = field(default_factory=list)
    breaking: bool = False
    requires_review: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def format_entry(self) -> str:
        """Human-readable single-entry format."""
        flag = " [BREAKING]" if self.breaking else ""
        review = " [NEEDS REVIEW]" if self.requires_review else ""
        lines = [
            f"[{self.timestamp}] {self.change_type.upper()}{flag}{review}",
            f"  Agent: {self.agent}",
            f"  Title: {self.title}",
            f"  Description: {self.description}",
        ]
        if self.files_affected:
            lines.append(f"  Files: {', '.join(self.files_affected)}")
        return "\n".join(lines)


class ChangeLogger:
    """Tracks and documents all changes made to the Guardian One system.

    Stores changes in a separate JSONL file (changelog.jsonl) alongside
    the audit log.  Provides querying, summary, and markdown export.
    """

    _DEFAULT_MAX_MEMORY = 5_000
    _DEFAULT_MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB
    _DEFAULT_MAX_ROTATED = 3

    def __init__(
        self,
        log_dir: Path | None = None,
        max_memory_entries: int = _DEFAULT_MAX_MEMORY,
        max_file_bytes: int = _DEFAULT_MAX_FILE_BYTES,
        max_rotated_files: int = _DEFAULT_MAX_ROTATED,
    ) -> None:
        self._log_dir = log_dir or Path("logs")
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._log_dir / "changelog.jsonl"
        self._lock = threading.Lock()
        self._max_memory = max_memory_entries
        self._max_file_bytes = max_file_bytes
        self._max_rotated = max_rotated_files
        self._entries: deque[ChangeEntry] = deque(maxlen=max_memory_entries)
        self._total_recorded: int = 0

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        agent: str,
        change_type: ChangeType,
        title: str,
        description: str,
        files_affected: list[str] | None = None,
        breaking: bool = False,
        requires_review: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> ChangeEntry:
        """Record a documented change."""
        entry = ChangeEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent=agent,
            change_type=change_type.value,
            title=title,
            description=description,
            files_affected=files_affected or [],
            breaking=breaking,
            requires_review=requires_review,
            metadata=metadata or {},
        )
        with self._lock:
            self._entries.append(entry)
            self._total_recorded += 1
            with open(self._log_file, "a") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
            self._maybe_rotate()
        return entry

    def _maybe_rotate(self) -> None:
        """Rotate changelog file if it exceeds the size limit."""
        try:
            if self._log_file.stat().st_size < self._max_file_bytes:
                return
        except OSError:
            return
        for i in range(self._max_rotated, 0, -1):
            src = self._log_dir / f"changelog.jsonl.{i}"
            if i == self._max_rotated:
                src.unlink(missing_ok=True)
            elif src.exists():
                src.rename(self._log_dir / f"changelog.jsonl.{i + 1}")
        if self._log_file.exists():
            self._log_file.rename(self._log_dir / "changelog.jsonl.1")

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def query(
        self,
        agent: str | None = None,
        change_type: ChangeType | None = None,
        since: str | None = None,
        breaking_only: bool = False,
        limit: int = 50,
    ) -> list[ChangeEntry]:
        """Filter changelog entries in memory."""
        results: list[ChangeEntry] = []
        for entry in reversed(self._entries):
            if agent and entry.agent != agent:
                continue
            if change_type and entry.change_type != change_type.value:
                continue
            if since and entry.timestamp < since:
                break
            if breaking_only and not entry.breaking:
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results

    def pending_reviews(self) -> list[ChangeEntry]:
        """Return changes that need Jeremy's review."""
        return [e for e in self._entries if e.requires_review]

    # ------------------------------------------------------------------
    # Output formats
    # ------------------------------------------------------------------

    def summary(self, last_n: int = 20) -> str:
        """Human-readable summary of recent changes."""
        entries = list(self._entries)
        recent = entries[-last_n:]
        if not recent:
            return "No changes recorded yet."
        lines = [f"=== Changelog (last {len(recent)} changes) ==="]
        for e in recent:
            flag = " *BREAKING*" if e.breaking else ""
            lines.append(
                f"[{e.timestamp}] {e.change_type:>12} | {e.agent:>14} | "
                f"{e.title}{flag}"
            )
        pending = self.pending_reviews()
        if pending:
            lines.append(f"\n** {len(pending)} changes need Jeremy's review **")
        return "\n".join(lines)

    def to_markdown(self, last_n: int = 50) -> str:
        """Export recent changes as a Markdown changelog."""
        entries = list(self._entries)
        recent = entries[-last_n:]
        if not recent:
            return "# Changelog\n\nNo changes recorded yet.\n"

        lines = ["# Guardian One Changelog\n"]

        # Group by date
        by_date: dict[str, list[ChangeEntry]] = {}
        for e in recent:
            date = e.timestamp[:10]
            by_date.setdefault(date, []).append(e)

        for date in sorted(by_date.keys(), reverse=True):
            lines.append(f"## {date}\n")
            for e in by_date[date]:
                flag = " **BREAKING**" if e.breaking else ""
                review = " _needs review_" if e.requires_review else ""
                lines.append(
                    f"- **[{e.change_type.upper()}]** {e.title}{flag}{review}  "
                )
                lines.append(f"  _{e.agent}_ — {e.description}")
                if e.files_affected:
                    lines.append(
                        f"  Files: `{'`, `'.join(e.files_affected)}`"
                    )
                lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load_from_disk(self) -> None:
        """Reload entries from the JSONL file."""
        if not self._log_file.exists():
            return
        entries: list[ChangeEntry] = []
        with open(self._log_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entries.append(ChangeEntry(**data))
                except (json.JSONDecodeError, TypeError):
                    continue
        for entry in entries[-self._max_memory:]:
            self._entries.append(entry)
        self._total_recorded = len(entries)

    @property
    def total_recorded(self) -> int:
        return self._total_recorded
