"""H.O.M.E. L.I.N.K. Network Scanner — LAN device discovery via nmap, ARP, mDNS.

Sovereign, local-first device discovery:
- nmap ping sweep for IP/MAC/vendor identification
- ARP table parsing for fast known-device lookup
- mDNS/SSDP for service-aware discovery (Home Assistant, printers, etc.)
- Device classification: known, iot, unknown
- Risk scoring per discovered device

All scanning is LAN-only. No data leaves the network.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from guardian_one.core.audit import AuditLog, Severity


class DeviceClassification(Enum):
    """Classification for discovered devices."""
    KNOWN = "known"
    IOT = "iot"
    UNKNOWN = "unknown"


@dataclass
class DiscoveredDevice:
    """A device found during a network scan."""
    ip_address: str
    mac_address: str = ""
    hostname: str = ""
    vendor: str = ""
    device_class: DeviceClassification = DeviceClassification.UNKNOWN
    risk_score: int = 3          # 1 (trusted) to 5 (critical risk)
    open_ports: list[int] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    scan_method: str = ""        # "nmap", "arp", "mdns"
    first_seen: str = ""
    last_seen: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "hostname": self.hostname,
            "vendor": self.vendor,
            "device_class": self.device_class.value,
            "risk_score": self.risk_score,
            "open_ports": self.open_ports,
            "services": self.services,
            "scan_method": self.scan_method,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }


# OUI prefixes for common IoT vendors (first 3 octets of MAC)
_IOT_OUI_PREFIXES: dict[str, str] = {
    "50:c7:bf": "TP-Link",
    "b0:95:75": "TP-Link",
    "98:da:c4": "TP-Link",
    "00:17:88": "Philips Hue",
    "ec:b5:fa": "Philips Hue",
    "34:ce:00": "Xiaomi",
    "7c:49:eb": "Xiaomi",
    "18:b4:30": "Ring (Amazon)",
    "fc:a1:83": "Ring (Amazon)",
    "68:54:fd": "Amazon Echo",
    "44:00:49": "Amazon Echo",
    "fc:65:de": "Samsung SmartThings",
    "b4:e6:2d": "LG Electronics",
    "a8:23:fe": "LG Electronics",
    "e8:9f:80": "Govee",
    "d4:ad:71": "Ryse",
}


class NetworkScanner:
    """LAN device discovery engine.

    Wraps system tools (nmap, arp-scan) with structured output parsing,
    device classification, and risk scoring. All operations are local.
    """

    def __init__(
        self,
        subnet: str = "192.168.1.0/24",
        audit: AuditLog | None = None,
        known_macs: set[str] | None = None,
    ) -> None:
        if not re.match(r"^[\d]{1,3}(\.[\d]{1,3}){3}/[\d]{1,2}$", subnet):
            raise ValueError(f"Invalid subnet format: {subnet}")
        self._subnet = subnet
        self._audit = audit
        self._known_macs: set[str] = {m.lower() for m in (known_macs or set())}
        self._history: dict[str, DiscoveredDevice] = {}  # MAC -> last seen
        self._scan_count: int = 0

    @property
    def subnet(self) -> str:
        return self._subnet

    @property
    def scan_count(self) -> int:
        return self._scan_count

    def update_known_macs(self, macs: set[str]) -> None:
        """Update the set of known/trusted MAC addresses."""
        self._known_macs = {m.lower() for m in macs}

    # ------------------------------------------------------------------
    # Scanning methods
    # ------------------------------------------------------------------

    def nmap_scan(self, extra_args: list[str] | None = None) -> list[DiscoveredDevice]:
        """Run nmap ping sweep on the subnet.

        Default command: nmap -sn <subnet>
        Returns parsed list of discovered devices.
        """
        if not shutil.which("nmap"):
            self._log("nmap_not_found", Severity.WARNING,
                      {"error": "nmap not installed"})
            return []

        cmd = ["nmap", "-sn", self._subnet]
        if extra_args:
            cmd.extend(extra_args)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
            )
            devices = self._parse_nmap_output(result.stdout)
            self._scan_count += 1
            self._update_history(devices)
            self._log("nmap_scan_complete", Severity.INFO, {
                "subnet": self._subnet,
                "discovered": len(devices),
            })
            return devices
        except subprocess.TimeoutExpired:
            self._log("nmap_timeout", Severity.WARNING, {
                "subnet": self._subnet, "timeout": 120,
            })
            return []
        except OSError as exc:
            self._log("nmap_error", Severity.ERROR, {"error": str(exc)})
            return []

    def arp_scan(self) -> list[DiscoveredDevice]:
        """Parse the system ARP table for quick device lookup.

        Uses `arp -a` (cross-platform) or `ip neigh` (Linux).
        Faster than nmap but only shows recently-communicating devices.
        """
        devices: list[DiscoveredDevice] = []
        now = datetime.now(timezone.utc).isoformat()

        # Try `ip neigh` first (Linux), fall back to `arp -a`
        for cmd in [["ip", "neigh"], ["arp", "-a"]]:
            if not shutil.which(cmd[0]):
                continue
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=10,
                )
                if cmd[0] == "ip":
                    devices = self._parse_ip_neigh(result.stdout, now)
                else:
                    devices = self._parse_arp_a(result.stdout, now)
                break
            except (subprocess.TimeoutExpired, OSError):
                continue

        self._update_history(devices)
        self._log("arp_scan_complete", Severity.INFO, {
            "discovered": len(devices),
        })
        return devices

    def full_scan(self) -> list[DiscoveredDevice]:
        """Run all available scan methods and merge results.

        Prefers nmap data over ARP (more detailed). Deduplicates by MAC.
        """
        merged: dict[str, DiscoveredDevice] = {}

        # ARP first (fast baseline)
        for d in self.arp_scan():
            key = d.mac_address.lower() or d.ip_address
            merged[key] = d

        # nmap overlay (richer data wins)
        for d in self.nmap_scan():
            key = d.mac_address.lower() or d.ip_address
            if key in merged:
                # Merge: nmap data takes priority but keep ARP first_seen
                existing = merged[key]
                d.first_seen = existing.first_seen or d.first_seen
            merged[key] = d

        result = list(merged.values())
        for d in result:
            self._classify(d)

        return result

    # ------------------------------------------------------------------
    # Classification & risk scoring
    # ------------------------------------------------------------------

    def _classify(self, device: DiscoveredDevice) -> None:
        """Classify a device and assign a risk score."""
        mac_lower = device.mac_address.lower()

        if mac_lower in self._known_macs:
            device.device_class = DeviceClassification.KNOWN
            device.risk_score = 1
            return

        # Check OUI prefix for IoT vendors
        prefix = mac_lower[:8] if len(mac_lower) >= 8 else ""
        if prefix in _IOT_OUI_PREFIXES:
            device.device_class = DeviceClassification.IOT
            device.vendor = device.vendor or _IOT_OUI_PREFIXES[prefix]
            device.risk_score = 2
            return

        # Unknown device — higher risk
        device.device_class = DeviceClassification.UNKNOWN
        device.risk_score = 4

        # Elevate risk if suspicious ports are open
        suspicious_ports = {22, 23, 80, 443, 8080, 8443, 5555}
        if device.open_ports and suspicious_ports & set(device.open_ports):
            device.risk_score = 5

    def classify_device(self, device: DiscoveredDevice) -> None:
        """Public API for classification (for testing)."""
        self._classify(device)

    # ------------------------------------------------------------------
    # History & unknown device detection
    # ------------------------------------------------------------------

    def _update_history(self, devices: list[DiscoveredDevice]) -> None:
        """Update scan history with latest results."""
        now = datetime.now(timezone.utc).isoformat()
        for d in devices:
            key = d.mac_address.lower() or d.ip_address
            if key in self._history:
                d.first_seen = self._history[key].first_seen
            else:
                d.first_seen = now
            d.last_seen = now
            self._history[key] = d

    def unknown_devices(self) -> list[DiscoveredDevice]:
        """Return devices not in the known MAC set."""
        return [
            d for d in self._history.values()
            if d.mac_address.lower() not in self._known_macs
        ]

    def new_devices_since(self, since_iso: str) -> list[DiscoveredDevice]:
        """Return devices first seen after the given ISO timestamp."""
        return [
            d for d in self._history.values()
            if d.first_seen > since_iso
        ]

    def history(self) -> list[DiscoveredDevice]:
        """All devices ever seen."""
        return list(self._history.values())

    # ------------------------------------------------------------------
    # Output parsing
    # ------------------------------------------------------------------

    def _parse_nmap_output(self, output: str) -> list[DiscoveredDevice]:
        """Parse nmap -sn output into DiscoveredDevice list."""
        devices: list[DiscoveredDevice] = []
        now = datetime.now(timezone.utc).isoformat()

        # nmap -sn output pattern:
        # Nmap scan report for hostname (ip)
        # Host is up (latency).
        # MAC Address: AA:BB:CC:DD:EE:FF (Vendor)
        current_ip = ""
        current_hostname = ""

        for line in output.splitlines():
            # Match "Nmap scan report for ..." lines
            report_match = re.match(
                r"Nmap scan report for\s+(?:(\S+)\s+\()?(\d+\.\d+\.\d+\.\d+)\)?",
                line,
            )
            if report_match:
                current_hostname = report_match.group(1) or ""
                current_ip = report_match.group(2)
                continue

            # Match MAC address lines
            mac_match = re.match(
                r"MAC Address:\s+([0-9A-Fa-f:]+)\s*(?:\((.+?)\))?",
                line,
            )
            if mac_match and current_ip:
                mac = mac_match.group(1).lower()
                vendor = mac_match.group(2) or ""
                devices.append(DiscoveredDevice(
                    ip_address=current_ip,
                    mac_address=mac,
                    hostname=current_hostname,
                    vendor=vendor,
                    scan_method="nmap",
                    last_seen=now,
                ))
                current_ip = ""
                current_hostname = ""

        return devices

    def _parse_ip_neigh(self, output: str, now: str) -> list[DiscoveredDevice]:
        """Parse `ip neigh` output."""
        devices: list[DiscoveredDevice] = []
        for line in output.splitlines():
            # Format: 192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE
            parts = line.split()
            if len(parts) >= 5 and "lladdr" in parts:
                ip = parts[0]
                lladdr_idx = parts.index("lladdr")
                mac = parts[lladdr_idx + 1].lower() if lladdr_idx + 1 < len(parts) else ""
                if mac and re.match(r"[0-9a-f]{2}(:[0-9a-f]{2}){5}", mac):
                    devices.append(DiscoveredDevice(
                        ip_address=ip,
                        mac_address=mac,
                        scan_method="arp",
                        last_seen=now,
                    ))
        return devices

    def _parse_arp_a(self, output: str, now: str) -> list[DiscoveredDevice]:
        """Parse `arp -a` output."""
        devices: list[DiscoveredDevice] = []
        for line in output.splitlines():
            # Format: hostname (192.168.1.1) at aa:bb:cc:dd:ee:ff [ether] on eth0
            match = re.match(
                r"(\S+)\s+\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([0-9a-fA-F:]+)",
                line,
            )
            if match:
                hostname = match.group(1) if match.group(1) != "?" else ""
                devices.append(DiscoveredDevice(
                    ip_address=match.group(2),
                    mac_address=match.group(3).lower(),
                    hostname=hostname,
                    scan_method="arp",
                    last_seen=now,
                ))
        return devices

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log(self, action: str, severity: Severity, details: dict[str, Any]) -> None:
        if self._audit:
            self._audit.record(
                agent="network_scanner",
                action=action,
                severity=severity,
                details=details,
            )

    def summary(self) -> dict[str, Any]:
        """Summary of scan history."""
        by_class: dict[str, int] = {}
        for d in self._history.values():
            c = d.device_class.value
            by_class[c] = by_class.get(c, 0) + 1

        return {
            "total_scans": self._scan_count,
            "total_devices_seen": len(self._history),
            "by_classification": by_class,
            "unknown_count": len(self.unknown_devices()),
            "subnet": self._subnet,
        }
