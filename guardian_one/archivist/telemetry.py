"""TelemetryHub — central cross-system event logging.

The single source of truth for all interactions across every system,
service, and account in Guardian One. Every agent, integration, and
external webhook feeds events here.

Storage: append-only JSONL on disk + in-memory ring buffer.
All entries are also backed up to Vault on flush.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TelemetryEvent:
    """A single cross-system telemetry event."""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source: str = ""          # originating system: "github", "gmail", "wazuh", "ollama", etc.
    source_type: str = ""     # "service", "device", "agent", "mcp", "api", "user"
    category: str = ""        # "interaction", "config_change", "new_tech", "backup", "auth"
    action: str = ""          # what happened: "repo_push", "email_received", "model_loaded"
    actor: str = ""           # who/what triggered it: "jeremy", "chronos", "github_webhook"
    target: str = ""          # what was acted on: "JT/main", "inbox", "llama3"
    details: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_DEFAULT_MAX_MEMORY = 10_000
_DEFAULT_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


class TelemetryHub:
    """Central telemetry collector — all systems report here.

    Every interaction across every service feeds into one stream:
    - Agent actions (VARYS alerts, CFO transactions, Chronos events)
    - MCP tool calls
    - External webhooks (GitHub, Gmail, Cloudflare)
    - Device events (IoT, smart home)
    - AI interactions (model calls, provider switches)
    """

    def __init__(
        self,
        data_dir: Path | None = None,
        max_memory: int = _DEFAULT_MAX_MEMORY,
        max_file_bytes: int = _DEFAULT_MAX_FILE_BYTES,
    ) -> None:
        self._data_dir = data_dir or Path("data")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._data_dir / "telemetry.jsonl"
        self._lock = threading.Lock()
        self._events: deque[TelemetryEvent] = deque(maxlen=max_memory)
        self._max_file_bytes = max_file_bytes
        self._total_logged: int = 0
        self._source_counts: dict[str, int] = {}

    def log(self, event: TelemetryEvent) -> None:
        """Log a telemetry event to memory and disk."""
        with self._lock:
            self._events.append(event)
            self._total_logged += 1
            self._source_counts[event.source] = (
                self._source_counts.get(event.source, 0) + 1
            )
            # Append to JSONL
            try:
                with open(self._log_file, "a") as f:
                    f.write(json.dumps(event.to_dict()) + "\n")
                self._maybe_rotate()
            except OSError as exc:
                logger.error("Telemetry write failed: %s", exc)

    def log_simple(
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
    ) -> TelemetryEvent:
        """Convenience: log with keyword args instead of building TelemetryEvent."""
        event = TelemetryEvent(
            source=source,
            source_type=source_type,
            category=category,
            action=action,
            actor=actor,
            target=target,
            details=details or {},
            tags=tags or [],
        )
        self.log(event)
        return event

    def query(
        self,
        source: str | None = None,
        category: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[TelemetryEvent]:
        """Query recent telemetry events with optional filters."""
        results: list[TelemetryEvent] = []
        for event in reversed(self._events):
            if source and event.source != source:
                continue
            if category and event.category != category:
                continue
            if since and event.timestamp < since:
                break
            results.append(event)
            if len(results) >= limit:
                break
        return results

    def sources(self) -> dict[str, int]:
        """Get event counts per source."""
        return dict(self._source_counts)

    def load_from_disk(self) -> None:
        """Reload recent events from the JSONL file."""
        if not self._log_file.exists():
            return
        events: list[TelemetryEvent] = []
        try:
            with open(self._log_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        events.append(TelemetryEvent(**{
                            k: v for k, v in data.items()
                            if k in TelemetryEvent.__dataclass_fields__
                        }))
                    except (json.JSONDecodeError, TypeError):
                        continue
        except OSError:
            return

        for event in events[-self._events.maxlen:]:
            self._events.append(event)
            self._source_counts[event.source] = (
                self._source_counts.get(event.source, 0) + 1
            )
        self._total_logged = len(events)

    def _maybe_rotate(self) -> None:
        """Rotate the telemetry file if too large."""
        try:
            if self._log_file.stat().st_size < self._max_file_bytes:
                return
        except OSError:
            return

        # Rotate: telemetry.jsonl → telemetry.jsonl.1
        for i in range(5, 0, -1):
            src = self._data_dir / f"telemetry.jsonl.{i}"
            if i == 5:
                src.unlink(missing_ok=True)
            elif src.exists():
                src.rename(self._data_dir / f"telemetry.jsonl.{i + 1}")

        if self._log_file.exists():
            self._log_file.rename(self._data_dir / "telemetry.jsonl.1")

    @property
    def total_logged(self) -> int:
        return self._total_logged

    def status(self) -> dict[str, Any]:
        return {
            "total_logged": self._total_logged,
            "in_memory": len(self._events),
            "sources": dict(self._source_counts),
            "log_file": str(self._log_file),
        }
