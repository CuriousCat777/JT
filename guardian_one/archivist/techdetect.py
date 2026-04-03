"""TechDetector — auto-detect new technology, services, and accounts.

Monitors the telemetry stream for first-seen sources, tools, APIs,
and devices. When new tech is detected:
1. Log it as a TechRecord
2. Back up the interaction to Vault
3. Flag it for Jeremy's review
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TechRecord:
    """A detected technology/service/tool/device."""
    name: str
    tech_type: str = ""       # "service", "device", "tool", "mcp_server", "ai_model", "api"
    first_seen: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_seen: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    interaction_count: int = 1
    source_event: str = ""    # The action that triggered detection
    details: dict[str, Any] = field(default_factory=dict)
    backed_up: bool = False
    reviewed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TechDetector:
    """Monitor for new technology entering the ecosystem.

    Tracks known tech and flags anything new. Persists the registry
    to disk so it survives restarts.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or Path("data")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._registry_file = self._data_dir / "tech_registry.json"
        self._registry: dict[str, TechRecord] = {}
        self._new_detections: list[TechRecord] = []

    @property
    def registry(self) -> dict[str, TechRecord]:
        return dict(self._registry)

    @property
    def new_detections(self) -> list[TechRecord]:
        """Get and clear the new detections queue."""
        detections = list(self._new_detections)
        self._new_detections.clear()
        return detections

    def check(self, source: str, source_type: str = "service", action: str = "", details: dict[str, Any] | None = None) -> TechRecord | None:
        """Check if a source is new tech. Returns TechRecord if first-seen."""
        key = f"{source_type}:{source}"

        if key in self._registry:
            # Known tech — update last_seen and count
            record = self._registry[key]
            record.last_seen = datetime.now(timezone.utc).isoformat()
            record.interaction_count += 1
            return None

        # New tech detected!
        record = TechRecord(
            name=source,
            tech_type=source_type,
            source_event=action,
            details=details or {},
        )
        self._registry[key] = record
        self._new_detections.append(record)

        logger.info("New tech detected: %s (%s)", source, source_type)
        return record

    def save(self) -> None:
        """Persist the tech registry to disk."""
        data = {
            key: record.to_dict()
            for key, record in self._registry.items()
        }
        try:
            with open(self._registry_file, "w") as f:
                json.dump(data, f, indent=2)
        except OSError as exc:
            logger.error("Failed to save tech registry: %s", exc)

    def load(self) -> None:
        """Load the tech registry from disk."""
        if not self._registry_file.exists():
            return
        try:
            with open(self._registry_file) as f:
                data = json.load(f)
            for key, record_data in data.items():
                self._registry[key] = TechRecord(**{
                    k: v for k, v in record_data.items()
                    if k in TechRecord.__dataclass_fields__
                })
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.error("Failed to load tech registry: %s", exc)

    def get_unreviewed(self) -> list[TechRecord]:
        """Get all tech records that haven't been reviewed by Jeremy."""
        return [r for r in self._registry.values() if not r.reviewed]

    def get_unbacked_up(self) -> list[TechRecord]:
        """Get all tech records not yet backed up to Vault."""
        return [r for r in self._registry.values() if not r.backed_up]

    def mark_reviewed(self, name: str, tech_type: str = "service") -> bool:
        """Mark a tech record as reviewed."""
        key = f"{tech_type}:{name}"
        if key in self._registry:
            self._registry[key].reviewed = True
            return True
        return False

    def mark_backed_up(self, name: str, tech_type: str = "service") -> bool:
        """Mark a tech record as backed up to Vault."""
        key = f"{tech_type}:{name}"
        if key in self._registry:
            self._registry[key].backed_up = True
            return True
        return False

    def status(self) -> dict[str, Any]:
        return {
            "total_tracked": len(self._registry),
            "unreviewed": len(self.get_unreviewed()),
            "unbacked_up": len(self.get_unbacked_up()),
            "by_type": self._count_by_type(),
        }

    def _count_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self._registry.values():
            counts[record.tech_type] = counts.get(record.tech_type, 0) + 1
        return counts
