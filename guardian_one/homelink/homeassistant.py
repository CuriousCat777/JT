"""H.O.M.E. L.I.N.K. Home Assistant Integration — Local dashboard & device control.

Provides the UI layer for the sovereign IoT stack:
- REST API client for Home Assistant (local network only)
- Device state synchronization (HA <-> Guardian One)
- Dashboard module definitions (room control, device groups, security panel)
- Automation forwarding (Guardian One -> HA automations)
- Service call proxy (turn on/off, set brightness, etc.)

Requirements:
- Home Assistant running on LAN (e.g., http://homeassistant.local:8123)
- Long-lived access token stored in Vault
- No cloud dependency (local API only)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from guardian_one.core.audit import AuditLog, Severity


class HAEntityDomain(Enum):
    """Home Assistant entity domains."""
    LIGHT = "light"
    SWITCH = "switch"
    COVER = "cover"           # Blinds/shades
    CAMERA = "camera"
    BINARY_SENSOR = "binary_sensor"
    SENSOR = "sensor"
    MEDIA_PLAYER = "media_player"
    AUTOMATION = "automation"
    CLIMATE = "climate"
    LOCK = "lock"


@dataclass
class HAEntity:
    """A Home Assistant entity."""
    entity_id: str                  # e.g., "light.bedroom_lamp"
    domain: HAEntityDomain
    friendly_name: str = ""
    state: str = "unknown"          # "on", "off", "unavailable", etc.
    attributes: dict[str, Any] = field(default_factory=dict)
    last_changed: str = ""
    last_updated: str = ""
    guardian_device_id: str = ""    # Maps to DeviceRegistry device_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "domain": self.domain.value,
            "friendly_name": self.friendly_name,
            "state": self.state,
            "attributes": self.attributes,
            "last_changed": self.last_changed,
            "last_updated": self.last_updated,
            "guardian_device_id": self.guardian_device_id,
        }


@dataclass
class HAServiceCall:
    """A Home Assistant service call."""
    domain: str                     # e.g., "light"
    service: str                    # e.g., "turn_on"
    entity_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "service": self.service,
            "entity_id": self.entity_id,
            "data": self.data,
            "timestamp": self.timestamp,
        }


@dataclass
class DashboardModule:
    """A UI module for the Home Assistant dashboard."""
    module_id: str
    title: str
    module_type: str              # "room_control", "device_groups", "security_overview"
    entities: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class HomeAssistantConfig:
    """Configuration for Home Assistant connection."""
    base_url: str = "http://homeassistant.local:8123"
    access_token: str = ""        # Long-lived access token
    verify_ssl: bool = False      # Local network — self-signed certs
    timeout: int = 10
    webhook_id: str = ""          # For automation triggers


class HomeAssistantClient:
    """Local Home Assistant API client.

    Communicates with HA via its REST API over the LAN.
    No cloud relay — all traffic stays local.
    """

    def __init__(
        self,
        config: HomeAssistantConfig | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self._config = config or HomeAssistantConfig()
        self._audit = audit
        self._connected = False
        self._entities: dict[str, HAEntity] = {}
        self._service_history: list[HAServiceCall] = []
        self._dashboard_modules: list[DashboardModule] = []
        self._last_sync: str = ""

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def base_url(self) -> str:
        return self._config.base_url

    def connect(self) -> bool:
        """Test connection to Home Assistant API.

        Calls GET /api/ to verify connectivity and authentication.
        """
        if not self._config.access_token:
            self._log("ha_no_token", Severity.WARNING, {
                "error": "No access token configured",
            })
            return False

        try:
            import urllib.request
            import ssl

            url = f"{self._config.base_url}/api/"
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {self._config.access_token}",
                "Content-Type": "application/json",
            })

            ctx = ssl.create_default_context()
            if not self._config.verify_ssl:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

            with urllib.request.urlopen(req, timeout=self._config.timeout,
                                        context=ctx) as resp:
                data = json.loads(resp.read())
                self._connected = True
                self._log("ha_connected", Severity.INFO, {
                    "message": data.get("message", ""),
                })
                return True

        except Exception as exc:
            self._log("ha_connect_error", Severity.WARNING, {
                "error": str(exc),
            })
            return False

    def disconnect(self) -> None:
        self._connected = False

    # ------------------------------------------------------------------
    # Entity management
    # ------------------------------------------------------------------

    def sync_entities(self) -> list[HAEntity]:
        """Fetch all entities from Home Assistant."""
        entities = self._api_get("/api/states")
        if entities is None:
            return list(self._entities.values())

        self._entities.clear()
        for state_obj in entities:
            entity_id = state_obj.get("entity_id", "")
            domain_str = entity_id.split(".")[0] if "." in entity_id else ""

            try:
                domain = HAEntityDomain(domain_str)
            except ValueError:
                continue

            entity = HAEntity(
                entity_id=entity_id,
                domain=domain,
                friendly_name=state_obj.get("attributes", {}).get(
                    "friendly_name", entity_id,
                ),
                state=state_obj.get("state", "unknown"),
                attributes=state_obj.get("attributes", {}),
                last_changed=state_obj.get("last_changed", ""),
                last_updated=state_obj.get("last_updated", ""),
            )
            self._entities[entity_id] = entity

        self._last_sync = datetime.now(timezone.utc).isoformat()
        self._log("ha_sync_complete", Severity.INFO, {
            "entity_count": len(self._entities),
        })
        return list(self._entities.values())

    def get_entity(self, entity_id: str) -> HAEntity | None:
        """Get a cached entity by ID."""
        return self._entities.get(entity_id)

    def entities_by_domain(self, domain: HAEntityDomain) -> list[HAEntity]:
        """Get all entities of a specific domain."""
        return [
            e for e in self._entities.values() if e.domain == domain
        ]

    # ------------------------------------------------------------------
    # Service calls (device control)
    # ------------------------------------------------------------------

    def call_service(self, call: HAServiceCall) -> dict[str, Any]:
        """Execute a service call on Home Assistant.

        Examples:
        - Turn on light: domain="light", service="turn_on", entity_id="light.bedroom"
        - Set brightness: domain="light", service="turn_on", data={"brightness": 128}
        - Open cover: domain="cover", service="open_cover", entity_id="cover.blinds"
        """
        payload: dict[str, Any] = {}
        if call.entity_id:
            payload["entity_id"] = call.entity_id
        if call.data:
            payload.update(call.data)

        result = self._api_post(
            f"/api/services/{call.domain}/{call.service}",
            payload,
        )

        self._service_history.append(call)
        self._log(f"ha_service_call:{call.domain}.{call.service}", Severity.INFO, {
            "entity_id": call.entity_id,
            "data": call.data,
            "success": result is not None,
        })

        return result or {"error": "Service call failed"}

    def turn_on(self, entity_id: str, **kwargs: Any) -> dict[str, Any]:
        """Convenience: turn on an entity."""
        domain = entity_id.split(".")[0]
        return self.call_service(HAServiceCall(
            domain=domain, service="turn_on",
            entity_id=entity_id, data=kwargs,
        ))

    def turn_off(self, entity_id: str) -> dict[str, Any]:
        """Convenience: turn off an entity."""
        domain = entity_id.split(".")[0]
        return self.call_service(HAServiceCall(
            domain=domain, service="turn_off",
            entity_id=entity_id,
        ))

    def set_brightness(self, entity_id: str, brightness: int) -> dict[str, Any]:
        """Set light brightness (0-255)."""
        return self.call_service(HAServiceCall(
            domain="light", service="turn_on",
            entity_id=entity_id, data={"brightness": brightness},
        ))

    def open_cover(self, entity_id: str) -> dict[str, Any]:
        """Open a cover (blind/shade)."""
        return self.call_service(HAServiceCall(
            domain="cover", service="open_cover",
            entity_id=entity_id,
        ))

    def close_cover(self, entity_id: str) -> dict[str, Any]:
        """Close a cover (blind/shade)."""
        return self.call_service(HAServiceCall(
            domain="cover", service="close_cover",
            entity_id=entity_id,
        ))

    # ------------------------------------------------------------------
    # Dashboard modules
    # ------------------------------------------------------------------

    def setup_default_modules(self) -> list[DashboardModule]:
        """Create the default dashboard module definitions."""
        self._dashboard_modules = [
            DashboardModule(
                module_id="room_control",
                title="Room Control",
                module_type="room_control",
                entities=[],
                config={
                    "rooms": ["bedroom", "living_room", "kitchen", "office"],
                    "show_temperature": True,
                    "show_occupancy": True,
                },
            ),
            DashboardModule(
                module_id="device_groups",
                title="Device Groups",
                module_type="device_groups",
                entities=[],
                config={
                    "groups": [
                        {"name": "All Lights", "domain": "light"},
                        {"name": "Smart Plugs", "domain": "switch"},
                        {"name": "Cameras", "domain": "camera"},
                        {"name": "Blinds", "domain": "cover"},
                    ],
                },
            ),
            DashboardModule(
                module_id="security_overview",
                title="Security Overview",
                module_type="security_overview",
                entities=[],
                config={
                    "show_cameras": True,
                    "show_motion": True,
                    "show_network_status": True,
                    "show_anomalies": True,
                    "alert_threshold": "warning",
                },
            ),
        ]
        return self._dashboard_modules

    def dashboard_modules(self) -> list[DashboardModule]:
        """Get configured dashboard modules."""
        if not self._dashboard_modules:
            self.setup_default_modules()
        return self._dashboard_modules

    # ------------------------------------------------------------------
    # Entity-to-device mapping
    # ------------------------------------------------------------------

    def map_entity_to_device(
        self, entity_id: str, guardian_device_id: str,
    ) -> None:
        """Link a HA entity to a Guardian One device registry entry."""
        entity = self._entities.get(entity_id)
        if entity:
            entity.guardian_device_id = guardian_device_id

    def mapped_entities(self) -> dict[str, str]:
        """Return entity_id -> guardian_device_id mappings."""
        return {
            eid: e.guardian_device_id
            for eid, e in self._entities.items()
            if e.guardian_device_id
        }

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Connection and entity status."""
        domain_counts: dict[str, int] = {}
        for e in self._entities.values():
            d = e.domain.value
            domain_counts[d] = domain_counts.get(d, 0) + 1

        return {
            "connected": self._connected,
            "base_url": self._config.base_url,
            "entity_count": len(self._entities),
            "domains": domain_counts,
            "last_sync": self._last_sync,
            "service_calls": len(self._service_history),
            "dashboard_modules": len(self._dashboard_modules),
            "mapped_devices": len(self.mapped_entities()),
        }

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _api_get(self, path: str) -> Any | None:
        """Make a GET request to the HA API."""
        try:
            import urllib.request
            import ssl

            url = f"{self._config.base_url}{path}"
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {self._config.access_token}",
                "Content-Type": "application/json",
            })

            ctx = ssl.create_default_context()
            if not self._config.verify_ssl:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

            with urllib.request.urlopen(req, timeout=self._config.timeout,
                                        context=ctx) as resp:
                return json.loads(resp.read())
        except Exception:
            return None

    def _api_post(self, path: str, data: dict[str, Any]) -> Any | None:
        """Make a POST request to the HA API."""
        try:
            import urllib.request
            import ssl

            url = f"{self._config.base_url}{path}"
            body = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(url, data=body, method="POST", headers={
                "Authorization": f"Bearer {self._config.access_token}",
                "Content-Type": "application/json",
            })

            ctx = ssl.create_default_context()
            if not self._config.verify_ssl:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

            with urllib.request.urlopen(req, timeout=self._config.timeout,
                                        context=ctx) as resp:
                return json.loads(resp.read())
        except Exception:
            return None

    def _log(self, action: str, severity: Severity, details: dict[str, Any]) -> None:
        if self._audit:
            self._audit.record(
                agent="home_assistant",
                action=action,
                severity=severity,
                details=details,
            )
