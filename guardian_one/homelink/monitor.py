"""Monitoring & Weekly Brief for H.O.M.E. L.I.N.K.

Tracks API health, detects anomalies, and generates structured reports
for Jeremy's review.

Provides:
    - Real-time service health dashboard
    - Anomaly detection (latency spikes, error bursts)
    - Risk scoring (1-5 scale)
    - Weekly brief generation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from guardian_one.homelink.gateway import Gateway, RequestRecord
from guardian_one.homelink.vault import Vault
from guardian_one.homelink.registry import IntegrationRegistry


@dataclass
class AnomalyAlert:
    """Detected anomaly in API behaviour."""
    service: str
    anomaly_type: str  # latency_spike, error_burst, auth_failure, circuit_open
    description: str
    severity: str      # low, medium, high, critical
    detected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class ServiceHealthSnapshot:
    """Point-in-time health of a single service."""
    service: str
    circuit_state: str
    success_rate: float
    avg_latency_ms: float
    rate_limit_remaining: int
    risk_score: int  # 1 (healthy) to 5 (critical)


class Monitor:
    """Observability engine for H.O.M.E. L.I.N.K."""

    def __init__(
        self,
        gateway: Gateway,
        vault: Vault,
        registry: IntegrationRegistry,
    ) -> None:
        self._gateway = gateway
        self._vault = vault
        self._registry = registry
        self._anomalies: list[AnomalyAlert] = []

    # ------------------------------------------------------------------
    # Health assessment
    # ------------------------------------------------------------------

    def assess_service(self, service: str) -> ServiceHealthSnapshot:
        """Calculate health snapshot and risk score for a service."""
        status = self._gateway.service_status(service)
        if "error" in status:
            return ServiceHealthSnapshot(
                service=service, circuit_state="unknown",
                success_rate=0, avg_latency_ms=0,
                rate_limit_remaining=0, risk_score=5,
            )

        risk = self._calculate_risk(status)
        return ServiceHealthSnapshot(
            service=service,
            circuit_state=status["circuit_state"],
            success_rate=status["success_rate"],
            avg_latency_ms=status["avg_latency_ms"],
            rate_limit_remaining=status["rate_limit_remaining"],
            risk_score=risk,
        )

    @staticmethod
    def _calculate_risk(status: dict[str, Any]) -> int:
        """Risk score 1 (healthy) to 5 (critical)."""
        score = 1

        if status["circuit_state"] == "open":
            score = max(score, 5)
        elif status["circuit_state"] == "half_open":
            score = max(score, 3)

        sr = status["success_rate"]
        if sr < 0.5:
            score = max(score, 5)
        elif sr < 0.8:
            score = max(score, 4)
        elif sr < 0.95:
            score = max(score, 2)

        if status["avg_latency_ms"] > 5000:
            score = max(score, 4)
        elif status["avg_latency_ms"] > 2000:
            score = max(score, 3)

        if status["rate_limit_remaining"] == 0:
            score = max(score, 3)

        return score

    def all_health(self) -> list[ServiceHealthSnapshot]:
        return [self.assess_service(s) for s in self._gateway.list_services()]

    # ------------------------------------------------------------------
    # Anomaly detection
    # ------------------------------------------------------------------

    def detect_anomalies(self) -> list[AnomalyAlert]:
        """Scan all services for anomalies."""
        new_anomalies: list[AnomalyAlert] = []

        for service in self._gateway.list_services():
            status = self._gateway.service_status(service)
            if "error" in status:
                continue

            if status["circuit_state"] == "open":
                new_anomalies.append(AnomalyAlert(
                    service=service,
                    anomaly_type="circuit_open",
                    description=f"Circuit breaker OPEN for {service} — service is failing.",
                    severity="critical",
                ))

            if status["success_rate"] < 0.8 and status["recent_requests"] > 5:
                new_anomalies.append(AnomalyAlert(
                    service=service,
                    anomaly_type="error_burst",
                    description=f"Error rate {(1 - status['success_rate'])*100:.0f}% for {service}.",
                    severity="high",
                ))

            if status["avg_latency_ms"] > 5000:
                new_anomalies.append(AnomalyAlert(
                    service=service,
                    anomaly_type="latency_spike",
                    description=f"Average latency {status['avg_latency_ms']:.0f}ms for {service}.",
                    severity="medium",
                ))

        self._anomalies.extend(new_anomalies)
        return new_anomalies

    # ------------------------------------------------------------------
    # Weekly brief
    # ------------------------------------------------------------------

    def weekly_brief(self) -> dict[str, Any]:
        """Generate the structured weekly status report."""
        health = self.all_health()
        vault_health = self._vault.health_report()
        anomalies = self.detect_anomalies()

        overall_risk = max((h.risk_score for h in health), default=1)

        integrations = []
        for h in health:
            record = self._registry.get(h.service)
            integrations.append({
                "service": h.service,
                "circuit_state": h.circuit_state,
                "success_rate": h.success_rate,
                "avg_latency_ms": h.avg_latency_ms,
                "risk_score": h.risk_score,
                "auth_method": record.auth_method if record else "unknown",
            })

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_risk_score": overall_risk,
            "active_integrations": integrations,
            "vault": vault_health,
            "anomalies": [
                {
                    "service": a.service,
                    "type": a.anomaly_type,
                    "description": a.description,
                    "severity": a.severity,
                }
                for a in anomalies
            ],
            "credentials_due_rotation": [
                m.key_name for m in self._vault.credentials_due_for_rotation()
            ],
            "credentials_expired": [
                m.key_name for m in self._vault.expired_credentials()
            ],
        }

    def weekly_brief_text(self) -> str:
        """Human-readable weekly brief."""
        brief = self.weekly_brief()
        lines = [
            "=" * 60,
            "  H.O.M.E. L.I.N.K. — Weekly Security & API Brief",
            f"  Generated: {brief['generated_at']}",
            f"  Overall Risk Score: {brief['overall_risk_score']}/5",
            "=" * 60,
            "",
            "ACTIVE INTEGRATIONS:",
        ]

        for svc in brief["active_integrations"]:
            risk_bar = "#" * svc["risk_score"] + "." * (5 - svc["risk_score"])
            lines.append(
                f"  [{risk_bar}] {svc['service']:20s} | "
                f"circuit={svc['circuit_state']:10s} | "
                f"success={svc['success_rate']:.0%} | "
                f"latency={svc['avg_latency_ms']:.0f}ms"
            )

        lines.append("")
        lines.append("VAULT STATUS:")
        v = brief["vault"]
        lines.append(f"  Total credentials: {v['total_credentials']}")
        lines.append(f"  Due for rotation:  {v['due_for_rotation']}")
        lines.append(f"  Expired:           {v['expired']}")

        if brief["credentials_due_rotation"]:
            lines.append(f"  Rotate now: {', '.join(brief['credentials_due_rotation'])}")

        if brief["anomalies"]:
            lines.append("")
            lines.append("ANOMALIES DETECTED:")
            for a in brief["anomalies"]:
                lines.append(f"  [{a['severity'].upper():8s}] {a['service']}: {a['description']}")

        if not brief["anomalies"]:
            lines.append("")
            lines.append("No anomalies detected.")

        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)
