"""IoT Sentinel Agent — Sovereign local-first IoT security & control.

The IoT Sentinel is the AI-driven guardian of Jeremy's local network and
smart home. It combines three roles:

1. **Network Monitor** — Continuous LAN scanning + anomaly detection
2. **Risk Summarizer** — Converts logs/events to plain-language alerts
3. **Recommendation Engine** — Suggests block/isolate/ignore with
   mandatory user approval (no autonomous destructive actions)

Design principles:
- LAN-first, internet optional
- Default-deny, zero-trust
- Offline-capable core functions
- Human-in-the-loop for all destructive actions
- Fail-closed security (unknown = untrusted)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig
from guardian_one.homelink.mqtt_broker import MqttBrokerClient, MqttBrokerConfig, MqttMessage
from guardian_one.homelink.network_monitor import (
    AlertSeverity,
    AnomalyType,
    NetworkAnomaly,
    NetworkMonitor,
)
from guardian_one.homelink.network_scanner import (
    DeviceClassification,
    DiscoveredDevice,
    NetworkScanner,
)


# ---------------------------------------------------------------------------
# Recommendation model
# ---------------------------------------------------------------------------

class RecommendationAction:
    """Possible actions the sentinel can recommend (user approval required)."""
    BLOCK = "block_device"
    ISOLATE = "isolate_vlan"
    QUARANTINE = "quarantine"
    IGNORE = "ignore"
    MONITOR = "monitor_closely"
    UPDATE_FIRMWARE = "update_firmware"
    CHANGE_PASSWORD = "change_password"


class IoTSentinel(BaseAgent):
    """Sovereign IoT security agent — monitors, summarizes, recommends.

    Combines network scanning, MQTT event processing, and AI-assisted
    risk summarization into a single agent that protects the local network.
    """

    def __init__(
        self,
        config: AgentConfig,
        audit: AuditLog,
        scanner: NetworkScanner | None = None,
        monitor: NetworkMonitor | None = None,
        mqtt: MqttBrokerClient | None = None,
    ) -> None:
        super().__init__(config, audit)
        subnet = config.custom.get("subnet", "192.168.1.0/24")
        scan_interval = config.custom.get("scan_interval_seconds", 300)

        self._scanner = scanner or NetworkScanner(subnet=subnet, audit=audit)
        self._monitor = monitor or NetworkMonitor(
            scanner=self._scanner, audit=audit,
            scan_interval_seconds=scan_interval,
        )
        self._mqtt = mqtt or MqttBrokerClient(audit=audit)

        # State
        self._recommendations: list[dict[str, Any]] = []
        self._pending_approvals: list[dict[str, Any]] = []
        self._action_history: list[dict[str, Any]] = []
        self._risk_summaries: list[dict[str, Any]] = []
        self._last_scan: str = ""
        self._alerts: list[str] = []

        # Wire up anomaly callbacks
        self._monitor.on_anomaly(self._handle_anomaly)

    @property
    def scanner(self) -> NetworkScanner:
        return self._scanner

    @property
    def monitor(self) -> NetworkMonitor:
        return self._monitor

    @property
    def mqtt(self) -> MqttBrokerClient:
        return self._mqtt

    # ------------------------------------------------------------------
    # BaseAgent lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        self._set_status(AgentStatus.RUNNING)

        # Load known MACs from config
        known_macs = set(self.config.custom.get("known_macs", []))
        if known_macs:
            self._monitor.set_baseline(known_macs)

        # Connect MQTT (non-blocking, falls back to local mode)
        mqtt_config = self.config.custom.get("mqtt", {})
        if mqtt_config:
            self._mqtt = MqttBrokerClient(
                config=MqttBrokerConfig(
                    host=mqtt_config.get("host", "localhost"),
                    port=mqtt_config.get("port", 1883),
                    use_tls=mqtt_config.get("use_tls", False),
                    username=mqtt_config.get("username", ""),
                    password=mqtt_config.get("password", ""),
                ),
                audit=self.audit,
            )
        self._mqtt.connect()

        # Subscribe to device events via MQTT
        self._mqtt.subscribe_all_device_states(self._on_device_state)
        self._mqtt.subscribe_events("security", self._on_security_event)

        self.log(
            "iot_sentinel_init",
            severity=Severity.INFO,
            details={
                "subnet": self._scanner.subnet,
                "known_macs": len(known_macs),
                "mqtt_connected": self._mqtt.connected,
                "scan_interval": self._monitor.scan_interval,
            },
        )
        self._set_status(AgentStatus.IDLE)

    def run(self) -> AgentReport:
        self._set_status(AgentStatus.RUNNING)
        self._alerts.clear()
        now = datetime.now(timezone.utc).isoformat()
        self._last_scan = now

        actions: list[str] = []
        recommendations: list[str] = []

        # 1. Run a scan cycle
        anomalies = self._monitor.scan_once()
        actions.append(f"Network scan: {len(anomalies)} anomalies detected")

        # 2. Generate recommendations from anomalies
        for anomaly in anomalies:
            rec = self._generate_recommendation(anomaly)
            if rec:
                self._recommendations.append(rec)
                recommendations.append(
                    f"[{rec['action']}] {rec['description']}"
                )

        # 3. Build risk summary
        risk_summary = self._build_risk_summary(anomalies)
        self._risk_summaries.append(risk_summary)
        actions.append(f"Risk summary: score {risk_summary['risk_score']}/5")

        # 4. AI-assisted summarization (if available)
        ai_reasoning = ""
        if self.ai_enabled and anomalies:
            ai_reasoning = self._ai_summarize(anomalies, risk_summary)
            actions.append("AI risk analysis complete")

        # 5. Check for critical alerts
        critical = [a for a in anomalies if a.severity == AlertSeverity.CRITICAL]
        for c in critical:
            self._alerts.append(f"CRITICAL: {c.description}")

        # 6. Publish status to MQTT
        self._mqtt.publish_event("sentinel_scan", {
            "anomalies": len(anomalies),
            "critical": len(critical),
            "risk_score": risk_summary["risk_score"],
        })

        mon_summary = self._monitor.summary()
        self.log("sentinel_scan_complete", severity=Severity.INFO, details={
            "anomalies": len(anomalies),
            "critical": len(critical),
            "recommendations": len(recommendations),
            "risk_score": risk_summary["risk_score"],
        })

        self._set_status(AgentStatus.IDLE)

        return AgentReport(
            agent_name=self.name,
            status=AgentStatus.IDLE.value,
            summary=(
                f"Network: {mon_summary['tracked_devices']} devices "
                f"({mon_summary['online_devices']} online) | "
                f"{len(anomalies)} anomalies | "
                f"Risk: {risk_summary['risk_score']}/5"
            ),
            actions_taken=actions,
            recommendations=recommendations,
            alerts=self._alerts,
            data={
                "network_summary": mon_summary,
                "risk_summary": risk_summary,
                "pending_approvals": len(self._pending_approvals),
                "last_scan": self._last_scan,
            },
            ai_reasoning=ai_reasoning,
        )

    def report(self) -> AgentReport:
        mon_summary = self._monitor.summary()
        last_risk = self._risk_summaries[-1] if self._risk_summaries else {
            "risk_score": 0,
        }
        return AgentReport(
            agent_name=self.name,
            status=self.status.value,
            summary=(
                f"Network: {mon_summary['tracked_devices']} devices | "
                f"Risk: {last_risk['risk_score']}/5"
            ),
            alerts=list(self._alerts),
            data={
                "network_summary": mon_summary,
                "risk_summary": last_risk,
                "pending_approvals": len(self._pending_approvals),
                "last_scan": self._last_scan,
            },
        )

    def shutdown(self) -> None:
        self._monitor.stop()
        self._mqtt.disconnect()
        super().shutdown()

    # ------------------------------------------------------------------
    # Recommendation engine
    # ------------------------------------------------------------------

    def _generate_recommendation(self, anomaly: NetworkAnomaly) -> dict[str, Any] | None:
        """Generate an actionable recommendation from an anomaly.

        All recommendations require user approval (execution_policy: user_approval_required).
        """
        now = datetime.now(timezone.utc).isoformat()

        if anomaly.anomaly_type == AnomalyType.NEW_DEVICE:
            action = (
                RecommendationAction.BLOCK
                if anomaly.severity == AlertSeverity.CRITICAL
                else RecommendationAction.ISOLATE
            )
            rec = {
                "action": action,
                "description": anomaly.description,
                "device_ip": anomaly.device_ip,
                "device_mac": anomaly.device_mac,
                "reason": "New device detected on network",
                "requires_approval": True,
                "approved": False,
                "timestamp": now,
            }
            self._pending_approvals.append(rec)
            return rec

        if anomaly.anomaly_type == AnomalyType.MAC_CHANGE:
            rec = {
                "action": RecommendationAction.BLOCK,
                "description": anomaly.description,
                "device_ip": anomaly.device_ip,
                "device_mac": anomaly.device_mac,
                "reason": "Possible MAC spoofing attack",
                "requires_approval": True,
                "approved": False,
                "timestamp": now,
            }
            self._pending_approvals.append(rec)
            return rec

        if anomaly.anomaly_type == AnomalyType.HIGH_RISK_DEVICE:
            rec = {
                "action": RecommendationAction.QUARANTINE,
                "description": anomaly.description,
                "device_ip": anomaly.device_ip,
                "device_mac": anomaly.device_mac,
                "reason": "High risk score — unrecognized device with suspicious characteristics",
                "requires_approval": True,
                "approved": False,
                "timestamp": now,
            }
            self._pending_approvals.append(rec)
            return rec

        if anomaly.anomaly_type == AnomalyType.DEVICE_OFFLINE:
            return {
                "action": RecommendationAction.MONITOR,
                "description": anomaly.description,
                "device_ip": anomaly.device_ip,
                "device_mac": anomaly.device_mac,
                "reason": "Device went offline — may need attention",
                "requires_approval": False,
                "approved": True,
                "timestamp": now,
            }

        return None

    def approve_recommendation(self, index: int) -> bool:
        """Approve a pending recommendation (human-in-the-loop)."""
        if 0 <= index < len(self._pending_approvals):
            rec = self._pending_approvals[index]
            rec["approved"] = True
            self._action_history.append({
                **rec,
                "approved_at": datetime.now(timezone.utc).isoformat(),
            })
            self.log(
                f"recommendation_approved:{rec['action']}",
                severity=Severity.WARNING,
                details=rec,
                requires_review=True,
            )
            # Publish approval event via MQTT
            self._mqtt.publish_event("recommendation_approved", rec)
            return True
        return False

    def deny_recommendation(self, index: int) -> bool:
        """Deny a pending recommendation."""
        if 0 <= index < len(self._pending_approvals):
            rec = self._pending_approvals.pop(index)
            rec["denied"] = True
            self.log(
                f"recommendation_denied:{rec['action']}",
                severity=Severity.INFO,
                details=rec,
            )
            return True
        return False

    def pending_approvals(self) -> list[dict[str, Any]]:
        """Return recommendations awaiting user approval."""
        return [r for r in self._pending_approvals if not r.get("approved")]

    # ------------------------------------------------------------------
    # Risk summarizer
    # ------------------------------------------------------------------

    def _build_risk_summary(self, anomalies: list[NetworkAnomaly]) -> dict[str, Any]:
        """Build a structured risk summary from anomalies."""
        now = datetime.now(timezone.utc).isoformat()
        mon = self._monitor.summary()

        # Calculate risk score
        risk = 1
        critical_count = sum(
            1 for a in anomalies if a.severity == AlertSeverity.CRITICAL
        )
        warning_count = sum(
            1 for a in anomalies if a.severity == AlertSeverity.WARNING
        )
        new_unknowns = sum(
            1 for a in anomalies if a.anomaly_type == AnomalyType.NEW_DEVICE
        )
        mac_changes = sum(
            1 for a in anomalies if a.anomaly_type == AnomalyType.MAC_CHANGE
        )

        if mac_changes > 0:
            risk = 5  # Spoofing is always critical
        elif critical_count > 0:
            risk = max(risk, 4)
        elif new_unknowns > 2:
            risk = max(risk, 4)
        elif warning_count > 3:
            risk = max(risk, 3)
        elif new_unknowns > 0:
            risk = max(risk, 2)

        return {
            "risk_score": risk,
            "timestamp": now,
            "total_anomalies": len(anomalies),
            "critical_count": critical_count,
            "warning_count": warning_count,
            "new_unknown_devices": new_unknowns,
            "mac_changes": mac_changes,
            "devices_online": mon["online_devices"],
            "devices_offline": mon["offline_devices"],
            "action_items": [
                {
                    "action": a.recommendation,
                    "target": f"{a.device_ip} ({a.device_mac})",
                    "reason": a.description,
                }
                for a in anomalies
                if a.recommendation
            ],
        }

    def _ai_summarize(
        self,
        anomalies: list[NetworkAnomaly],
        risk_summary: dict[str, Any],
    ) -> str:
        """Use AI to generate a plain-language risk summary."""
        anomaly_text = "\n".join(
            f"- [{a.severity.value}] {a.description}"
            for a in anomalies[:10]
        )
        prompt = (
            f"Summarize these network security events for a non-technical "
            f"homeowner in 2-3 sentences. Be direct about threats.\n\n"
            f"Risk score: {risk_summary['risk_score']}/5\n"
            f"Events:\n{anomaly_text}"
        )
        return self.think_quick(prompt) or ""

    # ------------------------------------------------------------------
    # MQTT event handlers
    # ------------------------------------------------------------------

    def _on_device_state(self, msg: MqttMessage) -> None:
        """Handle device state updates from MQTT."""
        data = msg.payload_json()
        if not data:
            return
        # Log device state changes for monitoring
        self.log(
            f"device_state:{msg.topic}",
            severity=Severity.INFO,
            details=data,
        )

    def _on_security_event(self, msg: MqttMessage) -> None:
        """Handle security events from MQTT."""
        data = msg.payload_json()
        if not data:
            return
        self.log(
            f"security_event:{msg.topic}",
            severity=Severity.WARNING,
            details=data,
            requires_review=True,
        )

    def _handle_anomaly(self, anomaly: NetworkAnomaly) -> None:
        """Callback from network monitor when anomaly is detected."""
        # Publish anomaly to MQTT for other systems (Home Assistant, Node-RED)
        self._mqtt.publish_event("anomaly", anomaly.to_dict())

    # ------------------------------------------------------------------
    # Continuous monitoring control
    # ------------------------------------------------------------------

    def start_monitoring(self) -> None:
        """Start continuous network monitoring."""
        self._monitor.start()
        self.log("continuous_monitoring_started", severity=Severity.INFO,
                 details={"interval": self._monitor.scan_interval})

    def stop_monitoring(self) -> None:
        """Stop continuous network monitoring."""
        self._monitor.stop()
        self.log("continuous_monitoring_stopped", severity=Severity.INFO)

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def dashboard_text(self) -> str:
        """Full IoT Sentinel dashboard."""
        mon = self._monitor.summary()
        last_risk = self._risk_summaries[-1] if self._risk_summaries else {
            "risk_score": 0, "total_anomalies": 0, "critical_count": 0,
        }
        pending = self.pending_approvals()

        lines = [
            "",
            "  +==============================================================+",
            "  |         IoT SENTINEL — SOVEREIGN NETWORK CONTROL             |",
            "  +==============================================================+",
            "",
            f"  Network:    {self._scanner.subnet}",
            f"  Status:     {'MONITORING' if mon['monitoring_active'] else 'IDLE'}",
            f"  Scans:      {mon['scan_count']}",
            f"  Last scan:  {mon['last_scan'] or 'never'}",
            "",
            f"  Devices:    {mon['tracked_devices']} tracked "
            f"({mon['online_devices']} online, {mon['offline_devices']} offline)",
            f"  Baseline:   {mon['baseline_size']} trusted MACs",
            f"  Risk:       {last_risk['risk_score']}/5",
            "",
        ]

        # Anomaly summary
        lines.append("  ANOMALY LOG")
        lines.append("  " + "-" * 50)
        if mon["anomalies_by_type"]:
            for atype, count in sorted(mon["anomalies_by_type"].items()):
                lines.append(f"    {atype:<25} {count}")
        else:
            lines.append("    No anomalies detected")
        lines.append("")

        # Pending approvals
        if pending:
            lines.append("  PENDING APPROVALS (user action required)")
            lines.append("  " + "-" * 50)
            for i, rec in enumerate(pending):
                lines.append(
                    f"    [{i}] {rec['action']}: {rec['description']}"
                )
                lines.append(f"        Reason: {rec['reason']}")
            lines.append("")

        # Recent critical alerts
        crits = self._monitor.critical_anomalies()
        if crits:
            lines.append("  CRITICAL ALERTS")
            lines.append("  " + "-" * 50)
            for a in crits[-5:]:
                ack = " [ACK]" if a.acknowledged else " [!]"
                lines.append(f"    {ack} {a.description}")
            lines.append("")

        # MQTT status
        mqtt_stats = self._mqtt.stats()
        lines.append("  MQTT BUS")
        lines.append("  " + "-" * 50)
        lines.append(
            f"    Connected: {'yes' if mqtt_stats['connected'] else 'no'} "
            f"({mqtt_stats['host']}:{mqtt_stats['port']})"
        )
        lines.append(
            f"    Messages:  {mqtt_stats['messages_received']} rx / "
            f"{mqtt_stats['messages_published']} tx"
        )
        lines.append(f"    Topics:    {len(mqtt_stats['subscriptions'])}")
        lines.append("")

        # Recommendations history
        if self._recommendations:
            lines.append("  RECENT RECOMMENDATIONS")
            lines.append("  " + "-" * 50)
            for rec in self._recommendations[-5:]:
                approved = "APPROVED" if rec.get("approved") else "PENDING"
                lines.append(f"    [{approved}] {rec['action']}: {rec['description'][:60]}")
            lines.append("")

        lines.append(
            "  +==============================================================+"
        )
        return "\n".join(lines)

    def maintenance_summary(self, period: str = "daily") -> dict[str, Any]:
        """Generate maintenance summary for the given period.

        Args:
            period: "daily", "weekly", or "monthly"
        """
        mon = self._monitor.summary()
        last_risk = self._risk_summaries[-1] if self._risk_summaries else {}

        summary: dict[str, Any] = {
            "period": period,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "network_status": {
                "devices_tracked": mon["tracked_devices"],
                "devices_online": mon["online_devices"],
                "devices_offline": mon["offline_devices"],
            },
            "security": {
                "total_anomalies": mon["total_anomalies"],
                "critical_anomalies": mon["critical_anomalies"],
                "unacknowledged": mon["unacknowledged"],
                "risk_score": last_risk.get("risk_score", 0),
            },
            "mqtt": self._mqtt.stats(),
            "pending_approvals": len(self.pending_approvals()),
        }

        if period == "weekly":
            summary["scan_count"] = mon["scan_count"]
            summary["anomalies_by_type"] = mon.get("anomalies_by_type", {})

        if period == "monthly":
            summary["recommendations_total"] = len(self._recommendations)
            summary["actions_taken"] = len(self._action_history)

        return summary
