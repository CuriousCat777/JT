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
    """Jeremy's actual device inventory — Duluth, MN residence.

    Cataloged from Alexa app device list and hardware inspection.
    All devices start as UNKNOWN status until the DeviceAgent
    performs its first LAN scan and updates them.

    SELF-SERVICE POLICY:
      - Kasa plugs: local LAN API via python-kasa (block *.tplinkcloud.com)
      - Govee lights: local UDP port 4003 (enable LAN Control in Govee app)
      - Hue lights: local REST via Hue Bridge (block *.meethue.com)
      - Ryse blinds: local via SmartBridge SB-B101 REST API
      - Ring: CLOUD-ONLY (Amazon) — cannot be self-serviced, flagged as risk
      - Echo Dots: CLOUD-ONLY (Amazon) — flagged as exposure vector
      - LG TV: local WebOS SSAP (block *.lgtvcommon.com, *.lgappstv.com)
    """
    devices: list[DeviceRecord] = []

    # =================================================================
    # TP-Link Kasa Smart Plugs (9 plugs — all local via python-kasa)
    # =================================================================
    _kasa_base = dict(
        category=DeviceCategory.SMART_PLUG,
        manufacturer="TP-Link",
        model="Smart Plug Mini (KP125)",
        protocols=[DeviceProtocol.WIFI, DeviceProtocol.LAN_API],
        network_segment=NetworkSegment.IOT_VLAN,
        local_api_only=True,
        integration_name="tplink_kasa",
        tags=["smart_home", "energy", "local_only"],
    )
    kasa_plugs = [
        ("plug-tplink-01", "Smart Plug Mini 1", "living_room"),
        ("plug-kasa-mb-bedside", "MB Right Bedside Corner", "master_bedroom"),
        ("plug-kasa-console", "Console", "living_room"),
        ("plug-kasa-island", "Island", "kitchen"),
        ("plug-kasa-office-desk", "Office Desk Light", "office"),
        ("plug-kasa-closet-top", "Closet MB Top", "master_bedroom"),
        ("plug-kasa-closet-bottom", "Closet MB Bottom", "master_bedroom"),
        ("plug-kasa-mini-02", "Smart Plug Mini 2", "living_room"),
        ("plug-kasa-fairy-office", "Fairy-lights Office", "office"),
    ]
    for did, name, loc in kasa_plugs:
        devices.append(DeviceRecord(
            device_id=did, name=name, location=loc, **_kasa_base))

    # =================================================================
    # Govee Smart Lights (18 devices — local LAN UDP on port 4003)
    # =================================================================
    _govee_base = dict(
        category=DeviceCategory.SMART_LIGHT,
        manufacturer="Govee",
        protocols=[DeviceProtocol.WIFI, DeviceProtocol.BLE, DeviceProtocol.LAN_API],
        network_segment=NetworkSegment.IOT_VLAN,
        integration_name="govee",
        vault_credential_key="GOVEE_API_KEY",
        tags=["smart_home", "lighting", "rgb", "local_only"],
    )
    govee_lights = [
        # Living room
        ("light-govee-lr-main", "Living Room", "Govee RGBIC Strip", "living_room"),
        ("light-govee-lr-small", "Living Room Small", "Govee RGBIC Strip", "living_room"),
        ("light-govee-lr-shelf", "LR Shelf Backlight", "Govee LED Strip", "living_room"),
        ("light-govee-music-sync", "Music Sync", "Govee Music Sync Box", "living_room"),
        # TV backlight
        ("light-govee-tv-backlight", "65in NaNo LG TV Backlight",
         "Govee DreamView/Strip", "living_room"),
        ("light-govee-dreamview", "Scenic DreamView1", "Govee DreamView T1", "living_room"),
        # Special lamps
        ("light-govee-q5-max", "Q5 Max+", "Govee Q5 Max+ Floor Lamp", "living_room"),
        ("light-govee-mushroom", "Mushroom", "Govee Mushroom Lamp", "living_room"),
        ("light-govee-duoroller", "Q5 DuoRoller+", "Govee Q5 DuoRoller+", "living_room"),
        ("light-govee-relaxed", "Relaxed", "Govee Ambient Light", "living_room"),
        # Bedroom
        ("light-govee-01", "Bedroom", "Govee Bulb/Strip", "master_bedroom"),
        ("light-govee-mb-0100", "MB 0100", "Govee RGBIC Strip", "master_bedroom"),
        ("light-govee-mb-0004", "MB0004", "Govee Bulb", "master_bedroom"),
        # Bathrooms
        ("light-govee-guest-bath", "Guest Bathroom", "Govee Bulb", "guest_bathroom"),
        ("light-govee-guest-bath-2", "Guest Bath", "Govee Bulb", "guest_bathroom"),
        ("light-govee-master-bath", "MasterBathroom", "Govee Bulb", "master_bathroom"),
        # Other
        ("light-govee-studio", "Studio", "Govee Bulb/Strip", "office"),
        ("light-govee-balcony", "Big Balcony", "Govee Outdoor Strip", "balcony"),
        ("light-govee-kitchen", "Kitchen", "Govee Bulb", "kitchen"),
    ]
    for did, name, model, loc in govee_lights:
        devices.append(DeviceRecord(
            device_id=did, name=name, model=model, location=loc,
            **_govee_base))

    # =================================================================
    # Philips Hue (Bridge + 3 bulbs — local REST API via phue)
    # =================================================================
    devices.append(DeviceRecord(
        device_id="light-hue-bridge",
        name="Philips Hue Bridge",
        category=DeviceCategory.SMART_LIGHT,
        manufacturer="Philips",
        model="BSB002",
        protocols=[DeviceProtocol.ZIGBEE, DeviceProtocol.LAN_API],
        network_segment=NetworkSegment.IOT_VLAN,
        local_api_only=True,
        encryption_enabled=True,
        integration_name="philips_hue",
        vault_credential_key="HUE_BRIDGE_API_KEY",
        ip_address="192.168.1.147",
        location="master_bedroom",
        notes="Bridge ID ecb5fafffeafca80, MAC ec:b5:fa:af:ca:80, "
              "firmware 1975170000. DHCP on gateway 192.168.1.1. "
              "Controls all Hue bulbs via Zigbee mesh. Local REST API on port 443. "
              "Block *.meethue.com at DNS for local-only. API key in Vault.",
        tags=["smart_home", "lighting", "zigbee", "local_only"],
    ))
    _hue_base = dict(
        category=DeviceCategory.SMART_LIGHT,
        manufacturer="Philips",
        protocols=[DeviceProtocol.ZIGBEE],
        network_segment=NetworkSegment.IOT_VLAN,
        local_api_only=True,
        integration_name="philips_hue",
        tags=["smart_home", "lighting", "zigbee", "local_only"],
    )
    hue_bulbs = [
        ("light-hue-kitchen-1", "Kitchen Lamp 1", "Hue White Ambiance", "kitchen"),
        ("light-hue-spot-01", "Spotlight Bulb01", "Hue Spot GU10", "living_room"),
        ("light-hue-spot-02", "Spotlight Bulb02", "Hue Spot GU10", "living_room"),
    ]
    for did, name, model, loc in hue_bulbs:
        devices.append(DeviceRecord(
            device_id=did, name=name, model=model, location=loc, **_hue_base))

    # =================================================================
    # Ring Security System — CLOUD-ONLY (Amazon) — EXPOSURE RISK
    # =================================================================
    # Ring Alarm Base Station
    devices.append(DeviceRecord(
        device_id="ring-base-station",
        name="Ring Alarm Base Station",
        category=DeviceCategory.NETWORK_INFRA,
        manufacturer="Ring (Amazon)",
        model="Ring Alarm Base Station",
        protocols=[DeviceProtocol.WIFI, DeviceProtocol.ZWAVE, DeviceProtocol.CLOUD_API],
        network_segment=NetworkSegment.IOT_VLAN,
        local_api_only=False,
        ip_address="192.168.1.22",
        notes="SECURITY WARNING: Ring is 100% Amazon cloud-dependent. All video, "
              "sensor data, and control routes through Amazon servers. Cannot be "
              "self-serviced. MAC 30:68:93:ad:26:41. Recommend supplementing with "
              "local NVR (Frigate) + RTSP cameras for self-sovereign security.",
        tags=["security", "cloud_dependent", "exposure_risk"],
    ))
    # Ring Doorbells
    devices.append(DeviceRecord(
        device_id="cam-01",
        name="Duluth Jeremy 304 Ring",
        category=DeviceCategory.SECURITY_CAMERA,
        manufacturer="Ring (Amazon)",
        model="Ring Video Doorbell",
        protocols=[DeviceProtocol.WIFI, DeviceProtocol.CLOUD_API],
        network_segment=NetworkSegment.IOT_VLAN,
        local_api_only=False,
        location="front_door",
        notes="Ring doorbell at unit 304. Cloud-only video. "
              "Long-term: replace with Amcrest/Reolink RTSP doorbell + Frigate NVR.",
        tags=["security", "cloud_dependent", "exposure_risk"],
    ))
    devices.append(DeviceRecord(
        device_id="ring-doorbell-duluth-2",
        name="Duluth Jeremy Ring",
        category=DeviceCategory.SECURITY_CAMERA,
        manufacturer="Ring (Amazon)",
        model="Ring Video Doorbell",
        protocols=[DeviceProtocol.WIFI, DeviceProtocol.CLOUD_API],
        network_segment=NetworkSegment.IOT_VLAN,
        local_api_only=False,
        tags=["security", "cloud_dependent"],
    ))
    devices.append(DeviceRecord(
        device_id="ring-doorbell-manteca",
        name="Manteca Ring",
        category=DeviceCategory.SECURITY_CAMERA,
        manufacturer="Ring (Amazon)",
        model="Ring Video Doorbell",
        protocols=[DeviceProtocol.WIFI, DeviceProtocol.CLOUD_API],
        network_segment=NetworkSegment.IOT_VLAN,
        local_api_only=False,
        location="manteca",
        notes="Ring doorbell at parents' Manteca property. Cloud-dependent. "
              "PRIORITY MONITORING: Full event logging enabled — motion, doorbell, "
              "and dings logged to audit trail with alerts to Jeremy. "
              "Neighborhood safety concern (stabbings, car theft reported 2026-03).",
        tags=["security", "cloud_dependent", "manteca", "priority_monitor", "family"],
    ))
    # Ring Sensors
    ring_sensors = [
        ("ring-contact-34552", "Contact Sensor 34552", DeviceCategory.SENSOR,
         "Ring Contact Sensor"),
        ("ring-contact-33664", "Contact Sensor 33664 (Disabled)", DeviceCategory.SENSOR,
         "Ring Contact Sensor"),
        ("motion-01", "Motion Detector 34817", DeviceCategory.MOTION_DETECTOR,
         "Ring Motion Detector"),
        ("ring-sensor-front-door", "Front Door", DeviceCategory.SENSOR,
         "Ring Contact Sensor"),
        ("ring-sensor-br-guest", "BR Guest", DeviceCategory.SENSOR,
         "Ring Contact Sensor"),
        ("ring-sensor-hallway", "Hallway", DeviceCategory.MOTION_DETECTOR,
         "Ring Motion Detector"),
    ]
    for did, name, cat, model in ring_sensors:
        devices.append(DeviceRecord(
            device_id=did, name=name, category=cat,
            manufacturer="Ring (Amazon)", model=model,
            protocols=[DeviceProtocol.ZWAVE, DeviceProtocol.CLOUD_API],
            network_segment=NetworkSegment.IOT_VLAN,
            local_api_only=False,
            tags=["security", "cloud_dependent"],
        ))

    # =================================================================
    # LG NanoCell TV — local WebOS SSAP + block telemetry
    # =================================================================
    devices.append(DeviceRecord(
        device_id="tv-main",
        name="65in LG NanoCell TV",
        category=DeviceCategory.SMART_TV,
        manufacturer="LG",
        model="65 NanoCell",
        protocols=[DeviceProtocol.WIFI, DeviceProtocol.LAN_API, DeviceProtocol.IR],
        network_segment=NetworkSegment.IOT_VLAN,
        local_api_only=False,
        ip_address="192.168.1.64",
        location="living_room",
        notes="LG WebOS TV with local SSAP control. MUST block telemetry: "
              "*.lgtvcommon.com, *.lgappstv.com, *.lgsmartad.com, ngfts.lge.com. "
              "Disable ACR in Settings > General > Live Plus. Disable UPnP. "
              "Flipper IR backup for power/input/volume.",
        tags=["entertainment", "iot", "telemetry_risk"],
    ))

    # =================================================================
    # Ryse SmartBridge + SmartShade — local BLE/WiFi
    # =================================================================
    devices.append(DeviceRecord(
        device_id="ryse-smartbridge",
        name="Ryse SmartBridge",
        category=DeviceCategory.NETWORK_INFRA,
        manufacturer="Ryse",
        model="SB-B101",
        protocols=[DeviceProtocol.WIFI, DeviceProtocol.BLE, DeviceProtocol.LAN_API],
        network_segment=NetworkSegment.IOT_VLAN,
        local_api_only=True,
        ip_address="192.168.1.175",
        location="living_room",
        notes="Ryse SmartBridge SB-B101 (date code 2448 / week 48 2024). "
              "Bridges BLE SmartShade motors to WiFi LAN. Has local REST API. "
              "Block cloud to keep local-only.",
        tags=["smart_home", "blinds", "bridge", "local_only"],
    ))
    devices.append(DeviceRecord(
        device_id="blind-ryse-01",
        name="Ryse SmartShade Motor",
        category=DeviceCategory.SMART_BLIND,
        manufacturer="Ryse",
        model="SmartShade",
        protocols=[DeviceProtocol.BLE, DeviceProtocol.WIFI],
        network_segment=NetworkSegment.IOT_VLAN,
        local_api_only=True,
        integration_name="ryse_smartshade",
        vault_credential_key="RYSE_API_KEY",
        location="living_room",
        notes="Motorizes existing blinds. Controlled via SmartBridge SB-B101 LAN API. "
              "Supports open/close/position (0-100%). Chronos schedules sunrise/sunset.",
        tags=["smart_home", "blinds", "automation", "chronos", "local_only"],
    ))

    # =================================================================
    # Roborock Robot Vacuum — local + cloud API via python-roborock
    # =================================================================
    devices.append(DeviceRecord(
        device_id="vacuum-roborock",
        name="Roborock Vacuum",
        category=DeviceCategory.OTHER,
        manufacturer="Roborock",
        model="Roborock",
        protocols=[DeviceProtocol.WIFI, DeviceProtocol.LAN_API, DeviceProtocol.CLOUD_API],
        network_segment=NetworkSegment.IOT_VLAN,
        local_api_only=False,
        integration_name="roborock",
        vault_credential_key="ROBOROCK_TOKEN",
        location="living_room",
        notes="Robot vacuum with local control via python-roborock library (port 58867). "
              "Needs device auth token from Roborock app login flow. "
              "Local API preferred (faster, private). Cloud fallback available. "
              "Schedule: full clean MWF at 9:00 AM. "
              "Controls: start, stop, pause, dock, spot clean, set fan speed.",
        tags=["smart_home", "vacuum", "automation", "chronos"],
    ))

    # =================================================================
    # Amazon Echo Dots — CLOUD-ONLY — exposure vectors
    # =================================================================
    devices.append(DeviceRecord(
        device_id="echo-dot-01",
        name="Jeremy's Echo Dot",
        category=DeviceCategory.MEDIA_PLAYER,
        manufacturer="Amazon",
        model="Echo Dot",
        protocols=[DeviceProtocol.WIFI, DeviceProtocol.BLE, DeviceProtocol.CLOUD_API],
        network_segment=NetworkSegment.IOT_VLAN,
        local_api_only=False,
        ip_address="192.168.1.112",
        location="living_room",
        notes="EXPOSURE RISK: Always-listening device. All audio processed on Amazon "
              "cloud. Cannot be self-serviced. Consider: disable mic when not in use, "
              "review Alexa Privacy Settings, delete voice recordings regularly. "
              "Long-term: replace with local voice assistant (Home Assistant + Whisper).",
        tags=["voice_assistant", "cloud_dependent", "exposure_risk", "always_listening"],
    ))
    devices.append(DeviceRecord(
        device_id="echo-dot-02",
        name="Jeremy's 2nd Echo Dot",
        category=DeviceCategory.MEDIA_PLAYER,
        manufacturer="Amazon",
        model="Echo Dot",
        protocols=[DeviceProtocol.WIFI, DeviceProtocol.BLE, DeviceProtocol.CLOUD_API],
        network_segment=NetworkSegment.IOT_VLAN,
        local_api_only=False,
        ip_address="192.168.1.152",
        notes="Second Echo Dot. MAC 40:d9:5a:2d:a6:96. Same exposure risks as primary.",
        tags=["voice_assistant", "cloud_dependent", "exposure_risk", "always_listening"],
    ))

    # =================================================================
    # Network Infrastructure
    # =================================================================
    # Spectrum Cable Modem (DOCSIS)
    devices.append(DeviceRecord(
        device_id="modem-spectrum",
        name="ModemJT1 (Spectrum ES2251)",
        category=DeviceCategory.NETWORK_INFRA,
        manufacturer="Askey/Spectrum",
        model="ES2251",
        protocols=[DeviceProtocol.WIFI],
        network_segment=NetworkSegment.TRUSTED_LAN,
        default_password_changed=True,
        location="network_closet",
        notes="DOCSIS cable modem, Spectrum-provided. ISP: Charter/Spectrum. "
              "Internet Gig plan — speeds up to 1000 Mbps. "
              "Bridge mode recommended to let router handle NAT/firewall.",
        tags=["network", "infrastructure", "isp"],
    ))
    # Spectrum WiFi 6 Router (NOT WiFi 6E — corrected from prior session)
    devices.append(DeviceRecord(
        device_id="router-spectrum",
        name="Spectrum WiFi 6 Router (SAX2V1S)",
        category=DeviceCategory.NETWORK_INFRA,
        manufacturer="Askey/Spectrum",
        model="SAX2V1S",
        protocols=[DeviceProtocol.WIFI],
        network_segment=NetworkSegment.TRUSTED_LAN,
        default_password_changed=True,
        upnp_disabled=True,
        ip_address="192.168.1.1",
        location="network_closet",
        notes="Spectrum WiFi 6 gateway (Askey SAX2V1S). SSID: sharknavigator. "
              "Internet Gig (1000 Mbps). 27 devices connected as of 2026-03-19. "
              "CONFIRMED: UPnP OFF, Security Shield ON (0 threats last 7 days). "
              "PROBLEM: Uses Spectrum DNS — zero control over telemetry blocking. "
              "ACTION ITEMS: "
              "1) Deploy Pi-hole or NextDNS for DNS-level IoT blocking. "
              "2) Create IoT VLAN (Spectrum gateway may not support — may need "
              "   a dedicated router like Ubiquiti Dream Machine). "
              "3) Block telemetry domains: *.tplinkcloud.com, *.meethue.com, "
              "   *.lgtvcommon.com, *.lgappstv.com, *.lgsmartad.com, ngfts.lge.com. "
              "4) Disable WPS. 5) Set strong admin password. "
              "NOTE: Spectrum supports 2.4 GHz IoT device setup — most smart "
              "devices (Kasa, Govee, Ryse) need 2.4 GHz band.",
        tags=["network", "infrastructure", "critical"],
    ))
    # TP-Link network switch (seen in hardware photos)
    devices.append(DeviceRecord(
        device_id="switch-tplink",
        name="TP-Link Network Switch",
        category=DeviceCategory.NETWORK_INFRA,
        manufacturer="TP-Link",
        model="Unmanaged Switch",
        protocols=[DeviceProtocol.WIFI],
        network_segment=NetworkSegment.TRUSTED_LAN,
        location="network_closet",
        notes="TP-Link unmanaged switch for wired connections. "
              "Upgrade to managed switch if VLAN segmentation needed.",
        tags=["network", "infrastructure"],
    ))

    # =================================================================
    # Connected Vehicle
    # =================================================================
    devices.append(DeviceRecord(
        device_id="vehicle-01",
        name="Connected Vehicle",
        category=DeviceCategory.VEHICLE,
        manufacturer="Unknown",
        protocols=[DeviceProtocol.OBD2, DeviceProtocol.CLOUD_API],
        network_segment=NetworkSegment.NOT_NETWORKED,
        notes="OBD-II for local diagnostics. Manufacturer cloud for remote features. "
              "Disable remote access when unattended for extended periods.",
        tags=["vehicle", "telematics"],
    ))

    # =================================================================
    # Flipper Zero — security research tool
    # =================================================================
    devices.append(DeviceRecord(
        device_id="flipper-zero",
        name="Flipper Zero",
        category=DeviceCategory.SECURITY_TOOL,
        manufacturer="Flipper Devices",
        model="Flipper Zero",
        protocols=[
            DeviceProtocol.RF_SUB_GHZ, DeviceProtocol.NFC,
            DeviceProtocol.IR, DeviceProtocol.BLE, DeviceProtocol.USB,
        ],
        network_segment=NetworkSegment.NOT_NETWORKED,
        local_api_only=True,
        firmware=FirmwareInfo(auto_update=False),
        location="office",
        notes="Security research multi-tool. USB-connected to workstation. "
              "Use for IR learning (TV, blinds), BLE audits, sub-GHz analysis. "
              "LEGAL: Only test devices you own.",
        tags=["security", "pentest", "research", "local_only"],
    ))

    return devices


