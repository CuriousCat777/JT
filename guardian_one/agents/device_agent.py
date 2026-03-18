"""Device Agent — IoT and LAN device management.

Responsibilities:
- Maintain inventory of all connected devices (cameras, plugs, lights, TV, vehicle, Flipper)
- Monitor device health and online/offline status
- Enforce security policies (VLAN isolation, default passwords, firmware updates)
- Detect unauthorized devices on the network
- Coordinate with Archivist for data sovereignty on device telemetry
- Alert on security events (camera offline, new unknown device, firmware CVE)

Managed ecosystems:
- TP-Link Kasa/Tapo (smart plugs) — local LAN API via python-kasa
- Philips Hue (smart lights) — Zigbee via Hue Bridge local API
- Govee (smart lights) — LAN UDP API or cloud API
- Security cameras — RTSP/ONVIF local streams
- Smart TV — LAN API (Samsung/LG/Roku depending on model)
- Vehicle — OBD-II local + manufacturer cloud API
- Flipper Zero — USB serial, no network
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig
from guardian_one.homelink.devices import (
    DeviceCategory,
    DeviceProtocol,
    DeviceRecord,
    DeviceRegistry,
    DeviceStatus,
    NetworkSegment,
)


class DeviceAgent(BaseAgent):
    """Manages IoT, smart home, and LAN-connected devices."""

    def __init__(
        self,
        config: AgentConfig,
        audit: AuditLog,
        device_registry: DeviceRegistry | None = None,
    ) -> None:
        super().__init__(config, audit)
        self.device_registry = device_registry or DeviceRegistry()
        self._scan_results: list[dict[str, Any]] = []
        self._alerts: list[str] = []
        self._last_scan: str = ""

    def initialize(self) -> None:
        self._set_status(AgentStatus.RUNNING)
        self.device_registry.load_defaults()
        self.log(
            "device_agent_init",
            severity=Severity.INFO,
            details={
                "devices_loaded": len(self.device_registry.all_devices()),
                "categories": self.device_registry.device_count_by_category(),
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

        # 1. Security audit
        audit = self.device_registry.security_audit()
        if audit["issue_count"] > 0:
            for issue in audit["issues"]:
                if issue["severity"] == "critical":
                    self._alerts.append(
                        f"CRITICAL: {issue['device']} — {issue['issue']}"
                    )
                    self.log(
                        f"device_security_critical:{issue['device']}",
                        severity=Severity.CRITICAL,
                        details=issue,
                        requires_review=True,
                    )
        actions.append(f"Security audit: {audit['issue_count']} issues found")

        # 2. Check for devices needing firmware updates
        needs_update = self._check_firmware_status()
        if needs_update:
            for device_id in needs_update:
                recommendations.append(f"Update firmware on {device_id}")
            actions.append(f"Firmware check: {len(needs_update)} devices need updates")

        # 3. Check VLAN isolation
        misplaced = self._check_vlan_isolation()
        if misplaced:
            for device_id, msg in misplaced:
                self._alerts.append(f"ISOLATION: {device_id} — {msg}")
                recommendations.append(f"Move {device_id} to IoT VLAN")

        # 4. Generate device status summary
        devices = self.device_registry.all_devices()
        status_counts = {}
        for d in devices:
            s = d.status.value
            status_counts[s] = status_counts.get(s, 0) + 1

        self.log(
            "device_scan_complete",
            severity=Severity.INFO,
            details={
                "total_devices": len(devices),
                "status_counts": status_counts,
                "issues": audit["issue_count"],
                "risk_score": audit["risk_score"],
            },
        )
        self._set_status(AgentStatus.IDLE)

        return AgentReport(
            agent_name=self.name,
            status=AgentStatus.IDLE.value,
            summary=(
                f"{len(devices)} devices managed | "
                f"{audit['issue_count']} security issues | "
                f"Risk: {audit['risk_score']}/5"
            ),
            actions_taken=actions,
            recommendations=recommendations,
            alerts=self._alerts,
            data={
                "device_count": len(devices),
                "categories": self.device_registry.device_count_by_category(),
                "security_audit": audit,
                "status_counts": status_counts,
                "last_scan": self._last_scan,
            },
        )

    def report(self) -> AgentReport:
        devices = self.device_registry.all_devices()
        audit = self.device_registry.security_audit()
        return AgentReport(
            agent_name=self.name,
            status=self.status.value,
            summary=(
                f"{len(devices)} devices | "
                f"{audit['issue_count']} issues | "
                f"Risk: {audit['risk_score']}/5"
            ),
            alerts=list(self._alerts),
            data={
                "device_count": len(devices),
                "categories": self.device_registry.device_count_by_category(),
                "security_audit": audit,
                "last_scan": self._last_scan,
            },
        )

    # ------------------------------------------------------------------
    # Device management
    # ------------------------------------------------------------------

    def add_device(self, device: DeviceRecord) -> None:
        self.device_registry.register(device)
        self.log(
            f"device_added:{device.device_id}",
            severity=Severity.INFO,
            details={
                "name": device.name,
                "category": device.category.value,
                "manufacturer": device.manufacturer,
                "segment": device.network_segment.value,
            },
        )

    def remove_device(self, device_id: str) -> bool:
        removed = self.device_registry.remove(device_id)
        if removed:
            self.log(
                f"device_removed:{device_id}",
                severity=Severity.WARNING,
                details={"device_id": device_id},
            )
        return removed

    def get_device(self, device_id: str) -> DeviceRecord | None:
        return self.device_registry.get(device_id)

    def list_devices(self) -> list[DeviceRecord]:
        return self.device_registry.all_devices()

    # ------------------------------------------------------------------
    # Network scanning (stub — requires local network access)
    # ------------------------------------------------------------------

    def scan_network(self) -> list[dict[str, Any]]:
        """Scan local network for devices.

        In production, this would use:
        - ARP scanning (scapy or arp-scan)
        - mDNS/SSDP discovery
        - ONVIF discovery for cameras
        - python-kasa for TP-Link devices
        - phue library for Hue bridge discovery

        Returns list of discovered devices with IP, MAC, hostname.
        """
        self.log("network_scan_start", severity=Severity.INFO)
        # Stub — actual implementation requires local network access
        discovered: list[dict[str, Any]] = []
        self._scan_results = discovered
        self._last_scan = datetime.now(timezone.utc).isoformat()
        self.log(
            "network_scan_complete",
            severity=Severity.INFO,
            details={"discovered_count": len(discovered)},
        )
        return discovered

    def detect_unknown_devices(self) -> list[dict[str, Any]]:
        """Compare scan results against registry to find unauthorized devices."""
        known_macs = {
            d.mac_address.lower()
            for d in self.device_registry.all_devices()
            if d.mac_address
        }
        unknown = [
            d for d in self._scan_results
            if d.get("mac", "").lower() not in known_macs
        ]
        if unknown:
            self.log(
                "unknown_devices_detected",
                severity=Severity.WARNING,
                details={"count": len(unknown), "devices": unknown},
                requires_review=True,
            )
        return unknown

    # ------------------------------------------------------------------
    # Security checks
    # ------------------------------------------------------------------

    def _check_firmware_status(self) -> list[str]:
        """Return device IDs where firmware is unknown or outdated."""
        needs_update = []
        for d in self.device_registry.all_devices():
            if d.firmware.current_version == "unknown":
                needs_update.append(d.device_id)
            elif (
                d.firmware.latest_available != "unknown"
                and d.firmware.current_version != d.firmware.latest_available
            ):
                needs_update.append(d.device_id)
        return needs_update

    def _check_vlan_isolation(self) -> list[tuple[str, str]]:
        """Check that IoT devices are properly isolated from trusted LAN."""
        misplaced = []
        iot_categories = {
            DeviceCategory.SECURITY_CAMERA,
            DeviceCategory.MOTION_DETECTOR,
            DeviceCategory.SMART_PLUG,
            DeviceCategory.SMART_LIGHT,
            DeviceCategory.SMART_TV,
            DeviceCategory.SENSOR,
        }
        for d in self.device_registry.all_devices():
            if (
                d.category in iot_categories
                and d.network_segment == NetworkSegment.TRUSTED_LAN
            ):
                misplaced.append((
                    d.device_id,
                    f"{d.name} ({d.category.value}) on trusted LAN — move to IoT VLAN",
                ))
        return misplaced

    # ------------------------------------------------------------------
    # Device ecosystem queries
    # ------------------------------------------------------------------

    def hue_devices(self) -> list[DeviceRecord]:
        return [d for d in self.device_registry.all_devices()
                if d.integration_name == "philips_hue"]

    def govee_devices(self) -> list[DeviceRecord]:
        return [d for d in self.device_registry.all_devices()
                if d.integration_name == "govee"]

    def tplink_devices(self) -> list[DeviceRecord]:
        return [d for d in self.device_registry.all_devices()
                if d.integration_name == "tplink_kasa"]

    def cameras(self) -> list[DeviceRecord]:
        return self.device_registry.by_category(DeviceCategory.SECURITY_CAMERA)

    def security_devices(self) -> list[DeviceRecord]:
        """All security-related devices (cameras, motion detectors, Flipper)."""
        return [
            d for d in self.device_registry.all_devices()
            if d.category in (
                DeviceCategory.SECURITY_CAMERA,
                DeviceCategory.MOTION_DETECTOR,
                DeviceCategory.SECURITY_TOOL,
            )
        ]

    # ------------------------------------------------------------------
    # Status display
    # ------------------------------------------------------------------

    def status_text(self) -> str:
        """Human-readable device status display."""
        devices = self.device_registry.all_devices()
        audit = self.device_registry.security_audit()
        cats = self.device_registry.device_count_by_category()

        lines = [
            "  H.O.M.E. L.I.N.K. — DEVICE MANAGEMENT",
            "  " + "=" * 50,
            f"  Total devices: {len(devices)}",
            f"  Security risk: {audit['risk_score']}/5",
            f"  Issues: {audit['issue_count']}",
            "",
            "  Device Inventory:",
        ]

        category_icons = {
            "security_camera": "[CAM]",
            "motion_detector": "[MOT]",
            "smart_plug": "[PLG]",
            "smart_light": "[LGT]",
            "smart_tv": "[TV ]",
            "vehicle": "[CAR]",
            "security_tool": "[SEC]",
            "network_infra": "[NET]",
            "media_player": "[MED]",
            "sensor": "[SNS]",
            "other": "[---]",
        }

        for d in sorted(devices, key=lambda x: x.category.value):
            icon = category_icons.get(d.category.value, "[???]")
            status_icon = {
                DeviceStatus.ONLINE: "ON ",
                DeviceStatus.OFFLINE: "OFF",
                DeviceStatus.STANDBY: "SBY",
                DeviceStatus.ERROR: "ERR",
                DeviceStatus.UNKNOWN: "???",
            }.get(d.status, "???")

            segment = d.network_segment.value[:8]
            lines.append(
                f"    {icon} {status_icon}  {d.name:<30} "
                f"{d.manufacturer:<12} {segment}"
            )

        if audit["issues"]:
            lines.append("")
            lines.append("  Security Issues:")
            for issue in audit["issues"][:10]:
                sev = issue["severity"].upper()
                lines.append(f"    [{sev}] {issue['device']}: {issue['issue']}")

        lines.append("")
        lines.append("  Categories:")
        for cat, count in sorted(cats.items()):
            lines.append(f"    {cat}: {count}")

        return "\n".join(lines)
