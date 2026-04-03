"""Risk scoring engine — composite threat scoring for alerts and entities.

Combines multiple signals into a normalized 0.0–1.0 risk score:
- Rule severity weight
- Event volume
- Anomaly z-score (if available)
- MITRE ATT&CK coverage
- Historical frequency
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from guardian_one.varys.models import Alert, AlertSeverity


# Severity base weights
_SEVERITY_WEIGHTS: dict[AlertSeverity, float] = {
    AlertSeverity.LOW: 0.15,
    AlertSeverity.MEDIUM: 0.40,
    AlertSeverity.HIGH: 0.70,
    AlertSeverity.CRITICAL: 0.95,
}

# MITRE tactics that indicate advanced threats get bonus weight
_HIGH_RISK_TACTICS = {
    "TA0004",  # Privilege Escalation
    "TA0005",  # Defense Evasion
    "TA0006",  # Credential Access
    "TA0008",  # Lateral Movement
    "TA0010",  # Exfiltration
    "TA0040",  # Impact
}


@dataclass
class EntityRisk:
    """Composite risk profile for a user, host, or IP."""
    entity: str
    entity_type: str        # "user", "host", "ip"
    risk_score: float = 0.0
    alert_count: int = 0
    tactics_seen: set[str] = None
    last_alert_time: str = ""

    def __post_init__(self):
        if self.tactics_seen is None:
            self.tactics_seen = set()

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity": self.entity,
            "entity_type": self.entity_type,
            "risk_score": round(self.risk_score, 3),
            "alert_count": self.alert_count,
            "tactics_seen": sorted(self.tactics_seen),
            "last_alert_time": self.last_alert_time,
        }


class RiskScorer:
    """Calculate composite risk scores for alerts and entities."""

    def __init__(self) -> None:
        self._entity_risks: dict[str, EntityRisk] = {}
        self._alert_history: list[str] = []

    @property
    def entity_risks(self) -> dict[str, EntityRisk]:
        return dict(self._entity_risks)

    def score_alert(self, alert: Alert) -> float:
        """Calculate a composite risk score for an alert (0.0–1.0)."""
        score = 0.0

        # Base severity weight (40% of score)
        severity_base = _SEVERITY_WEIGHTS.get(alert.severity, 0.3)
        score += severity_base * 0.4

        # Event volume factor (20% of score)
        event_count = len(alert.events)
        volume_factor = min(event_count / 20.0, 1.0)  # Cap at 20 events
        score += volume_factor * 0.2

        # MITRE ATT&CK factor (20% of score)
        if alert.mitre_tactic in _HIGH_RISK_TACTICS:
            score += 0.2
        elif alert.mitre_tactic:
            score += 0.1

        # Recurrence factor (20% of score)
        rule_count = sum(1 for rid in self._alert_history if rid == alert.rule_id)
        recurrence = min(rule_count / 10.0, 1.0)
        score += recurrence * 0.2

        # Clamp to [0, 1]
        score = max(0.0, min(1.0, score))

        # Track this alert
        self._alert_history.append(alert.rule_id)
        alert.risk_score = score

        # Update entity risk profiles
        self._update_entity_risk(alert, score)

        return score

    def score_batch(self, alerts: list[Alert]) -> list[float]:
        """Score a batch of alerts."""
        return [self.score_alert(a) for a in alerts]

    def _update_entity_risk(self, alert: Alert, score: float) -> None:
        """Update risk profiles for entities mentioned in the alert."""
        entities = []
        if alert.source_user:
            entities.append((alert.source_user, "user"))
        if alert.source_ip:
            entities.append((alert.source_ip, "ip"))
        if alert.host_name:
            entities.append((alert.host_name, "host"))

        for entity, etype in entities:
            key = f"{etype}:{entity}"
            if key not in self._entity_risks:
                self._entity_risks[key] = EntityRisk(
                    entity=entity, entity_type=etype
                )
            er = self._entity_risks[key]
            er.alert_count += 1
            er.last_alert_time = alert.timestamp
            if alert.mitre_tactic:
                er.tactics_seen.add(alert.mitre_tactic)
            # Running max for entity risk
            er.risk_score = max(er.risk_score, score)

    def get_high_risk_entities(self, threshold: float = 0.6) -> list[EntityRisk]:
        """Return entities with risk score above threshold."""
        return sorted(
            [er for er in self._entity_risks.values() if er.risk_score >= threshold],
            key=lambda e: e.risk_score,
            reverse=True,
        )

    def status(self) -> dict[str, Any]:
        return {
            "total_scored": len(self._alert_history),
            "tracked_entities": len(self._entity_risks),
            "high_risk_entities": len(self.get_high_risk_entities()),
        }