# ---------------------------------------------------------------------------
# Jeremy's room layout — Duluth, MN residence
# ---------------------------------------------------------------------------

def _jeremys_rooms() -> list[Room]:
    """Room definitions mapping physical spaces to device groups."""
    return [
        Room(
            room_id="living-room",
            name="Living Room",
            room_type=RoomType.LIVING_ROOM,
            device_ids=[
                "tv-main", "plug-tplink-01", "plug-kasa-console", "plug-kasa-mini-02",
                "blind-ryse-01", "ryse-smartbridge",
                "light-govee-lr-main", "light-govee-lr-small", "light-govee-lr-shelf",
                "light-govee-music-sync", "light-govee-tv-backlight",
                "light-govee-dreamview", "light-govee-q5-max", "light-govee-mushroom",
                "light-govee-duoroller", "light-govee-relaxed",
                "light-hue-spot-01", "light-hue-spot-02",
                "echo-dot-01",
            ],
            auto_lights=True,
            auto_blinds=True,
            notes="Main hub — Govee RGB ecosystem + Hue spots + Kasa plugs + Ryse blinds.",
        ),
        Room(
            room_id="bedroom-master",
            name="Master Bedroom",
            room_type=RoomType.BEDROOM,
            device_ids=[
                "plug-kasa-mb-bedside", "plug-kasa-closet-top", "plug-kasa-closet-bottom",
                "light-govee-01", "light-govee-mb-0100", "light-govee-mb-0004",
                "light-hue-bridge",
            ],
            auto_lights=True,
            auto_blinds=True,
            notes="Hue Bridge physically here — controls all Hue bulbs house-wide via Zigbee. "
                  "Govee strips for ambient. Kasa plugs for bedside + closet.",
        ),
        Room(
            room_id="kitchen",
            name="Kitchen",
            room_type=RoomType.KITCHEN,
            device_ids=[
                "plug-kasa-island", "light-hue-kitchen-1", "light-govee-kitchen",
            ],
            auto_lights=True,
            auto_blinds=False,
            notes="Hue for task lighting, Govee for ambient, Kasa plug on island.",
        ),
        Room(
            room_id="office",
            name="Office / Studio",
            room_type=RoomType.OFFICE,
            device_ids=[
                "plug-kasa-office-desk", "plug-kasa-fairy-office",
                "light-govee-studio", "flipper-zero",
            ],
            auto_lights=True,
            auto_blinds=False,
            notes="Workspace. Flipper Zero USB-connected. Desk light + fairy lights "
                  "via Kasa plugs. Govee Studio for ambient.",
        ),
        Room(
            room_id="guest-bathroom",
            name="Guest Bathroom",
            room_type=RoomType.BATHROOM,
            device_ids=[
                "light-govee-guest-bath", "light-govee-guest-bath-2",
            ],
            auto_lights=True,
            auto_blinds=False,
        ),
        Room(
            room_id="master-bathroom",
            name="Master Bathroom",
            room_type=RoomType.BATHROOM,
            device_ids=["light-govee-master-bath"],
            auto_lights=True,
            auto_blinds=False,
        ),
        Room(
            room_id="hallway",
            name="Hallway",
            room_type=RoomType.HALLWAY,
            device_ids=["ring-sensor-hallway"],
            auto_lights=False,
            auto_blinds=False,
            occupancy_sensor_id="ring-sensor-hallway",
        ),
        Room(
            room_id="balcony",
            name="Big Balcony",
            room_type=RoomType.EXTERIOR,
            device_ids=["light-govee-balcony"],
            auto_lights=True,
            auto_blinds=False,
            notes="Govee outdoor strip for ambient balcony lighting.",
        ),
        Room(
            room_id="guest-bedroom",
            name="Guest Bedroom",
            room_type=RoomType.BEDROOM,
            device_ids=["ring-sensor-br-guest"],
            auto_lights=False,
            auto_blinds=False,
        ),
        Room(
            room_id="front-entry",
            name="Front Entry",
            room_type=RoomType.ENTRY,
            device_ids=[
                "cam-01", "ring-sensor-front-door",
                "ring-contact-34552", "motion-01",
            ],
            auto_lights=False,
            auto_blinds=False,
            occupancy_sensor_id="motion-01",
            notes="Ring doorbell + contact/motion sensors. Entry security zone.",
        ),
        Room(
            room_id="network-closet",
            name="Network Closet",
            room_type=RoomType.OTHER,
            device_ids=["modem-spectrum", "router-spectrum", "switch-tplink", "ring-base-station"],
            auto_lights=False,
            auto_blinds=False,
            notes="Network infrastructure and Ring Alarm base station.",
        ),
    ]


