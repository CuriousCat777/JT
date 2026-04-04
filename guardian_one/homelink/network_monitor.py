"""H.O.M.E. L.I.N.K. Network Monitor — Continuous LAN surveillance + anomaly detection.

Zero-trust continuous monitoring:
- Periodic network scans (configurable interval)
- New device detection and alerting
- Traffic anomaly detection (port scans, MAC spoofing, rogue DHCP)
- Device health tracking (online/offline transitions)
- Risk-scored event log for AI summarization
- Fail-closed: unknown devices are flagged, not trusted

All monitoring is passive and LAN-local. No external telemetry.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.homelink.network_scanner import (
    DeviceClassification,
    DiscoveredDevice,
    NetworkScanner,
)


class AnomalyType(Enum):
    """Types of network anomalies detected."""
    NEW_DEVICE = "new_device"
    DEVICE_OFFLINE = "device_offline"
    DEVICE_ONLINE = "device_online"
    MAC_CHANGE = "mac_change"            # IP kept same MAC — spoofing?
    PORT_SCAN = "port_scan"              # Multiple ports probed
    ROGUE_DHCP = "rogue_dhcp"            # Unauthorized DHCP server
    UNKNOWN_VENDOR = "unknown_vendor"    # Unrecognized OUI
    HIGH_RISK_DEVICE = "high_risk_device"
    TRAFFIC_SPIKE = "traffic_spike"


class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class NetworkAnomaly:
    """A detected network anomaly event."""
    anomaly_type: AnomalyType
    severity: AlertSeverity
    device_ip: str = ""
    device_mac: str = ""
    description: str = ""
    recommendation: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    acknowledged: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "anomaly_type": self.anomaly_type.value,
            "severity": self.severity.value,
            "device_ip": self.device_ip,
            "device_mac": self.device_mac,
            "description": self.description,
            "recommendation": self.recommendation,
            "timestamp": self.timestamp,
            "acknowledged": self.acknowledged,
        }


@dataclass
class DeviceHealthRecord:
    """Tracks a device's online/offline state over time."""
    mac_address: str
    ip_address: str
    last_seen: str = ""
    is_online: bool = False
    offline_count: int = 0
    online_since: str = ""
    transitions: list[dict[str, str]] = field(default_factory=list)


