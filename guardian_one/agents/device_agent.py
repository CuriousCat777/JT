"""Device Agent — IoT, LAN, and smart home device management + automation.

Responsibilities:
- Maintain inventory of all connected devices (cameras, plugs, lights, blinds, TV, vehicle, Flipper)
- Monitor device health and online/offline status
- Enforce security policies (VLAN isolation, default passwords, firmware updates)
- Detect unauthorized devices on the network
- Execute automation rules driven by Chronos schedule events
- Manage room-based device groups
- Coordinate Flipper Zero for device auditing and backup control
- Provide full dashboard of home state

Managed ecosystems:
- TP-Link Kasa/Tapo (smart plugs) — local LAN API via python-kasa
- Philips Hue (smart lights) — Zigbee via Hue Bridge local API
- Govee (smart lights) — LAN UDP API or cloud API
- Ryse SmartShade (smart blinds) — BLE/WiFi via SmartBridge
- Security cameras — RTSP/ONVIF local streams
- Smart TV — LAN API (Samsung/LG/Roku depending on model)
- Vehicle — OBD-II local + manufacturer cloud API
- Flipper Zero — USB serial, sub-GHz/NFC/IR/BLE security tool
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig
from guardian_one.homelink.automations import (
    ActionType,
    AutomationAction,
    AutomationEngine,
    TriggerType,
)
from guardian_one.homelink.devices import (
    DeviceCategory,
    DeviceProtocol,
    DeviceRecord,
    DeviceRegistry,
    DeviceStatus,
    FlipperCapability,
    NetworkSegment,
)


class DeviceAgent(BaseAgent):
    """Manages IoT, smart home, and LAN-connected devices + automations."""

    def __init__(
        self,
        config: AgentConfig,
        audit: AuditLog,
        device_registry: DeviceRegistry | None = None,
        automation_engine: AutomationEngine | None = None,
    ) -> None:
        super().__init__(config, audit)
        self.device_registry = device_registry or DeviceRegistry()
        self.automation = automation_engine or AutomationEngine(audit=audit)
        self._scan_results: list[dict[str, Any]] = []
        self._alerts: list[str] = []
        self._last_scan: str = ""
        self._action_log: list[dict[str, Any]] = []

    def initialize(self) -> None:
        self._set_status(AgentStatus.RUNNING)
        self.device_registry.load_defaults()
        self.automation.load_defaults()
        self.log(
            "device_agent_init",
            severity=Severity.INFO,
            details={
                "devices_loaded": len(self.device_registry.all_devices()),
                "rooms_loaded": len(self.device_registry.all_rooms()),
                "flipper_profiles": len(self.device_registry.all_flipper_profiles()),
                "automation_rules": len(self.automation.all_rules()),
                "scenes": len(self.automation.all_scenes()),
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
        status_counts: dict[str, int] = {}
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
                "room_count": len(self.device_registry.all_rooms()),
                "automation_rules": len(self.automation.all_rules()),
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
                "room_count": len(self.device_registry.all_rooms()),
                "automation_rules": len(self.automation.all_rules()),
                "categories": self.device_registry.device_count_by_category(),
                "security_audit": audit,
                "last_scan": self._last_scan,
            },
        )

    # ------------------------------------------------------------------
    # Chronos integration — schedule event handler
    # ------------------------------------------------------------------

    def handle_schedule_event(self, event: str) -> list[dict[str, Any]]:
        """Called by Chronos when a schedule event fires.

        Args:
            event: One of 'wake', 'sleep', 'leave', 'arrive'

        Returns:
            List of executed action records
        """
        self.log(
            f"schedule_event:{event}",
            severity=Severity.INFO,
            details={"event": event},
        )
        pending_actions = self.automation.evaluate_trigger(
            TriggerType.SCHEDULE, {"event": event}
        )
        return self._execute_actions(pending_actions, source=f"schedule:{event}")

    def handle_occupancy_event(self, state: str, room_id: str = "") -> list[dict[str, Any]]:
        """Called when motion is detected or cleared.

        Args:
            state: 'detected' or 'cleared'
            room_id: Which room the motion is in
        """
        pending = self.automation.evaluate_trigger(
            TriggerType.OCCUPANCY, {"state": state, "room_id": room_id}
        )
        return self._execute_actions(pending, source=f"occupancy:{state}:{room_id}")

    def handle_solar_event(self, event: str) -> list[dict[str, Any]]:
        """Called at sunrise/sunset.

        Args:
            event: 'sunrise' or 'sunset'
        """
        trigger = TriggerType.SUNRISE if event == "sunrise" else TriggerType.SUNSET
        pending = self.automation.evaluate_trigger(trigger, {"event": event})
        return self._execute_actions(pending, source=f"solar:{event}")

    def activate_scene(self, scene_id: str) -> list[dict[str, Any]]:
        """Manually activate a scene (e.g., 'scene-movie', 'scene-goodnight')."""
        actions = self.automation.activate_scene(scene_id)
        return self._execute_actions(actions, source=f"scene:{scene_id}")

    # ------------------------------------------------------------------
    # Action execution
    # ------------------------------------------------------------------

    def _execute_actions(
        self, actions: list[AutomationAction], source: str = ""
    ) -> list[dict[str, Any]]:
        """Execute a list of automation actions and log results.

        In production, this dispatches to actual device APIs:
        - Ryse SmartBridge API for blinds
        - python-kasa for TP-Link plugs
        - phue for Hue lights
        - Govee LAN/cloud API for Govee
        - ONVIF/RTSP for cameras

        Currently stubs the actual API calls but logs everything.
        """
        results: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc).isoformat()

        for action in actions:
            record = {
                "action": action.action_type.value,
                "device_id": action.target_device_id,
                "room_id": action.target_room_id,
                "parameters": action.parameters,
                "source": source,
                "timestamp": now,
                "status": "executed",  # Would be "success"/"failed" with real API
            }
            results.append(record)
            self._action_log.append(record)
            self.log(
                f"action_executed:{action.action_type.value}",
                severity=Severity.INFO,
                details={
                    "device": action.target_device_id,
                    "room": action.target_room_id,
                    "params": action.parameters,
                    "source": source,
                },
            )

        return results

    def action_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(reversed(self._action_log[-limit:]))

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
            DeviceCategory.SMART_BLIND,
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

    def ryse_devices(self) -> list[DeviceRecord]:
        return [d for d in self.device_registry.all_devices()
                if d.integration_name == "ryse_smartshade"]

    def cameras(self) -> list[DeviceRecord]:
        return self.device_registry.by_category(DeviceCategory.SECURITY_CAMERA)

    def blinds(self) -> list[DeviceRecord]:
        return self.device_registry.by_category(DeviceCategory.SMART_BLIND)

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
    # Flipper Zero operations
    # ------------------------------------------------------------------

    def flipper_audit(self) -> dict[str, Any]:
        """Report on Flipper Zero capabilities across all devices."""
        profiles = self.device_registry.all_flipper_profiles()
        controllable = self.device_registry.flipper_controllable_devices()

        cap_counts: dict[str, int] = {}
        for p in profiles:
            for cap in p.capabilities:
                cap_counts[cap.value] = cap_counts.get(cap.value, 0) + 1

        untested = [p for p in profiles if not p.tested]

        return {
            "total_profiles": len(profiles),
            "controllable_devices": len(controllable),
            "capabilities": cap_counts,
            "untested_profiles": len(untested),
            "devices": [
                {
                    "device_id": p.device_id,
                    "capabilities": [c.value for c in p.capabilities],
                    "ir_file": p.ir_remote_file,
                    "sub_ghz_file": p.sub_ghz_file,
                    "tested": p.tested,
                    "notes": p.notes,
                }
                for p in profiles
            ],
        }

    # ------------------------------------------------------------------
    # Dashboard — full home status display
    # ------------------------------------------------------------------

    def dashboard_text(self) -> str:
        """Full H.O.M.E. L.I.N.K. dashboard — devices, rooms, automations, Flipper."""
        devices = self.device_registry.all_devices()
        rooms = self.device_registry.all_rooms()
        audit = self.device_registry.security_audit()
        auto_summary = self.automation.summary()
        flipper = self.flipper_audit()

        category_icons = {
            "security_camera": "[CAM]", "motion_detector": "[MOT]",
            "smart_plug": "[PLG]", "smart_light": "[LGT]",
            "smart_blind": "[BLD]", "smart_tv": "[TV ]",
            "vehicle": "[CAR]", "security_tool": "[SEC]",
            "network_infra": "[NET]", "media_player": "[MED]",
            "sensor": "[SNS]", "other": "[---]",
        }
        status_icons = {
            DeviceStatus.ONLINE: "ON ", DeviceStatus.OFFLINE: "OFF",
            DeviceStatus.STANDBY: "SBY", DeviceStatus.ERROR: "ERR",
            DeviceStatus.UNKNOWN: "???",
        }

        lines = [
            "",
            "  ╔══════════════════════════════════════════════════════════╗",
            "  ║        H.O.M.E. L.I.N.K. — CONTROL DASHBOARD          ║",
            "  ╚══════════════════════════════════════════════════════════╝",
            "",
            f"  Devices: {len(devices)}    Rooms: {len(rooms)}    "
            f"Rules: {auto_summary['enabled_rules']}/{auto_summary['total_rules']}    "
            f"Scenes: {auto_summary['total_scenes']}    "
            f"Risk: {audit['risk_score']}/5",
            "",
        ]

        # --- Room view ---
        lines.append("  ROOMS")
        lines.append("  " + "-" * 56)
        for room in rooms:
            room_devices = self.device_registry.devices_in_room(room.room_id)
            auto_flags = []
            if room.auto_lights:
                auto_flags.append("lights")
            if room.auto_blinds:
                auto_flags.append("blinds")
            auto_str = f" [auto: {', '.join(auto_flags)}]" if auto_flags else ""
            lines.append(f"  {room.name:<24} {len(room_devices)} devices{auto_str}")
            for d in room_devices:
                icon = category_icons.get(d.category.value, "[???]")
                si = status_icons.get(d.status, "???")
                lines.append(f"    {icon} {si}  {d.name}")
        lines.append("")

        # --- All devices (flat view) ---
        lines.append("  DEVICE INVENTORY")
        lines.append("  " + "-" * 56)
        lines.append(f"  {'':4} {'Sts':3}  {'Name':<28} {'Mfg':<12} {'Segment'}")
        for d in sorted(devices, key=lambda x: (x.location or "zzz", x.category.value)):
            icon = category_icons.get(d.category.value, "[???]")
            si = status_icons.get(d.status, "???")
            seg = d.network_segment.value[:10]
            lines.append(f"  {icon} {si}  {d.name:<28} {d.manufacturer:<12} {seg}")
        lines.append("")

        # --- Automation rules ---
        lines.append("  AUTOMATION RULES")
        lines.append("  " + "-" * 56)
        for rule in sorted(self.automation.all_rules(), key=lambda r: r.priority):
            status_char = "E" if rule.status.value == "enabled" else "D"
            execs = f"x{rule.execution_count}" if rule.execution_count else "new"
            lines.append(
                f"  [{status_char}] P{rule.priority} {rule.name:<40} {execs}"
            )
        lines.append("")

        # --- Scenes ---
        lines.append("  SCENES")
        lines.append("  " + "-" * 56)
        for scene in self.automation.all_scenes():
            lines.append(
                f"  {scene.scene_id:<20} {scene.name:<20} "
                f"({len(scene.actions)} actions)"
            )
        lines.append("")

        # --- Flipper Zero ---
        lines.append("  FLIPPER ZERO — DEVICE PROFILES")
        lines.append("  " + "-" * 56)
        for fp in flipper["devices"]:
            tested = "OK" if fp["tested"] else "UNTESTED"
            caps = ", ".join(fp["capabilities"][:3])
            lines.append(f"  {fp['device_id']:<20} [{tested}] {caps}")
        lines.append(f"  Total: {flipper['total_profiles']} profiles, "
                     f"{flipper['controllable_devices']} controllable")
        lines.append("")

        # --- Security issues ---
        if audit["issues"]:
            lines.append("  SECURITY ISSUES")
            lines.append("  " + "-" * 56)
            for issue in audit["issues"][:8]:
                sev = issue["severity"].upper()[:4]
                lines.append(f"  [{sev}] {issue['device']}: {issue['issue']}")
            if audit["issue_count"] > 8:
                lines.append(f"  ... and {audit['issue_count'] - 8} more")
            lines.append("")

        return "\n".join(lines)

    def status_text(self) -> str:
        """Short device status display (backward compatible)."""
        return self.dashboard_text()
