"""Behavioral anomaly detection using statistical baselines.

Builds per-user and per-host behavioral profiles and flags deviations.
Uses a lightweight z-score approach by default, with optional PyOD
integration for Isolation Forest when available.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from guardian_one.varys.models import Alert, AlertSeverity, SecurityEvent

logger = logging.getLogger(__name__)


@dataclass
class BehaviorProfile:
    """Statistical profile for a user or host."""
    entity: str                    # user or host identifier
    entity_type: str = "user"     # "user" or "host"
    event_counts: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    last_updated: str = ""
    total_events: int = 0

    def add_observation(self, action: str, count: float) -> None:
        self.event_counts[action].append(count)
        self.total_events += 1
        self.last_updated = datetime.now(timezone.utc).isoformat()

    def mean(self, action: str) -> float:
        values = self.event_counts.get(action, [])
        if not values:
            return 0.0
        return sum(values) / len(values)

    def stddev(self, action: str) -> float:
        values = self.event_counts.get(action, [])
        if len(values) < 2:
            return 0.0
        avg = self.mean(action)
        variance = sum((v - avg) ** 2 for v in values) / len(values)
        return math.sqrt(variance)

    def z_score(self, action: str, value: float) -> float:
        """Compute z-score for a new observation."""
        sd = self.stddev(action)
        if sd == 0:
            return 0.0
        return (value - self.mean(action)) / sd

    @property
    def has_baseline(self) -> bool:
        """Need at least 5 observations to have a meaningful baseline."""
        return self.total_events >= 5


class AnomalyDetector:
    """Detect behavioral anomalies in security events.

    Maintains rolling profiles per user/host and flags deviations
    beyond the configured z-score threshold.
    """

    def __init__(self, z_threshold: float = 3.0) -> None:
        self._z_threshold = z_threshold
        self._user_profiles: dict[str, BehaviorProfile] = {}
        self._host_profiles: dict[str, BehaviorProfile] = {}
        self._window_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._total_anomalies: int = 0

    @property
    def total_anomalies(self) -> int:
        return self._total_anomalies

    @property
    def user_profiles(self) -> dict[str, BehaviorProfile]:
        return dict(self._user_profiles)

    @property
    def host_profiles(self) -> dict[str, BehaviorProfile]:
        return dict(self._host_profiles)

    def observe(self, event: SecurityEvent) -> None:
        """Add an event observation to the behavioral baseline."""
        if event.source_user:
            key = f"user:{event.source_user}"
            self._window_counts[key][event.action] += 1

        if event.host_name:
            key = f"host:{event.host_name}"
            self._window_counts[key][event.action] += 1

    def flush_window(self) -> None:
        """Flush current window counts into profiles as observations.

        Call this at regular intervals (e.g. every hour) to build baselines.
        """
        for entity_key, action_counts in self._window_counts.items():
            entity_type, entity = entity_key.split(":", 1)
            profiles = self._user_profiles if entity_type == "user" else self._host_profiles

            if entity not in profiles:
                profiles[entity] = BehaviorProfile(
                    entity=entity,
                    entity_type=entity_type,
                )

            profile = profiles[entity]
            for action, count in action_counts.items():
                profile.add_observation(action, float(count))

        self._window_counts.clear()

    def detect(self, event: SecurityEvent) -> Alert | None:
        """Check if an event is anomalous based on behavioral profiles.

        Returns an Alert if anomalous, None otherwise.
        """
        anomalies: list[str] = []

        # Check user behavior
        if event.source_user and event.source_user in self._user_profiles:
            profile = self._user_profiles[event.source_user]
            if profile.has_baseline:
                current = self._window_counts.get(f"user:{event.source_user}", {}).get(event.action, 0)
                z = profile.z_score(event.action, float(current))
                if abs(z) > self._z_threshold:
                    anomalies.append(
                        f"User '{event.source_user}' action '{event.action}' "
                        f"z-score={z:.1f} (threshold={self._z_threshold})"
                    )

        # Check host behavior
        if event.host_name and event.host_name in self._host_profiles:
            profile = self._host_profiles[event.host_name]
            if profile.has_baseline:
                current = self._window_counts.get(f"host:{event.host_name}", {}).get(event.action, 0)
                z = profile.z_score(event.action, float(current))
                if abs(z) > self._z_threshold:
                    anomalies.append(
                        f"Host '{event.host_name}' action '{event.action}' "
                        f"z-score={z:.1f} (threshold={self._z_threshold})"
                    )

        if not anomalies:
            return None

        self._total_anomalies += 1

        return Alert(
            title="Behavioral Anomaly Detected",
            description="; ".join(anomalies),
            severity=AlertSeverity.MEDIUM,
            rule_id="VARYS-ANOMALY",
            rule_name="Behavioral Anomaly",
            events=[event],
            source_user=event.source_user,
            host_name=event.host_name,
        )

    def detect_batch(self, events: list[SecurityEvent]) -> list[Alert]:
        """Run anomaly detection on a batch of events."""
        alerts: list[Alert] = []
        for event in events:
            self.observe(event)
            alert = self.detect(event)
            if alert:
                alerts.append(alert)
        return alerts

    def status(self) -> dict[str, Any]:
        return {
            "z_threshold": self._z_threshold,
            "total_anomalies": self._total_anomalies,
            "user_profiles": len(self._user_profiles),
            "host_profiles": len(self._host_profiles),
            "active_window_entities": len(self._window_counts),
        }
