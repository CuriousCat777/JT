"""H.O.M.E. L.I.N.K. Device Management — IoT, LAN, and smart device inventory.

Manages Jeremy's local network devices including:
- Security cameras and motion detectors
- Smart plugs (TP-Link Kasa/Tapo)
- Smart lights (Philips Hue, Govee)
- Smart TV
- Connected vehicle (OBD-II / manufacturer API)
- Flipper Zero (RF/NFC/IR security tool)
- Network infrastructure (router, switches, APs)

All device communication routes through the Gateway with full audit trail.
Device credentials stored in Vault. Threat models in Registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Device model
# ---------------------------------------------------------------------------

class DeviceCategory(Enum):
    SECURITY_CAMERA = "security_camera"
    MOTION_DETECTOR = "motion_detector"
    SMART_PLUG = "smart_plug"
    SMART_LIGHT = "smart_light"
    SMART_TV = "smart_tv"
    VEHICLE = "vehicle"
    SECURITY_TOOL = "security_tool"
    NETWORK_INFRA = "network_infra"
    MEDIA_PLAYER = "media_player"
    SENSOR = "sensor"
    OTHER = "other"


class DeviceProtocol(Enum):
    """Communication protocols used by IoT devices."""
    WIFI = "wifi"
    ZIGBEE = "zigbee"
    ZWAVE = "z-wave"
    BLUETOOTH = "bluetooth"
    BLE = "ble"
    MATTER = "matter"
    LAN_API = "lan_api"          # Local HTTP/REST API
    CLOUD_API = "cloud_api"      # Vendor cloud API
    RF_433 = "rf_433mhz"
    RF_868 = "rf_868mhz"
    RF_SUB_GHZ = "rf_sub_ghz"   # Flipper Zero sub-GHz
    NFC = "nfc"
    IR = "infrared"
    OBD2 = "obd2"               # Vehicle diagnostics
    MQTT = "mqtt"
    USB = "usb"


class DeviceStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    STANDBY = "standby"
    ERROR = "error"
    UNKNOWN = "unknown"
    FIRMWARE_UPDATE = "firmware_update"


class NetworkSegment(Enum):
    """VLAN / network segment for device isolation."""
    IOT_VLAN = "iot_vlan"           # Isolated IoT VLAN (recommended)
    TRUSTED_LAN = "trusted_lan"     # Main trusted network
    GUEST = "guest"                 # Guest network
    DMZ = "dmz"                     # Exposed services
    NOT_NETWORKED = "not_networked" # USB/Bluetooth only devices


@dataclass
class FirmwareInfo:
    """Firmware version tracking for update management."""
    current_version: str = "unknown"
    latest_available: str = "unknown"
    auto_update: bool = False
    last_checked: str = ""
    update_url: str = ""


@dataclass
class DeviceRecord:
    """A device on the local network or connected ecosystem."""

    # Identity
    device_id: str                        # Unique identifier (e.g., "cam-front-door")
    name: str                             # Human-readable name
    category: DeviceCategory
    manufacturer: str
    model: str = ""

    # Network
    ip_address: str = ""                  # LAN IP (static recommended for cameras)
    mac_address: str = ""                 # For MAC-based access control
    protocols: list[DeviceProtocol] = field(default_factory=list)
    network_segment: NetworkSegment = NetworkSegment.IOT_VLAN
    hostname: str = ""

    # Status
    status: DeviceStatus = DeviceStatus.UNKNOWN
    last_seen: str = ""
    firmware: FirmwareInfo = field(default_factory=FirmwareInfo)

    # Security
    default_password_changed: bool = False
    upnp_disabled: bool = False
    local_api_only: bool = False          # True = no cloud dependency
    encryption_enabled: bool = False
    vault_credential_key: str = ""        # Key name in Vault for this device's auth

    # Integration
    integration_name: str = ""            # Matches IntegrationRegistry name
    owner_agent: str = "device_agent"
    location: str = ""                    # Physical location (e.g., "front_door", "living_room")

    # Metadata
    notes: str = ""
    added_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Device registry
# ---------------------------------------------------------------------------

class DeviceRegistry:
    """Inventory of all managed local devices.

    Every device Jeremy owns gets registered here with its security posture,
    network location, and protocol information. The DeviceAgent uses this
    to monitor health, detect unauthorized devices, and enforce policies.
    """

    def __init__(self) -> None:
        self._devices: dict[str, DeviceRecord] = {}

    def register(self, device: DeviceRecord) -> None:
        self._devices[device.device_id] = device

    def get(self, device_id: str) -> DeviceRecord | None:
        return self._devices.get(device_id)

    def remove(self, device_id: str) -> bool:
        return self._devices.pop(device_id, None) is not None

    def all_devices(self) -> list[DeviceRecord]:
        return list(self._devices.values())

    def by_category(self, category: DeviceCategory) -> list[DeviceRecord]:
        return [d for d in self._devices.values() if d.category == category]

    def by_segment(self, segment: NetworkSegment) -> list[DeviceRecord]:
        return [d for d in self._devices.values() if d.network_segment == segment]

    def by_protocol(self, protocol: DeviceProtocol) -> list[DeviceRecord]:
        return [d for d in self._devices.values() if protocol in d.protocols]

    def by_status(self, status: DeviceStatus) -> list[DeviceRecord]:
        return [d for d in self._devices.values() if d.status == status]

    def by_location(self, location: str) -> list[DeviceRecord]:
        return [d for d in self._devices.values()
                if d.location.lower() == location.lower()]

    def update_status(self, device_id: str, status: DeviceStatus) -> bool:
        device = self._devices.get(device_id)
        if device:
            device.status = status
            device.last_seen = datetime.now(timezone.utc).isoformat()
            return True
        return False

    # ------------------------------------------------------------------
    # Security auditing
    # ------------------------------------------------------------------

    def security_audit(self) -> dict[str, Any]:
        """Audit device inventory for security issues."""
        devices = self.all_devices()
        if not devices:
            return {
                "total_devices": 0,
                "issues": [],
                "risk_score": 0,
                "summary": "No devices registered.",
            }

        issues: list[dict[str, str]] = []
        for d in devices:
            if not d.default_password_changed:
                issues.append({
                    "device": d.device_id,
                    "severity": "critical",
                    "issue": "Default password not changed",
                })
            if not d.upnp_disabled:
                issues.append({
                    "device": d.device_id,
                    "severity": "high",
                    "issue": "UPnP not confirmed disabled",
                })
            if d.network_segment == NetworkSegment.TRUSTED_LAN and d.category in (
                DeviceCategory.SECURITY_CAMERA, DeviceCategory.SMART_PLUG,
                DeviceCategory.SMART_LIGHT, DeviceCategory.SMART_TV,
            ):
                issues.append({
                    "device": d.device_id,
                    "severity": "high",
                    "issue": f"IoT device on trusted LAN — isolate to {NetworkSegment.IOT_VLAN.value}",
                })
            if not d.local_api_only and d.category == DeviceCategory.SECURITY_CAMERA:
                issues.append({
                    "device": d.device_id,
                    "severity": "high",
                    "issue": "Security camera depends on cloud — prefer local-only API",
                })
            if d.firmware.current_version == "unknown":
                issues.append({
                    "device": d.device_id,
                    "severity": "medium",
                    "issue": "Firmware version unknown — check for updates",
                })
            if not d.encryption_enabled and d.category == DeviceCategory.SECURITY_CAMERA:
                issues.append({
                    "device": d.device_id,
                    "severity": "high",
                    "issue": "Camera stream not encrypted — enable HTTPS/RTMPS",
                })

        critical = sum(1 for i in issues if i["severity"] == "critical")
        high = sum(1 for i in issues if i["severity"] == "high")
        risk_score = min(5, 1 + critical * 2 + high)

        return {
            "total_devices": len(devices),
            "online": len(self.by_status(DeviceStatus.ONLINE)),
            "offline": len(self.by_status(DeviceStatus.OFFLINE)),
            "issues": sorted(issues, key=lambda i: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(i["severity"], 4)),
            "issue_count": len(issues),
            "risk_score": risk_score,
            "summary": f"{len(devices)} devices, {len(issues)} issues, risk {risk_score}/5",
        }

    def device_count_by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for d in self._devices.values():
            key = d.category.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Load Jeremy's known devices
    # ------------------------------------------------------------------

    def load_defaults(self) -> None:
        """Register all of Jeremy's known devices."""
        for device in _jeremys_devices():
            self.register(device)


