"""Monitoring & Weekly Brief for H.O.M.E. L.I.N.K.

Unified observability for both API infrastructure and smart home systems.

Provides:
    - Real-time service health dashboard (API integrations)
    - Device inventory health and security audit (smart home)
    - Automation engine status and execution history
    - Anomaly detection (latency spikes, error bursts, device offline)
    - Risk scoring (1-5 scale, combining API + device risks)
    - Weekly brief generation covering the full H.O.M.E. L.I.N.K. picture
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from guardian_one.homelink.gateway import Gateway, RequestRecord
from guardian_one.homelink.vault import Vault
from guardian_one.homelink.registry import IntegrationRegistry
from guardian_one.homelink.devices import DeviceRegistry, DeviceStatus
from guardian_one.homelink.automations import AutomationEngine


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
        device_registry: DeviceRegistry | None = None,
        automation_engine: AutomationEngine | None = None,
    ) -> None:
        self._gateway = gateway
        self._vault = vault
        self._registry = registry
        self._devices = device_registry
        self._automations = automation_engine
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
        """Generate the structured weekly status report.

        Covers the full H.O.M.E. L.I.N.K. picture:
        - API integration health (gateway, circuit states, latency)
        - Vault credential status (rotation, expiry)
        - Device inventory health (online/offline, security audit)
        - Automation engine status (rules, scenes, execution history)
        - Detected anomalies across all systems
        """
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

        # Device inventory health
        device_summary: dict[str, Any] = {"registered": False}
        if self._devices:
            audit = self._devices.security_audit()
            device_summary = {
                "registered": True,
                "total_devices": audit["total_devices"],
                "online": audit.get("online", 0),
                "offline": audit.get("offline", 0),
                "security_issues": audit.get("issue_count", 0),
                "device_risk_score": audit.get("risk_score", 0),
                "rooms": len(self._devices.all_rooms()),
                "flipper_profiles": len(self._devices.all_flipper_profiles()),
                "categories": self._devices.device_count_by_category(),
            }
            # Factor device risk into overall risk
            overall_risk = max(overall_risk, audit.get("risk_score", 1))

        # Automation engine status
        automation_summary: dict[str, Any] = {"registered": False}
        if self._automations:
            auto_sum = self._automations.summary()
            automation_summary = {
                "registered": True,
                "total_rules": auto_sum["total_rules"],
                "enabled_rules": auto_sum["enabled_rules"],
                "total_scenes": auto_sum["total_scenes"],
                "total_executions": auto_sum["total_executions"],
                "rules_by_trigger": auto_sum["rules_by_trigger"],
            }

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_risk_score": overall_risk,
            "active_integrations": integrations,
            "vault": vault_health,
            "devices": device_summary,
            "automations": automation_summary,
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
        """Human-readable weekly brief covering full H.O.M.E. L.I.N.K. status."""
        brief = self.weekly_brief()
        lines = [
            "=" * 60,
            "  H.O.M.E. L.I.N.K. — Weekly Status Brief",
            "  Home Operations Management Engine",
            f"  Generated: {brief['generated_at']}",
            f"  Overall Risk Score: {brief['overall_risk_score']}/5",
            "=" * 60,
            "",
        ]

        # --- API Integrations ---
        lines.append("API INTEGRATIONS:")
        if brief["active_integrations"]:
            for svc in brief["active_integrations"]:
                risk_bar = "#" * svc["risk_score"] + "." * (5 - svc["risk_score"])
                lines.append(
                    f"  [{risk_bar}] {svc['service']:20s} | "
                    f"circuit={svc['circuit_state']:10s} | "
                    f"success={svc['success_rate']:.0%} | "
                    f"latency={svc['avg_latency_ms']:.0f}ms"
                )
        else:
            lines.append("  No integrations registered.")

        # --- Vault ---
        lines.append("")
        lines.append("VAULT STATUS:")
        v = brief["vault"]
        lines.append(f"  Total credentials: {v['total_credentials']}")
        lines.append(f"  Due for rotation:  {v['due_for_rotation']}")
        lines.append(f"  Expired:           {v['expired']}")
        if brief["credentials_due_rotation"]:
            lines.append(f"  Rotate now: {', '.join(brief['credentials_due_rotation'])}")

        # --- Devices ---
        lines.append("")
        lines.append("DEVICE INVENTORY:")
        dev = brief["devices"]
        if dev.get("registered"):
            lines.append(f"  Total devices:     {dev['total_devices']}")
            lines.append(f"  Online:            {dev['online']}")
            lines.append(f"  Offline:           {dev['offline']}")
            lines.append(f"  Security issues:   {dev['security_issues']}")
            lines.append(f"  Device risk score: {dev['device_risk_score']}/5")
            lines.append(f"  Rooms mapped:      {dev['rooms']}")
            lines.append(f"  Flipper profiles:  {dev['flipper_profiles']}")
            if dev.get("categories"):
                cats = ", ".join(f"{k}={v}" for k, v in dev["categories"].items())
                lines.append(f"  By category:       {cats}")
        else:
            lines.append("  Device registry not connected.")

        # --- Automations ---
        lines.append("")
        lines.append("AUTOMATION ENGINE:")
        auto = brief["automations"]
        if auto.get("registered"):
            lines.append(f"  Total rules:       {auto['total_rules']}")
            lines.append(f"  Enabled rules:     {auto['enabled_rules']}")
            lines.append(f"  Total scenes:      {auto['total_scenes']}")
            lines.append(f"  Total executions:  {auto['total_executions']}")
            if auto.get("rules_by_trigger"):
                triggers = ", ".join(
                    f"{k}={v}" for k, v in auto["rules_by_trigger"].items() if v > 0
                )
                if triggers:
                    lines.append(f"  By trigger:        {triggers}")
        else:
            lines.append("  Automation engine not connected.")

        # --- Anomalies ---
        if brief["anomalies"]:
            lines.append("")
            lines.append("ANOMALIES DETECTED:")
            for a in brief["anomalies"]:
                lines.append(f"  [{a['severity'].upper():8s}] {a['service']}: {a['description']}")
        else:
            lines.append("")
            lines.append("No anomalies detected.")

        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)
