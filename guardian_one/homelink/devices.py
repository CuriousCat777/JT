"""H.O.M.E. L.I.N.K. Device Management — IoT, LAN, and smart device inventory.

Manages Jeremy's local network devices including:
- Security cameras and motion detectors
- Smart plugs (TP-Link Kasa/Tapo)
- Smart lights (Philips Hue, Govee)
- Smart blinds (Ryse SmartShades)
- Smart TV
- Connected vehicle (OBD-II / manufacturer API)
- Flipper Zero (RF/NFC/IR security tool)
- Network infrastructure (router, switches, APs)

Naming convention:  {category}-{location}-{index}
  Examples: cam-front-door-01, light-hue-bedroom-01, blind-ryse-living-01

Room model maps physical rooms to device groups for automations.
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
    SMART_BLIND = "smart_blind"
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
# Room model — maps physical spaces to device groups
# ---------------------------------------------------------------------------

class RoomType(Enum):
    BEDROOM = "bedroom"
    LIVING_ROOM = "living_room"
    KITCHEN = "kitchen"
    BATHROOM = "bathroom"
    OFFICE = "office"
    HALLWAY = "hallway"
    GARAGE = "garage"
    EXTERIOR = "exterior"
    ENTRY = "entry"
    OTHER = "other"


@dataclass
class Room:
    """A physical room/zone with associated devices and automation policies."""
    room_id: str                          # e.g., "bedroom-master"
    name: str                             # e.g., "Master Bedroom"
    room_type: RoomType
    floor: int = 1                        # Floor number (1 = ground)
    device_ids: list[str] = field(default_factory=list)
    # Automation policies for this room
    auto_lights: bool = True              # Auto lights on occupancy
    auto_blinds: bool = True              # Auto blinds on schedule
    occupancy_sensor_id: str = ""         # Motion detector for this room
    notes: str = ""


# ---------------------------------------------------------------------------
# Flipper Zero capabilities model
# ---------------------------------------------------------------------------

class FlipperCapability(Enum):
    """What the Flipper Zero can do for each device."""
    IR_CAPTURE = "ir_capture"             # Learn IR remote codes
    IR_TRANSMIT = "ir_transmit"           # Send IR commands
    SUB_GHZ_CAPTURE = "sub_ghz_capture"   # Record sub-GHz signals
    SUB_GHZ_TRANSMIT = "sub_ghz_transmit" # Replay sub-GHz signals
    NFC_READ = "nfc_read"                 # Read NFC tags
    NFC_EMULATE = "nfc_emulate"           # Emulate NFC tags
    BLE_SCAN = "ble_scan"                 # Scan BLE devices
    GPIO_CONTROL = "gpio_control"         # GPIO pin control


@dataclass
class FlipperProfile:
    """Maps a device to its Flipper Zero interaction capabilities."""
    device_id: str                        # Which device this profile is for
    capabilities: list[FlipperCapability] = field(default_factory=list)
    ir_remote_file: str = ""              # Path to .ir file on Flipper SD
    sub_ghz_file: str = ""                # Path to .sub file on Flipper SD
    notes: str = ""
    tested: bool = False                  # Has this been verified working?
    last_tested: str = ""


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
        self._rooms: dict[str, Room] = {}
        self._flipper_profiles: dict[str, FlipperProfile] = {}

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
    # Room management
    # ------------------------------------------------------------------

    def add_room(self, room: Room) -> None:
        self._rooms[room.room_id] = room

    def get_room(self, room_id: str) -> Room | None:
        return self._rooms.get(room_id)

    def all_rooms(self) -> list[Room]:
        return list(self._rooms.values())

    def devices_in_room(self, room_id: str) -> list[DeviceRecord]:
        room = self._rooms.get(room_id)
        if not room:
            return []
        return [d for d in self._devices.values() if d.device_id in room.device_ids]

    def room_for_device(self, device_id: str) -> Room | None:
        for room in self._rooms.values():
            if device_id in room.device_ids:
                return room
        return None

    def rooms_by_type(self, room_type: RoomType) -> list[Room]:
        return [r for r in self._rooms.values() if r.room_type == room_type]

    def room_summary(self) -> list[dict[str, Any]]:
        """Summary of all rooms with device counts."""
        result = []
        for room in self._rooms.values():
            devices = self.devices_in_room(room.room_id)
            result.append({
                "room_id": room.room_id,
                "name": room.name,
                "type": room.room_type.value,
                "device_count": len(devices),
                "device_ids": [d.device_id for d in devices],
                "auto_lights": room.auto_lights,
                "auto_blinds": room.auto_blinds,
            })
        return result

    # ------------------------------------------------------------------
    # Flipper Zero profiles
    # ------------------------------------------------------------------

    def add_flipper_profile(self, profile: FlipperProfile) -> None:
        self._flipper_profiles[profile.device_id] = profile

    def get_flipper_profile(self, device_id: str) -> FlipperProfile | None:
        return self._flipper_profiles.get(device_id)

    def all_flipper_profiles(self) -> list[FlipperProfile]:
        return list(self._flipper_profiles.values())

    def flipper_controllable_devices(self) -> list[DeviceRecord]:
        """Devices that have a Flipper profile (IR/sub-GHz/NFC control)."""
        return [
            d for d in self._devices.values()
            if d.device_id in self._flipper_profiles
        ]

    # ------------------------------------------------------------------
    # Load Jeremy's known devices
    # ------------------------------------------------------------------

    def load_defaults(self) -> None:
        """Register all of Jeremy's known devices, rooms, and Flipper profiles."""
        for device in _jeremys_devices():
            self.register(device)
        for room in _jeremys_rooms():
            self.add_room(room)
        for profile in _jeremys_flipper_profiles():
            self.add_flipper_profile(profile)


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

        # --- Smart blinds (Ryse SmartShades) ---
        DeviceRecord(
            device_id="blind-ryse-01",
            name="Ryse SmartShade Motor 1",
            category=DeviceCategory.SMART_BLIND,
            manufacturer="Ryse",
            model="SmartShade",
            protocols=[DeviceProtocol.BLE, DeviceProtocol.WIFI, DeviceProtocol.CLOUD_API],
            network_segment=NetworkSegment.IOT_VLAN,
            integration_name="ryse_smartshade",
            notes="Ryse SmartShade motorizes existing blinds. BLE for local control, "
                  "WiFi via SmartBridge for remote/automation. Supports open/close/position. "
                  "Schedule via Chronos: open at sunrise, close at sunset. "
                  "Controllable via Flipper Zero IR if IR receiver present. "
                  "Guardian One can send commands through SmartBridge local API or cloud.",
            vault_credential_key="RYSE_API_KEY",
            location="living_room",
            tags=["smart_home", "blinds", "automation", "chronos"],
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


# ---------------------------------------------------------------------------
# Jeremy's room layout
# ---------------------------------------------------------------------------

def _jeremys_rooms() -> list[Room]:
    """Room definitions mapping physical spaces to device groups."""
    return [
        Room(
            room_id="living-room",
            name="Living Room",
            room_type=RoomType.LIVING_ROOM,
            device_ids=[
                "tv-main", "light-govee-01", "plug-tplink-01",
                "blind-ryse-01", "motion-01",
            ],
            auto_lights=True,
            auto_blinds=True,
            occupancy_sensor_id="motion-01",
        ),
        Room(
            room_id="bedroom-master",
            name="Master Bedroom",
            room_type=RoomType.BEDROOM,
            device_ids=["light-hue-bridge"],
            auto_lights=True,
            auto_blinds=True,
            notes="Hue bridge here controls all Hue bulbs house-wide via Zigbee.",
        ),
        Room(
            room_id="office",
            name="Office",
            room_type=RoomType.OFFICE,
            device_ids=["flipper-zero"],
            auto_lights=True,
            auto_blinds=False,
            notes="Primary workspace. Flipper Zero USB-connected to workstation.",
        ),
        Room(
            room_id="exterior-front",
            name="Front Exterior",
            room_type=RoomType.EXTERIOR,
            device_ids=["cam-01"],
            auto_lights=False,
            auto_blinds=False,
            notes="Front-facing security camera. Motion detection for alerts.",
        ),
        Room(
            room_id="garage",
            name="Garage",
            room_type=RoomType.GARAGE,
            device_ids=["vehicle-01"],
            auto_lights=False,
            auto_blinds=False,
        ),
    ]


# ---------------------------------------------------------------------------
# Flipper Zero interaction profiles
# ---------------------------------------------------------------------------

def _jeremys_flipper_profiles() -> list[FlipperProfile]:
    """Defines how the Flipper Zero can interact with each device.

    These profiles tell the DeviceAgent which devices can be controlled,
    audited, or tested via the Flipper Zero.
    """
    return [
        FlipperProfile(
            device_id="tv-main",
            capabilities=[
                FlipperCapability.IR_CAPTURE,
                FlipperCapability.IR_TRANSMIT,
            ],
            ir_remote_file="infrared/tv_main.ir",
            notes="Learn TV power, volume, input, mute via IR. "
                  "Flipper can serve as universal remote backup.",
        ),
        FlipperProfile(
            device_id="blind-ryse-01",
            capabilities=[
                FlipperCapability.BLE_SCAN,
                FlipperCapability.IR_CAPTURE,
                FlipperCapability.IR_TRANSMIT,
            ],
            notes="BLE scan to verify Ryse SmartShade is broadcasting. "
                  "If Ryse has IR receiver, capture/replay open/close commands.",
        ),
        FlipperProfile(
            device_id="plug-tplink-01",
            capabilities=[FlipperCapability.BLE_SCAN],
            notes="BLE scan to detect if plug is broadcasting. "
                  "TP-Link Kasa plugs don't use sub-GHz or IR — LAN API only.",
        ),
        FlipperProfile(
            device_id="light-govee-01",
            capabilities=[
                FlipperCapability.BLE_SCAN,
                FlipperCapability.IR_CAPTURE,
                FlipperCapability.IR_TRANSMIT,
            ],
            notes="Govee devices often include IR remote. Capture with Flipper "
                  "for backup control. BLE scan to verify device presence.",
        ),
        FlipperProfile(
            device_id="cam-01",
            capabilities=[FlipperCapability.BLE_SCAN],
            notes="BLE scan to detect camera presence. "
                  "Test: does camera expose any unprotected BLE services?",
        ),
        FlipperProfile(
            device_id="motion-01",
            capabilities=[
                FlipperCapability.SUB_GHZ_CAPTURE,
                FlipperCapability.BLE_SCAN,
            ],
            notes="If motion detector uses 433MHz sub-GHz, capture signals "
                  "to verify encryption. BLE scan if WiFi/BLE model. "
                  "SECURITY AUDIT: verify signals are encrypted, not replayable.",
        ),
    ]