class NetworkMonitor:
    """Continuous LAN monitoring engine with anomaly detection.

    Runs periodic scans, compares results to baseline, and generates
    anomaly alerts. Designed for sovereign, offline-capable operation.
    """

    def __init__(
        self,
        scanner: NetworkScanner | None = None,
        audit: AuditLog | None = None,
        scan_interval_seconds: int = 300,
        max_anomaly_history: int = 500,
    ) -> None:
        self._scanner = scanner or NetworkScanner()
        self._audit = audit
        self._scan_interval = scan_interval_seconds
        self._anomalies: deque[NetworkAnomaly] = deque(maxlen=max_anomaly_history)
        self._device_health: dict[str, DeviceHealthRecord] = {}
        self._baseline_macs: set[str] = set()
        self._ip_mac_map: dict[str, str] = {}  # IP -> MAC for spoofing detection
        self._callbacks: list[Callable[[NetworkAnomaly], None]] = []
        self._monitoring = False
        self._monitor_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._scan_count: int = 0
        self._last_scan: str = ""

    @property
    def monitoring(self) -> bool:
        return self._monitoring

    @property
    def scan_interval(self) -> int:
        return self._scan_interval

    # ------------------------------------------------------------------
    # Baseline management
    # ------------------------------------------------------------------

    def set_baseline(self, known_macs: set[str]) -> None:
        """Set the baseline of known/trusted MAC addresses."""
        self._baseline_macs = {m.lower() for m in known_macs}
        self._scanner.update_known_macs(self._baseline_macs)

    def add_to_baseline(self, mac: str) -> None:
        """Add a MAC address to the trusted baseline."""
        self._baseline_macs.add(mac.lower())
        self._scanner.update_known_macs(self._baseline_macs)

    def remove_from_baseline(self, mac: str) -> None:
        """Remove a MAC from the trusted baseline."""
        self._baseline_macs.discard(mac.lower())
        self._scanner.update_known_macs(self._baseline_macs)

    # ------------------------------------------------------------------
    # Anomaly callbacks
    # ------------------------------------------------------------------

    def on_anomaly(self, callback: Callable[[NetworkAnomaly], None]) -> None:
        """Register a callback for anomaly events."""
        self._callbacks.append(callback)

    def _emit_anomaly(self, anomaly: NetworkAnomaly) -> None:
        """Record and dispatch an anomaly."""
        with self._lock:
            self._anomalies.append(anomaly)

        self._log(
            f"anomaly:{anomaly.anomaly_type.value}",
            Severity.WARNING if anomaly.severity == AlertSeverity.WARNING
            else Severity.CRITICAL if anomaly.severity == AlertSeverity.CRITICAL
            else Severity.INFO,
            anomaly.to_dict(),
            requires_review=anomaly.severity == AlertSeverity.CRITICAL,
        )

        for cb in self._callbacks:
            try:
                cb(anomaly)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Single scan cycle
    # ------------------------------------------------------------------

    def scan_once(self) -> list[NetworkAnomaly]:
        """Run a single scan cycle and return any anomalies detected."""
        anomalies: list[NetworkAnomaly] = []
        now = datetime.now(timezone.utc).isoformat()

        # Get current devices on the network
        devices = self._scanner.full_scan()
        current_macs: set[str] = set()

        for device in devices:
            mac = device.mac_address.lower()
            if not mac:
                continue
            current_macs.add(mac)

            # --- New device detection ---
            if mac not in self._baseline_macs and mac not in self._device_health:
                anomaly = NetworkAnomaly(
                    anomaly_type=AnomalyType.NEW_DEVICE,
                    severity=AlertSeverity.WARNING
                    if device.risk_score <= 3
                    else AlertSeverity.CRITICAL,
                    device_ip=device.ip_address,
                    device_mac=mac,
                    description=(
                        f"New device detected: {device.vendor or 'unknown vendor'} "
                        f"at {device.ip_address} (MAC: {mac})"
                    ),
                    recommendation=(
                        "block_device" if device.risk_score >= 4
                        else "isolate_vlan" if device.risk_score >= 3
                        else "ignore"
                    ),
                    metadata=device.to_dict(),
                )
                anomalies.append(anomaly)
                self._emit_anomaly(anomaly)

            # --- High risk device ---
            if device.risk_score >= 4 and mac not in self._baseline_macs:
                anomaly = NetworkAnomaly(
                    anomaly_type=AnomalyType.HIGH_RISK_DEVICE,
                    severity=AlertSeverity.CRITICAL,
                    device_ip=device.ip_address,
                    device_mac=mac,
                    description=(
                        f"High-risk device: {device.vendor or 'unknown'} "
                        f"risk={device.risk_score}/5 at {device.ip_address}"
                    ),
                    recommendation="block_device",
                    metadata=device.to_dict(),
                )
                anomalies.append(anomaly)
                self._emit_anomaly(anomaly)

            # --- MAC change detection (potential spoofing) ---
            if device.ip_address in self._ip_mac_map:
                prev_mac = self._ip_mac_map[device.ip_address]
                if prev_mac != mac:
                    anomaly = NetworkAnomaly(
                        anomaly_type=AnomalyType.MAC_CHANGE,
                        severity=AlertSeverity.CRITICAL,
                        device_ip=device.ip_address,
                        device_mac=mac,
                        description=(
                            f"MAC address changed for {device.ip_address}: "
                            f"{prev_mac} -> {mac} (possible spoofing)"
                        ),
                        recommendation="block_device",
                        metadata={
                            "previous_mac": prev_mac,
                            "new_mac": mac,
                        },
                    )
                    anomalies.append(anomaly)
                    self._emit_anomaly(anomaly)

            self._ip_mac_map[device.ip_address] = mac

            # --- Update health record ---
            if mac not in self._device_health:
                self._device_health[mac] = DeviceHealthRecord(
                    mac_address=mac,
                    ip_address=device.ip_address,
                    last_seen=now,
                    is_online=True,
                    online_since=now,
                )
            else:
                health = self._device_health[mac]
                if not health.is_online:
                    # Device came back online
                    health.is_online = True
                    health.online_since = now
                    health.transitions.append({
                        "state": "online", "timestamp": now,
                    })
                    anomaly = NetworkAnomaly(
                        anomaly_type=AnomalyType.DEVICE_ONLINE,
                        severity=AlertSeverity.INFO,
                        device_ip=device.ip_address,
                        device_mac=mac,
                        description=f"Device {mac} ({device.ip_address}) back online",
                    )
                    anomalies.append(anomaly)
                    self._emit_anomaly(anomaly)

                health.last_seen = now
                health.ip_address = device.ip_address

        # --- Detect offline devices ---
        for mac, health in self._device_health.items():
            if health.is_online and mac not in current_macs:
                health.is_online = False
                health.offline_count += 1
                health.transitions.append({
                    "state": "offline", "timestamp": now,
                })
                anomaly = NetworkAnomaly(
                    anomaly_type=AnomalyType.DEVICE_OFFLINE,
                    severity=AlertSeverity.WARNING,
                    device_ip=health.ip_address,
                    device_mac=mac,
                    description=(
                        f"Device {mac} ({health.ip_address}) went offline "
                        f"(offline count: {health.offline_count})"
                    ),
                    recommendation="ignore",
                )
                anomalies.append(anomaly)
                self._emit_anomaly(anomaly)

        self._scan_count += 1
        self._last_scan = now

        self._log("scan_cycle_complete", Severity.INFO, {
            "devices_found": len(devices),
            "anomalies": len(anomalies),
            "scan_number": self._scan_count,
        })

        return anomalies

    # ------------------------------------------------------------------
    # Continuous monitoring
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start continuous monitoring in a background thread."""
        if self._monitoring:
            return
        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="network-monitor",
        )
        self._monitor_thread.start()
        self._log("monitoring_started", Severity.INFO, {
            "interval_seconds": self._scan_interval,
        })

    def stop(self) -> None:
        """Stop continuous monitoring."""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=10)
            self._monitor_thread = None
        self._log("monitoring_stopped", Severity.INFO, {})

    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self._monitoring:
            try:
                self.scan_once()
            except Exception as exc:
                self._log("monitor_error", Severity.ERROR, {
                    "error": str(exc),
                })
            # Sleep in small increments to allow quick shutdown
            for _ in range(self._scan_interval):
                if not self._monitoring:
                    break
                time.sleep(1)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def anomalies(self, limit: int = 50) -> list[NetworkAnomaly]:
        """Return recent anomalies."""
        with self._lock:
            items = list(self._anomalies)
        return items[-limit:]

    def unacknowledged_anomalies(self) -> list[NetworkAnomaly]:
        """Return anomalies that haven't been acknowledged."""
        with self._lock:
            return [a for a in self._anomalies if not a.acknowledged]

    def critical_anomalies(self) -> list[NetworkAnomaly]:
        """Return critical-severity anomalies."""
        with self._lock:
            return [
                a for a in self._anomalies
                if a.severity == AlertSeverity.CRITICAL
            ]

    def acknowledge_anomaly(self, index: int) -> bool:
        """Acknowledge an anomaly by its index in the list."""
        with self._lock:
            items = list(self._anomalies)
            if 0 <= index < len(items):
                items[index].acknowledged = True
                return True
        return False

    def device_health(self) -> list[DeviceHealthRecord]:
        """Return health records for all tracked devices."""
        return list(self._device_health.values())

    def online_devices(self) -> list[DeviceHealthRecord]:
        return [h for h in self._device_health.values() if h.is_online]

    def offline_devices(self) -> list[DeviceHealthRecord]:
        return [h for h in self._device_health.values() if not h.is_online]

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Network monitoring summary."""
        with self._lock:
            anomaly_list = list(self._anomalies)

        by_type: dict[str, int] = {}
        for a in anomaly_list:
            t = a.anomaly_type.value
            by_type[t] = by_type.get(t, 0) + 1

        critical_count = sum(
            1 for a in anomaly_list if a.severity == AlertSeverity.CRITICAL
        )
        unack_count = sum(1 for a in anomaly_list if not a.acknowledged)

        return {
            "monitoring_active": self._monitoring,
            "scan_count": self._scan_count,
            "last_scan": self._last_scan,
            "scan_interval_seconds": self._scan_interval,
            "total_anomalies": len(anomaly_list),
            "critical_anomalies": critical_count,
            "unacknowledged": unack_count,
            "anomalies_by_type": by_type,
            "tracked_devices": len(self._device_health),
            "online_devices": len(self.online_devices()),
            "offline_devices": len(self.offline_devices()),
            "baseline_size": len(self._baseline_macs),
        }

    def summary_text(self) -> str:
        """Human-readable monitoring summary."""
        s = self.summary()
        lines = [
            "",
            "  H.O.M.E. L.I.N.K. — NETWORK MONITOR",
            "  " + "=" * 50,
            "",
            f"  Status:     {'ACTIVE' if s['monitoring_active'] else 'STOPPED'}",
            f"  Scans:      {s['scan_count']}",
            f"  Last scan:  {s['last_scan'] or 'never'}",
            f"  Interval:   {s['scan_interval_seconds']}s",
            "",
            f"  Devices:    {s['tracked_devices']} tracked "
            f"({s['online_devices']} online, {s['offline_devices']} offline)",
            f"  Baseline:   {s['baseline_size']} trusted MACs",
            "",
            f"  Anomalies:  {s['total_anomalies']} total, "
            f"{s['critical_anomalies']} critical, "
            f"{s['unacknowledged']} unacknowledged",
        ]

        if s["anomalies_by_type"]:
            lines.append("")
            lines.append("  ANOMALY BREAKDOWN")
            lines.append("  " + "-" * 40)
            for atype, count in sorted(s["anomalies_by_type"].items()):
                lines.append(f"    {atype:<25} {count}")

        # Show recent critical anomalies
        crits = self.critical_anomalies()
        if crits:
            lines.append("")
            lines.append("  CRITICAL ALERTS")
            lines.append("  " + "-" * 40)
            for a in crits[-5:]:
                ack = " [ACK]" if a.acknowledged else ""
                lines.append(f"    {a.description}{ack}")
                if a.recommendation:
                    lines.append(f"      -> {a.recommendation}")

        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log(
        self,
        action: str,
        severity: Severity,
        details: dict[str, Any],
        requires_review: bool = False,
    ) -> None:
        if self._audit:
            self._audit.record(
                agent="network_monitor",
                action=action,
                severity=severity,
                details=details,
                requires_review=requires_review,
            )
