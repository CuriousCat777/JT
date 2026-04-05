"""Risk scoring — composite score across security domains."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from guardian_one.varys.agent import SecurityAlert


@dataclass
class RiskScore:
    """Composite risk score (0-100) with category breakdown."""
    overall: int
    endpoint: int
    network: int
    identity: int
    data: int
    trend: str  # rising, stable, declining

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "categories": {
                "endpoint": self.endpoint,
                "network": self.network,
                "identity": self.identity,
                "data": self.data,
            },
            "trend": self.trend,
        }


# Severity weights for score calculation
_SEVERITY_WEIGHT = {
    "critical": 25,
    "high": 15,
    "medium": 5,
    "low": 1,
}

# Source-to-category mapping
_SOURCE_CATEGORY = {
    "sigma": "endpoint",
    "anomaly": "identity",
    "network": "network",
    "wazuh": "endpoint",
    "auth": "identity",
    "cloud": "data",
}


class RiskScorer:
    """Computes composite risk scores from active alerts."""

    def __init__(self, max_score: int = 100) -> None:
        self._max = max_score
        self._previous_overall: int | None = None

    def compute(self, alerts: list[Any]) -> RiskScore:
        """Compute risk from the current alert set."""
        scores = {"endpoint": 0, "network": 0, "identity": 0, "data": 0}

        active = [a for a in alerts if a.status.value in ("new", "escalated")]

        for alert in active:
            weight = _SEVERITY_WEIGHT.get(alert.severity.value, 1)
            category = _SOURCE_CATEGORY.get(alert.source, "endpoint")
            scores[category] = min(scores[category] + weight, self._max)

        overall = min(
            sum(scores.values()) // max(len(scores), 1),
            self._max,
        )

        # Determine trend
        if self._previous_overall is None:
            trend = "stable"
        elif overall > self._previous_overall:
            trend = "rising"
        elif overall < self._previous_overall:
            trend = "declining"
        else:
            trend = "stable"

        self._previous_overall = overall

        return RiskScore(
            overall=overall,
            endpoint=scores["endpoint"],
            network=scores["network"],
            identity=scores["identity"],
            data=scores["data"],
            trend=trend,
        )
