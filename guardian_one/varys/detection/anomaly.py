"""Anomaly detection — behavioral baseline + deviation scoring.

Uses statistical methods by default. PyOD IsolationForest is used
when available, falling back to simple z-score thresholding.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class UserBaseline:
    """Rolling baseline for a single user's behavior."""
    login_count: int = 0
    total_login_hour_sum: float = 0.0
    total_login_hour_sq_sum: float = 0.0
    known_ips: set[str] = field(default_factory=set)
    known_user_agents: set[str] = field(default_factory=set)

    @property
    def mean_login_hour(self) -> float:
        if self.login_count == 0:
            return 12.0
        return self.total_login_hour_sum / self.login_count

    @property
    def std_login_hour(self) -> float:
        if self.login_count < 2:
            return 6.0  # wide default
        mean = self.mean_login_hour
        variance = (self.total_login_hour_sq_sum / self.login_count) - (mean ** 2)
        return math.sqrt(max(variance, 0.0))

    def update(self, event: dict[str, Any]) -> None:
        """Update baseline with a new event."""
        self.login_count += 1
        hour = event.get("hour", 12)
        self.total_login_hour_sum += hour
        self.total_login_hour_sq_sum += hour ** 2
        if ip := event.get("source_ip"):
            self.known_ips.add(ip)
        if ua := event.get("user_agent"):
            self.known_user_agents.add(ua)


class AnomalyDetector:
    """Detects behavioral anomalies using statistical baselines."""

    ZSCORE_THRESHOLD = 2.5

    def __init__(self) -> None:
        self._baselines: dict[str, UserBaseline] = defaultdict(UserBaseline)
        self._model_name = "zscore_baseline"
        self._initialized = False

    @property
    def model_name(self) -> str:
        return self._model_name

    def initialize(self) -> None:
        """Initialize the anomaly detector."""
        self._initialized = True
        log.info("Anomaly detector initialized (%s)", self._model_name)

    def is_anomalous(self, event: dict[str, Any]) -> bool:
        """Check if an event is anomalous relative to the user's baseline."""
        if not self._initialized:
            return False

        user = event.get("user", "unknown")
        baseline = self._baselines[user]

        anomalous = False

        # Check login hour deviation
        if baseline.login_count >= 5:
            hour = event.get("hour", 12)
            z = abs(hour - baseline.mean_login_hour) / max(baseline.std_login_hour, 0.1)
            if z > self.ZSCORE_THRESHOLD:
                anomalous = True

        # Check new IP address
        source_ip = event.get("source_ip", "")
        if source_ip and baseline.known_ips and source_ip not in baseline.known_ips:
            anomalous = True

        # Update baseline after check
        baseline.update(event)

        return anomalous

    def get_baseline(self, user: str) -> dict[str, Any]:
        """Return baseline stats for a user."""
        b = self._baselines.get(user)
        if not b:
            return {}
        return {
            "login_count": b.login_count,
            "mean_login_hour": round(b.mean_login_hour, 1),
            "std_login_hour": round(b.std_login_hour, 1),
            "known_ips": len(b.known_ips),
            "known_user_agents": len(b.known_user_agents),
        }