# ---------------------------------------------------------------------------
# Flipper Zero interaction profiles
# ---------------------------------------------------------------------------

def _jeremys_flipper_profiles() -> list[FlipperProfile]:
    """Defines how the Flipper Zero can interact with each device.

    Profiles for authorized security testing and backup control.
    """
    return [
        FlipperProfile(
            device_id="tv-main",
            capabilities=[
                FlipperCapability.IR_CAPTURE, FlipperCapability.IR_TRANSMIT,
            ],
            ir_remote_file="infrared/lg_nanocell_65.ir",
            notes="LG NanoCell IR: power, volume, input, mute, smart home button. "
                  "Capture all codes as backup for when LAN API is unreachable.",
        ),
        FlipperProfile(
            device_id="blind-ryse-01",
            capabilities=[
                FlipperCapability.BLE_SCAN,
                FlipperCapability.IR_CAPTURE, FlipperCapability.IR_TRANSMIT,
            ],
            notes="BLE scan to verify SmartShade is broadcasting. "
                  "If Ryse has IR receiver, capture open/close codes as backup.",
        ),
        FlipperProfile(
            device_id="plug-tplink-01",
            capabilities=[FlipperCapability.BLE_SCAN],
            notes="BLE scan to verify plug presence. Kasa plugs are LAN-only control.",
        ),
        FlipperProfile(
            device_id="light-govee-01",
            capabilities=[
                FlipperCapability.BLE_SCAN,
                FlipperCapability.IR_CAPTURE, FlipperCapability.IR_TRANSMIT,
            ],
            notes="Govee devices often include IR remote. Capture with Flipper "
                  "for backup control. BLE scan to verify presence.",
        ),
        FlipperProfile(
            device_id="light-govee-lr-main",
            capabilities=[
                FlipperCapability.BLE_SCAN,
                FlipperCapability.IR_CAPTURE, FlipperCapability.IR_TRANSMIT,
            ],
            notes="Main living room Govee strip. BLE + IR backup.",
        ),
        FlipperProfile(
            device_id="cam-01",
            capabilities=[FlipperCapability.BLE_SCAN],
            notes="SECURITY AUDIT: Scan Ring doorbell BLE services for exposure. "
                  "Check for unprotected BLE characteristics.",
        ),
        FlipperProfile(
            device_id="motion-01",
            capabilities=[
                FlipperCapability.SUB_GHZ_CAPTURE, FlipperCapability.BLE_SCAN,
            ],
            notes="Ring motion detector — Z-Wave protocol. Capture Z-Wave signals "
                  "to verify encryption (S2 framework). AUDIT: ensure not replayable.",
        ),
        FlipperProfile(
            device_id="ring-base-station",
            capabilities=[
                FlipperCapability.BLE_SCAN, FlipperCapability.SUB_GHZ_CAPTURE,
            ],
            notes="SECURITY AUDIT: Scan Ring Alarm base station Z-Wave and BLE. "
                  "Verify Z-Wave S2 encryption. Check for unauthenticated endpoints.",
        ),
        FlipperProfile(
            device_id="echo-dot-01",
            capabilities=[FlipperCapability.BLE_SCAN],
            notes="BLE scan Echo Dot for exposed services. "
                  "Audit what BLE characteristics are advertised.",
        ),
        FlipperProfile(
            device_id="ryse-smartbridge",
            capabilities=[FlipperCapability.BLE_SCAN],
            notes="Scan SmartBridge SB-B101 BLE for open services and auth posture.",
        ),
    ]
