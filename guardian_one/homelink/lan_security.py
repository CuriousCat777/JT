"""H.O.M.E. L.I.N.K. LAN Security — DNS blocking, VLAN policy, telemetry audit.

This module defines the network security posture for Jeremy's local network:
- DNS blocklists per vendor (telemetry, analytics, ad-serving)
- VLAN isolation policies (which device categories belong where)
- Network audit that checks the DeviceRegistry against these policies

Guardian One cannot reconfigure the router directly. This module produces
actionable reports for manual or Pi-hole/NextDNS configuration.

All policies are local-first: the goal is to eliminate cloud dependencies
for every device that supports local control.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from guardian_one.homelink.devices import (
    DeviceCategory,
    DeviceRecord,
    DeviceRegistry,
    NetworkSegment,
)


# ---------------------------------------------------------------------------
# DNS blocklists — telemetry domains to block per vendor
# ---------------------------------------------------------------------------

@dataclass
class DnsBlocklist:
    """Domains to block at DNS level for a specific vendor/device."""
    vendor: str
    description: str
    domains: list[str] = field(default_factory=list)
    wildcard_domains: list[str] = field(default_factory=list)
    notes: str = ""


# Vendor-specific blocklists derived from device documentation and traffic analysis
KASA_BLOCKLIST = DnsBlocklist(
    vendor="TP-Link Kasa",
    description="Block cloud dependency — python-kasa uses local encrypted TCP only",
    domains=[
        "n-devs.tplinkcloud.com",
        "n-deventry.tplinkcloud.com",
        "euw1-api.tplinkra.com",
        "use1-api.tplinkra.com",
    ],
    wildcard_domains=["*.tplinkcloud.com", "*.tplinkra.com"],
    notes="Kasa plugs work 100% locally via python-kasa. Blocking cloud "
          "prevents firmware auto-updates and telemetry. Check firmware "
          "manually via python-kasa before blocking.",
)

HUE_BLOCKLIST = DnsBlocklist(
    vendor="Philips Hue",
    description="Block cloud — Hue Bridge has local HTTPS API on port 443",
    domains=[
        "diagnostics.meethue.com",
        "www2.meethue.com",
    ],
    wildcard_domains=["*.meethue.com"],
    notes="Hue Bridge API works fully local. Blocking meethue.com disables "
          "remote access via Hue app (keep local app or use phue library). "
          "Bridge firmware updates require temporary unblock.",
)

GOVEE_BLOCKLIST = DnsBlocklist(
    vendor="Govee",
    description="Block cloud — Govee LAN UDP on port 4003 for local control",
    domains=[
        "app2.govee.com",
        "openapi.govee.com",
        "community-api.govee.com",
    ],
    wildcard_domains=["*.govee.com"],
    notes="Govee LAN control must be enabled once in the Govee app before "
          "blocking cloud. After that, UDP 4003 works without internet. "
          "BLE control via Govee Home app still works locally.",
)

LG_TV_BLOCKLIST = DnsBlocklist(
    vendor="LG WebOS TV",
    description="Block telemetry, ACR, and ad-serving while keeping SSAP local API",
    domains=[
        "ngfts.lge.com",
        "aic-ngfts.lge.com",
        "ibs.lgappstv.com",
        "us.rdx2.lgtvsdp.com",
        "eu.rdx2.lgtvsdp.com",
        "lgad.cjpowercast.com",
        "edgesuite.net",
        "us.info.lgsmartad.com",
        "ad.lgappstv.com",
        "sg.lgtvcommon.com",
        "samsungacr.com",  # Sometimes resolved by LG TVs too
    ],
    wildcard_domains=[
        "*.lgtvcommon.com",
        "*.lgappstv.com",
        "*.lgsmartad.com",
        "*.lgtvsdp.com",
    ],
    notes="CRITICAL: Disable ACR (Automatic Content Recognition) in "
          "Settings > General > Live Plus BEFORE blocking DNS. "
          "SSAP local API for power/input/volume works without internet.",
)

RING_BLOCKLIST = DnsBlocklist(
    vendor="Ring (Amazon)",
    description="CANNOT fully block — Ring is 100% cloud-dependent",
    domains=[],
    wildcard_domains=[],
    notes="WARNING: Blocking Ring domains will disable ALL Ring functionality. "
          "Ring has NO local API. Long-term plan: replace with local RTSP "
          "cameras + Frigate NVR. Until then, Ring stays on cloud. "
          "Consider blocking Ring on guest network only.",
)

ECHO_BLOCKLIST = DnsBlocklist(
    vendor="Amazon Echo",
    description="CANNOT block without disabling device entirely",
    domains=[],
    wildcard_domains=[],
    notes="Echo Dots are 100% cloud-dependent. All voice processing happens "
          "on Amazon servers. Mitigation: disable mic when not in use, "
          "review Alexa Privacy Settings, delete voice recordings regularly.",
)

RYSE_BLOCKLIST = DnsBlocklist(
    vendor="Ryse SmartBridge",
    description="Block cloud — SmartBridge SB-B101 has local REST API",
    domains=[],
    wildcard_domains=["*.ryseup.com", "*.rysesmarthome.com"],
    notes="Ryse SmartBridge has local REST API over WiFi. Block cloud "
          "to prevent telemetry. BLE control works locally regardless.",
)

ALL_BLOCKLISTS: list[DnsBlocklist] = [
    KASA_BLOCKLIST,
    HUE_BLOCKLIST,
    GOVEE_BLOCKLIST,
    LG_TV_BLOCKLIST,
    RING_BLOCKLIST,
    ECHO_BLOCKLIST,
    RYSE_BLOCKLIST,
]


# ---------------------------------------------------------------------------
# VLAN isolation policy
# ---------------------------------------------------------------------------

@dataclass
class VlanPolicy:
    """Defines which device categories should be on which network segment."""
    category: DeviceCategory
    required_segment: NetworkSegment
    reason: str


VLAN_POLICIES: list[VlanPolicy] = [
    VlanPolicy(
        DeviceCategory.SMART_PLUG, NetworkSegment.IOT_VLAN,
        "Smart plugs should be isolated from trusted LAN to prevent lateral movement",
    ),
    VlanPolicy(
        DeviceCategory.SMART_LIGHT, NetworkSegment.IOT_VLAN,
        "Smart lights (Govee, Hue) should be on IoT VLAN — Zigbee mesh "
        "contained by Hue Bridge which should also be on IoT VLAN",
    ),
    VlanPolicy(
        DeviceCategory.SMART_BLIND, NetworkSegment.IOT_VLAN,
        "Ryse SmartShade on IoT VLAN — local REST API only needs LAN access",
    ),
    VlanPolicy(
        DeviceCategory.SMART_TV, NetworkSegment.IOT_VLAN,
        "LG TV is a telemetry risk — isolate on IoT VLAN and block outbound",
    ),
    VlanPolicy(
        DeviceCategory.SECURITY_CAMERA, NetworkSegment.IOT_VLAN,
        "Cameras on IoT VLAN — Ring needs internet but should be isolated "
        "from trusted LAN. Future RTSP cameras will be local-only.",
    ),
    VlanPolicy(
        DeviceCategory.MEDIA_PLAYER, NetworkSegment.IOT_VLAN,
        "Echo Dots on IoT VLAN — always-listening devices must be isolated",
    ),
    VlanPolicy(
        DeviceCategory.SENSOR, NetworkSegment.IOT_VLAN,
        "Ring sensors communicate via Z-Wave through base station — IoT VLAN",
    ),
    VlanPolicy(
        DeviceCategory.MOTION_DETECTOR, NetworkSegment.IOT_VLAN,
        "Motion detectors on IoT VLAN via Ring base station",
    ),
    VlanPolicy(
        DeviceCategory.NETWORK_INFRA, NetworkSegment.TRUSTED_LAN,
        "Network infrastructure (router, switches, bridges) stays on trusted LAN",
    ),
    VlanPolicy(
        DeviceCategory.SECURITY_TOOL, NetworkSegment.NOT_NETWORKED,
        "Flipper Zero is USB-only — should never be on the network",
    ),
]


# ---------------------------------------------------------------------------
# LAN security auditor
# ---------------------------------------------------------------------------

class LanSecurityAuditor:
    """Audits the device registry against LAN security policies.

    Produces actionable reports on:
    - VLAN isolation violations
    - Missing DNS blocks
    - Cloud-dependent devices that should be local
    - Devices with default credentials
    """

    def __init__(self, registry: DeviceRegistry) -> None:
        self._registry = registry

    def vlan_violations(self) -> list[dict[str, str]]:
        """Check all devices against VLAN isolation policies."""
        violations: list[dict[str, str]] = []
        policy_map = {p.category: p for p in VLAN_POLICIES}

        for device in self._registry.all_devices():
            policy = policy_map.get(device.category)
            if not policy:
                continue
            if device.network_segment != policy.required_segment:
                violations.append({
                    "device_id": device.device_id,
                    "name": device.name,
                    "current_segment": device.network_segment.value,
                    "required_segment": policy.required_segment.value,
                    "reason": policy.reason,
                })
        return violations

    def cloud_dependent_devices(self) -> list[dict[str, str]]:
        """List devices that depend on cloud APIs (exposure risks)."""
        cloud_devices: list[dict[str, str]] = []
        for device in self._registry.all_devices():
            if not device.local_api_only and device.category not in (
                DeviceCategory.NETWORK_INFRA,
                DeviceCategory.VEHICLE,
            ):
                cloud_devices.append({
                    "device_id": device.device_id,
                    "name": device.name,
                    "manufacturer": device.manufacturer,
                    "category": device.category.value,
                    "risk": "Cloud-dependent — data leaves local network",
                })
        return cloud_devices

    def dns_block_report(self) -> dict[str, Any]:
        """Generate a Pi-hole/NextDNS configuration report."""
        all_domains: list[str] = []
        all_wildcards: list[str] = []
        vendor_report: list[dict[str, Any]] = []

        for bl in ALL_BLOCKLISTS:
            all_domains.extend(bl.domains)
            all_wildcards.extend(bl.wildcard_domains)
            vendor_report.append({
                "vendor": bl.vendor,
                "description": bl.description,
                "domains": bl.domains,
                "wildcards": bl.wildcard_domains,
                "blockable": len(bl.domains) + len(bl.wildcard_domains) > 0,
                "notes": bl.notes,
            })

        return {
            "total_domains": len(all_domains),
            "total_wildcards": len(all_wildcards),
            "vendors": vendor_report,
            "pihole_blocklist": sorted(set(all_domains)),
            "pihole_wildcards": sorted(set(all_wildcards)),
        }

    def default_credential_devices(self) -> list[dict[str, str]]:
        """Devices that haven't confirmed password change."""
        return [
            {
                "device_id": d.device_id,
                "name": d.name,
                "severity": "critical",
            }
            for d in self._registry.all_devices()
            if not d.default_password_changed
        ]

    def full_audit(self) -> dict[str, Any]:
        """Run all LAN security checks and return a comprehensive report."""
        vlan = self.vlan_violations()
        cloud = self.cloud_dependent_devices()
        dns = self.dns_block_report()
        creds = self.default_credential_devices()

        # Risk score: 1 (good) to 5 (critical)
        risk = 1
        if len(creds) > 0:
            risk = max(risk, 4)
        if len(vlan) > 3:
            risk = max(risk, 3)
        if len(cloud) > 5:
            risk = max(risk, 3)
        if dns["total_domains"] > 0 and not _dns_blocking_deployed():
            risk = max(risk, 3)

        return {
            "vlan_violations": vlan,
            "vlan_violation_count": len(vlan),
            "cloud_dependent_devices": cloud,
            "cloud_dependent_count": len(cloud),
            "dns_block_report": dns,
            "default_credential_devices": creds,
            "default_credential_count": len(creds),
            "risk_score": risk,
            "summary": (
                f"LAN Security: {len(vlan)} VLAN violations, "
                f"{len(cloud)} cloud-dependent devices, "
                f"{len(creds)} default credentials, "
                f"risk {risk}/5"
            ),
            "action_items": _action_items(vlan, cloud, dns, creds),
        }

    def audit_text(self) -> str:
        """Human-readable LAN security audit report."""
        audit = self.full_audit()
        lines = [
            "=" * 60,
            "  H.O.M.E. L.I.N.K. — LAN SECURITY AUDIT",
            "=" * 60,
            "",
            f"  Risk Score: {audit['risk_score']}/5",
            "",
        ]

        # VLAN
        lines.append("── VLAN ISOLATION ──────────────────────────────")
        if audit["vlan_violations"]:
            for v in audit["vlan_violations"]:
                lines.append(
                    f"  ⚠ {v['name']} ({v['device_id']}): "
                    f"on {v['current_segment']}, should be {v['required_segment']}"
                )
        else:
            lines.append("  ✓ All devices on correct segments")

        # Cloud
        lines.append("")
        lines.append("── CLOUD DEPENDENCIES ─────────────────────────")
        for c in audit["cloud_dependent_devices"]:
            lines.append(f"  ⚠ {c['name']}: {c['risk']}")

        # DNS
        lines.append("")
        lines.append("── DNS BLOCKING ───────────────────────────────")
        dns = audit["dns_block_report"]
        lines.append(f"  Domains to block: {dns['total_domains']}")
        lines.append(f"  Wildcard rules: {dns['total_wildcards']}")
        for v in dns["vendors"]:
            status = "BLOCKABLE" if v["blockable"] else "CANNOT BLOCK"
            lines.append(f"  {v['vendor']}: {status}")

        # Credentials
        lines.append("")
        lines.append("── DEFAULT CREDENTIALS ────────────────────────")
        if audit["default_credential_devices"]:
            for c in audit["default_credential_devices"]:
                lines.append(f"  ✗ {c['name']} — change password immediately")
        else:
            lines.append("  ✓ All passwords changed")

        # Action items
        lines.append("")
        lines.append("── ACTION ITEMS ───────────────────────────────")
        for i, item in enumerate(audit["action_items"], 1):
            lines.append(f"  {i}. [{item['priority']}] {item['action']}")

        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dns_blocking_deployed() -> bool:
    """Check if Pi-hole or NextDNS is deployed.

    Probes pihole.local (the default Pi-hole hostname) via a quick TCP
    connect on port 80.  Returns True if a DNS-blocking appliance
    appears reachable on the LAN.
    """
    import socket

    for host in ("pihole.local", "pi.hole"):
        try:
            with socket.create_connection((host, 80), timeout=2):
                return True
        except OSError:
            continue
    return False