# ---------------------------------------------------------------------------
# Jeremy's device inventory
# ---------------------------------------------------------------------------

def _jeremys_devices() -> list[DeviceRecord]:
    """Jeremy's actual device inventory.

    All devices start as UNKNOWN status until the DeviceAgent
    performs its first network scan and updates them.
    """
    return [
        # --- Security cameras ---
        DeviceRecord(
            device_id="cam-01",
            name="Security Camera 1",
            category=DeviceCategory.SECURITY_CAMERA,
            manufacturer="Unknown",
            protocols=[DeviceProtocol.WIFI, DeviceProtocol.LAN_API],
            network_segment=NetworkSegment.IOT_VLAN,
            local_api_only=False,
            notes="Verify manufacturer and model. Move to local NVR if cloud-dependent. "
                  "Enable RTSP over TLS if supported.",
            tags=["security", "surveillance"],
        ),

        # --- Motion detectors ---
        DeviceRecord(
            device_id="motion-01",
            name="Motion Detector 1",
            category=DeviceCategory.MOTION_DETECTOR,
            manufacturer="Unknown",
            protocols=[DeviceProtocol.WIFI],
            network_segment=NetworkSegment.IOT_VLAN,
            notes="Verify protocol (Zigbee/Z-Wave/WiFi). Pair with security cameras for alerts.",
            tags=["security", "automation"],
        ),

        # --- Smart TV ---
        DeviceRecord(
            device_id="tv-main",
            name="Smart TV",
            category=DeviceCategory.SMART_TV,
            manufacturer="Unknown",
            protocols=[DeviceProtocol.WIFI, DeviceProtocol.LAN_API],
            network_segment=NetworkSegment.IOT_VLAN,
            notes="Disable ACR (Automatic Content Recognition). Block telemetry domains "
                  "at router/Pi-hole level. Disable UPnP. Use HDMI input from a "
                  "trusted device when possible.",
            tags=["entertainment", "iot"],
        ),

        # --- Smart plugs (TP-Link) ---
        DeviceRecord(
            device_id="plug-tplink-01",
            name="TP-Link Smart Plug 1",
            category=DeviceCategory.SMART_PLUG,
            manufacturer="TP-Link",
            protocols=[DeviceProtocol.WIFI, DeviceProtocol.LAN_API],
            network_segment=NetworkSegment.IOT_VLAN,
            local_api_only=True,
            integration_name="tplink_kasa",
            notes="TP-Link Kasa/Tapo plugs support local API via python-kasa library. "
                  "Block cloud access at router for local-only mode.",
            tags=["smart_home", "energy"],
        ),

        # --- Smart lights (Philips Hue) ---
        DeviceRecord(
            device_id="light-hue-bridge",
            name="Philips Hue Bridge",
            category=DeviceCategory.SMART_LIGHT,
            manufacturer="Philips",
            model="Hue Bridge",
            protocols=[DeviceProtocol.ZIGBEE, DeviceProtocol.LAN_API],
            network_segment=NetworkSegment.IOT_VLAN,
            local_api_only=True,
            encryption_enabled=True,
            integration_name="philips_hue",
            notes="Hue Bridge controls all Hue bulbs via Zigbee. Local API on port 443. "
                  "API key stored in Vault. Block cloud access for local-only mode. "
                  "Bridge is the only Hue device that needs WiFi/LAN.",
            vault_credential_key="HUE_BRIDGE_API_KEY",
            tags=["smart_home", "lighting"],
        ),

        # --- Smart lights (Govee) ---
        DeviceRecord(
            device_id="light-govee-01",
            name="Govee Light Strip/Bulb",
            category=DeviceCategory.SMART_LIGHT,
            manufacturer="Govee",
            protocols=[DeviceProtocol.WIFI, DeviceProtocol.BLE, DeviceProtocol.LAN_API],
            network_segment=NetworkSegment.IOT_VLAN,
            integration_name="govee",
            notes="Govee devices support local LAN API (UDP broadcast) on newer models. "
                  "Older models require cloud API. Check model for local control support. "
                  "BLE control available via govee-bt-client.",
            vault_credential_key="GOVEE_API_KEY",
            tags=["smart_home", "lighting", "rgb"],
        ),

        # --- Connected vehicle ---
        DeviceRecord(
            device_id="vehicle-01",
            name="Connected Vehicle",
            category=DeviceCategory.VEHICLE,
            manufacturer="Unknown",
            protocols=[DeviceProtocol.OBD2, DeviceProtocol.CLOUD_API],
            network_segment=NetworkSegment.NOT_NETWORKED,
            notes="Vehicle telematics: GPS, diagnostics, remote start/lock. "
                  "OBD-II dongle for local diagnostics (ELM327 compatible). "
                  "Manufacturer app/API for remote features. "
                  "CRITICAL: Disable remote access when vehicle is unattended for extended periods. "
                  "Review manufacturer API for data sharing/selling practices.",
            tags=["vehicle", "telematics"],
        ),

        # --- Flipper Zero ---
        DeviceRecord(
            device_id="flipper-zero",
            name="Flipper Zero",
            category=DeviceCategory.SECURITY_TOOL,
            manufacturer="Flipper Devices",
            model="Flipper Zero",
            protocols=[
                DeviceProtocol.RF_SUB_GHZ, DeviceProtocol.NFC,
                DeviceProtocol.IR, DeviceProtocol.BLE,
                DeviceProtocol.USB,
            ],
            network_segment=NetworkSegment.NOT_NETWORKED,
            local_api_only=True,
            notes="Multi-tool for security research: sub-GHz, NFC, RFID, IR, GPIO. "
                  "USB connection only — no WiFi (unless WiFi dev board attached). "
                  "Use for: testing IoT device security, cloning access badges (authorized only), "
                  "IR remote learning, sub-GHz signal analysis. "
                  "KEEP FIRMWARE UPDATED via qFlipper or Flipper mobile app. "
                  "LEGAL: Only use on devices you own or have written authorization to test.",
            firmware=FirmwareInfo(auto_update=False),
            tags=["security", "pentest", "research"],
        ),
    ]