def _action_items(
    vlan: list[dict], cloud: list[dict],
    dns: dict[str, Any], creds: list[dict],
) -> list[dict[str, str]]:
    """Generate prioritized action items from audit findings."""
    items: list[dict[str, str]] = []

    if creds:
        items.append({
            "priority": "CRITICAL",
            "action": f"Change default passwords on {len(creds)} device(s)",
        })

    if not _dns_blocking_deployed():
        items.append({
            "priority": "HIGH",
            "action": "Deploy Pi-hole or NextDNS for DNS-level telemetry blocking. "
                      f"{dns['total_domains']} domains + {dns['total_wildcards']} "
                      "wildcards ready to block.",
        })

    if vlan:
        items.append({
            "priority": "HIGH",
            "action": f"Fix {len(vlan)} VLAN isolation violation(s) — "
                      "IoT devices on trusted LAN. Note: Spectrum SAX2V1S may not "
                      "support VLANs — consider Ubiquiti Dream Machine or similar.",
        })

    if cloud:
        items.append({
            "priority": "MEDIUM",
            "action": f"{len(cloud)} cloud-dependent device(s) — plan migration "
                      "to local-only alternatives where possible.",
        })

    items.append({
        "priority": "LOW",
        "action": "Enable LAN Control in Govee app for all Govee devices "
                  "(required once before DNS blocking).",
    })

    return items
