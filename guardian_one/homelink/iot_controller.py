"""Sovereign IoT Local Control — H.O.M.E. L.I.N.K. IoT orchestration layer.

Manages the local-first IoT control stack:
    - Docker Compose lifecycle for core services (Home Assistant, Mosquitto,
      Node-RED, n8n, Zigbee2MQTT, Ollama, Tailscale)
    - Service health monitoring and status reporting
    - MQTT bus management (publish/subscribe)
    - Integration with existing H.O.M.E. L.I.N.K. infrastructure
      (Gateway, Vault, Audit, Monitor)

Design principles:
    - LAN-first, internet optional
    - Default-deny, zero-trust networking
    - No autonomous destructive actions (human-in-the-loop)
    - Offline-capable core functions
    - Fail-closed security posture
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from guardian_one.core.audit import AuditLog, Severity


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class ServiceState(Enum):
    """State of a Docker-managed IoT service."""
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    STARTING = "starting"
    UNKNOWN = "unknown"


class DeviceClassification(Enum):
    """Classification of discovered network devices."""
    KNOWN = "known"
    IOT = "iot"
    UNKNOWN = "unknown"
    QUARANTINED = "quarantined"


@dataclass
class IoTService:
    """A service in the IoT Docker Compose stack."""
    name: str
    image: str
    container_name: str
    state: ServiceState = ServiceState.UNKNOWN
    ports: list[str] = field(default_factory=list)
    url: str = ""
    last_check: str = ""
    error: str = ""
    required: bool = True  # Core vs optional


@dataclass
class DiscoveredDevice:
    """A device found on the LAN via network scan."""
    ip_address: str
    mac_address: str = ""
    vendor: str = ""
    hostname: str = ""
    device_class: DeviceClassification = DeviceClassification.UNKNOWN
    risk_score: int = 3  # 1 (safe) to 5 (critical)
    first_seen: str = ""
    last_seen: str = ""
    open_ports: list[int] = field(default_factory=list)
    notes: str = ""


@dataclass
class MQTTMessage:
    """An MQTT message on the local bus."""
    topic: str
    payload: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    retained: bool = False


@dataclass
class IoTStackHealth:
    """Aggregate health report for the IoT stack."""
    generated_at: str
    stack_dir: str
    compose_exists: bool
    docker_available: bool
    services: list[dict[str, Any]]
    running_count: int
    total_count: int
    overall_status: str  # healthy, degraded, offline
    anomalies: list[str]
    network_devices: int = 0


# ---------------------------------------------------------------------------
# Core services definition
# ---------------------------------------------------------------------------

CORE_SERVICES: list[IoTService] = [
    IoTService(
        name="homeassistant",
        image="ghcr.io/home-assistant/home-assistant:stable",
        container_name="homeassistant",
        ports=["8123"],
        url="http://localhost:8123",
        required=True,
    ),
    IoTService(
        name="mosquitto",
        image="eclipse-mosquitto",
        container_name="mosquitto",
        ports=["1883:1883"],
        url="tcp://localhost:1883",
        required=True,
    ),
    IoTService(
        name="nodered",
        image="nodered/node-red",
        container_name="nodered",
        ports=["1880:1880"],
        url="http://localhost:1880",
        required=True,
    ),
    IoTService(
        name="n8n",
        image="n8nio/n8n",
        container_name="n8n",
        ports=["5678:5678"],
        url="http://localhost:5678",
        required=True,
    ),
    IoTService(
        name="zigbee2mqtt",
        image="koenkk/zigbee2mqtt",
        container_name="zigbee2mqtt",
        ports=[],
        required=False,
    ),
    IoTService(
        name="ollama",
        image="ollama/ollama",
        container_name="ollama",
        ports=["11434:11434"],
        url="http://localhost:11434",
        required=False,
    ),
    IoTService(
        name="tailscale",
        image="tailscale/tailscale",
        container_name="tailscale",
        ports=[],
        required=False,
    ),
]


# ---------------------------------------------------------------------------
# VLAN / Firewall policy definitions
# ---------------------------------------------------------------------------

@dataclass
class VLANPolicy:
    """VLAN segmentation policy for the IoT network."""
    vlan_id: int
    name: str
    description: str
    allowed_outbound: list[str] = field(default_factory=list)
    blocked_outbound: list[str] = field(default_factory=list)


DEFAULT_VLANS: list[VLANPolicy] = [
    VLANPolicy(
        vlan_id=10,
        name="core",
        description="Core infrastructure (Guardian host, NAS, router)",
        allowed_outbound=["all"],
    ),
    VLANPolicy(
        vlan_id=20,
        name="iot",
        description="IoT devices (sensors, plugs, lights, cameras)",
        allowed_outbound=["mqtt_only"],
        blocked_outbound=["internet", "core_vlan_direct"],
    ),
    VLANPolicy(
        vlan_id=30,
        name="user",
        description="User devices (laptops, phones, tablets)",
        allowed_outbound=["all"],
    ),
]

FIREWALL_RULES: list[str] = [
    "deny_all_outbound_iot",
    "allow_iot_to_mqtt_only",
    "vpn_only_external_access",
]


# ---------------------------------------------------------------------------
# IoT Controller
# ---------------------------------------------------------------------------

class IoTController:
    """Orchestrates the sovereign IoT Docker Compose stack.

    Provides lifecycle management, health monitoring, and integration
    with the H.O.M.E. L.I.N.K. infrastructure layer.

    Usage:
        controller = IoTController(
            stack_dir=Path("~/iot-stack"),
            audit=audit_log,
        )
        controller.initialize()
        health = controller.stack_health()
        controller.start_stack()
    """

    def __init__(
        self,
        stack_dir: Path,
        audit: AuditLog,
        timezone: str = "America/Chicago",
    ) -> None:
        self._stack_dir = Path(stack_dir).expanduser()
        self._audit = audit
        self._timezone = timezone
        self._services: dict[str, IoTService] = {}
        self._discovered_devices: list[DiscoveredDevice] = []
        self._known_macs: dict[str, str] = {}  # MAC -> device name
        self._mqtt_log: list[MQTTMessage] = []
        self._mqtt_lock = threading.Lock()
        self._initialized = False

    @property
    def stack_dir(self) -> Path:
        return self._stack_dir

    @property
    def compose_path(self) -> Path:
        return self._stack_dir / "docker-compose.yml"

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Load core services into memory and verify prerequisites."""
        for svc in CORE_SERVICES:
            self._services[svc.name] = IoTService(
                name=svc.name,
                image=svc.image,
                container_name=svc.container_name,
                ports=list(svc.ports),
                url=svc.url,
                required=svc.required,
            )
        self._initialized = True
        self._audit.record(
            agent="homelink_iot",
            action="iot_controller_initialized",
            details={
                "stack_dir": str(self._stack_dir),
                "services_loaded": len(self._services),
            },
        )

    # ------------------------------------------------------------------
    # Docker Compose lifecycle
    # ------------------------------------------------------------------

    def _resolve_compose_cmd(self) -> list[str] | None:
        """Resolve the Docker Compose command (v1 or v2).

        Returns the command list (e.g. ``["docker-compose"]`` or
        ``["docker", "compose"]``) or ``None`` if unavailable.
        """
        if shutil.which("docker-compose") is not None:
            return ["docker-compose"]

        docker_path = shutil.which("docker")
        if docker_path is None:
            return None

        try:
            result = subprocess.run(
                [docker_path, "compose", "version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if result.returncode == 0:
                return [docker_path, "compose"]
        except OSError:
            pass
        return None

    def docker_available(self) -> bool:
        """Check if Docker and a Compose implementation are available."""
        return self._resolve_compose_cmd() is not None

    def generate_compose(self, zigbee_device: str = "/dev/ttyUSB0",
                         tailscale_authkey: str = "") -> str:
        """Generate the docker-compose.yml content for the IoT stack."""
        compose = {
            "version": "3.9",
            "services": {
                "homeassistant": {
                    "image": "ghcr.io/home-assistant/home-assistant:stable",
                    "container_name": "homeassistant",
                    "network_mode": "host",
                    "volumes": ["./homeassistant:/config"],
                    "restart": "unless-stopped",
                },
                "mosquitto": {
                    "image": "eclipse-mosquitto",
                    "container_name": "mosquitto",
                    "ports": ["1883:1883"],
                    "volumes": ["./mosquitto/config:/mosquitto/config"],
                    "restart": "unless-stopped",
                },
                "zigbee2mqtt": {
                    "image": "koenkk/zigbee2mqtt",
                    "container_name": "zigbee2mqtt",
                    "depends_on": ["mosquitto"],
                    "ports": ["8080:8080"],
                    "volumes": ["./zigbee2mqtt:/app/data"],
                    "devices": [f"{zigbee_device}:{zigbee_device}"],
                    "restart": "unless-stopped",
                },
                "nodered": {
                    "image": "nodered/node-red",
                    "container_name": "nodered",
                    "ports": ["1880:1880"],
                    "volumes": ["./nodered:/data"],
                    "restart": "unless-stopped",
                },
                "n8n": {
                    "image": "n8nio/n8n",
                    "container_name": "n8n",
                    "ports": ["5678:5678"],
                    "volumes": ["./n8n:/home/node/.n8n"],
                    "environment": [f"GENERIC_TIMEZONE={self._timezone}"],
                    "restart": "unless-stopped",
                },
                "ollama": {
                    "image": "ollama/ollama",
                    "container_name": "ollama",
                    "ports": ["11434:11434"],
                    "volumes": ["./ollama:/root/.ollama"],
                    "restart": "unless-stopped",
                },
                "tailscale": {
                    "image": "tailscale/tailscale",
                    "container_name": "tailscale",
                    "network_mode": "host",
                    "cap_add": ["NET_ADMIN"],
                    "environment": [
                        f"TS_AUTHKEY={tailscale_authkey or 'YOUR_KEY_HERE'}"
                    ],
                    "restart": "unless-stopped",
                },
            },
        }

        # Use json for structured output then convert to YAML-like format
        # We produce valid docker-compose YAML without requiring PyYAML
        return self._dict_to_yaml(compose)

    def scaffold_stack(self, zigbee_device: str = "/dev/ttyUSB0",
                       tailscale_authkey: str = "") -> dict[str, Any]:
        """Create the full directory structure and config files for the IoT stack.

        Returns a dict describing what was created.
        """
        created: list[str] = []

        # Create subdirectories
        subdirs = [
            "homeassistant", "mosquitto", "zigbee2mqtt",
            "nodered", "n8n", "ollama",
        ]
        for d in subdirs:
            path = self._stack_dir / d
            path.mkdir(parents=True, exist_ok=True)
            created.append(str(path))

        # Generate docker-compose.yml
        compose_content = self.generate_compose(
            zigbee_device=zigbee_device,
            tailscale_authkey=tailscale_authkey,
        )
        self.compose_path.write_text(compose_content)
        created.append(str(self.compose_path))

        # Mosquitto config (under config/ subdir to match compose mount)
        (self._stack_dir / "mosquitto" / "config").mkdir(parents=True, exist_ok=True)
        mosquitto_conf = self._stack_dir / "mosquitto" / "config" / "mosquitto.conf"
        mosquitto_conf.write_text(
            "# Secure-by-default Mosquitto configuration\n"
            "listener 1883\n"
            "allow_anonymous false\n"
            "password_file /mosquitto/config/passwords\n"
            "# To create the password file, run:\n"
            "#   docker exec -it mosquitto mosquitto_passwd -c /mosquitto/config/passwords <username>\n"
            "# Then restart the Mosquitto container to apply changes.\n"
        )
        created.append(str(mosquitto_conf))

        # Zigbee2MQTT config
        z2m_conf = self._stack_dir / "zigbee2mqtt" / "configuration.yaml"
        z2m_content = (
            "homeassistant: true\n"
            "mqtt:\n"
            "  base_topic: home\n"
            f"  server: mqtt://mosquitto:1883\n"
            "serial:\n"
            f"  port: {zigbee_device}\n"
            "frontend:\n"
            "  port: 8080\n"
        )
        z2m_conf.write_text(z2m_content)
        created.append(str(z2m_conf))

        self._audit.record(
            agent="homelink_iot",
            action="stack_scaffolded",
            details={
                "stack_dir": str(self._stack_dir),
                "files_created": len(created),
            },
        )

        return {
            "success": True,
            "stack_dir": str(self._stack_dir),
            "files_created": created,
            "compose_path": str(self.compose_path),
            "next_steps": [
                f"cd {self._stack_dir}",
                "docker-compose up -d",
                "Access Home Assistant at http://<host-ip>:8123",
                "Access Node-RED at http://<host-ip>:1880",
                "Access n8n at http://<host-ip>:5678",
                "Secure MQTT: disable allow_anonymous after testing",
            ],
        }

    def start_stack(self) -> dict[str, Any]:
        """Start the IoT Docker Compose stack."""
        if not self.compose_path.exists():
            return {"success": False, "error": "docker-compose.yml not found. Run scaffold first."}

        compose_cmd = self._resolve_compose_cmd()
        if compose_cmd is None:
            return {"success": False, "error": "Docker or docker-compose not found on PATH."}

        self._audit.record(
            agent="homelink_iot",
            action="stack_start_requested",
            severity=Severity.WARNING,
            details={"stack_dir": str(self._stack_dir)},
            requires_review=True,
        )

        try:
            result = subprocess.run(
                [*compose_cmd, "up", "-d"],
                cwd=str(self._stack_dir),
                capture_output=True,
                text=True,
                timeout=120,
            )
            success = result.returncode == 0
            self._audit.record(
                agent="homelink_iot",
                action="stack_started" if success else "stack_start_failed",
                severity=Severity.INFO if success else Severity.ERROR,
                details={
                    "returncode": result.returncode,
                    "stdout": result.stdout[:500],
                    "stderr": result.stderr[:500],
                },
            )
            return {
                "success": success,
                "output": result.stdout,
                "error": result.stderr if not success else "",
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Compose up timed out (120s)"}
        except FileNotFoundError:
            return {"success": False, "error": "Compose command not found on PATH"}

    def stop_stack(self) -> dict[str, Any]:
        """Stop the IoT Docker Compose stack."""
        if not self.compose_path.exists():
            return {"success": False, "error": "docker-compose.yml not found."}

        compose_cmd = self._resolve_compose_cmd()
        if compose_cmd is None:
            return {"success": False, "error": "Docker or docker-compose not found on PATH."}

        self._audit.record(
            agent="homelink_iot",
            action="stack_stop_requested",
            severity=Severity.WARNING,
            details={"stack_dir": str(self._stack_dir)},
            requires_review=True,
        )

        try:
            result = subprocess.run(
                [*compose_cmd, "down"],
                cwd=str(self._stack_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else "",
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Compose down timed out (60s)"}
        except FileNotFoundError:
            return {"success": False, "error": "Compose command not found on PATH"}

    def service_ps(self) -> list[dict[str, Any]]:
        """Get running status of each container via docker ps."""
        if not self.docker_available():
            return []

        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return []

            running = {}
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                name = parts[0] if len(parts) > 0 else ""
                status = parts[1] if len(parts) > 1 else ""
                ports = parts[2] if len(parts) > 2 else ""
                running[name] = {"status": status, "ports": ports}

            services = []
            for svc in self._services.values():
                container = running.get(svc.container_name)
                if container and "Up" in container["status"]:
                    state = ServiceState.RUNNING
                else:
                    state = ServiceState.STOPPED
                svc.state = state
                svc.last_check = datetime.now(timezone.utc).isoformat()
                services.append({
                    "name": svc.name,
                    "container": svc.container_name,
                    "state": state.value,
                    "image": svc.image,
                    "url": svc.url,
                    "required": svc.required,
                    "docker_status": container["status"] if container else "not running",
                })

            return services

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    # ------------------------------------------------------------------
    # Health monitoring
    # ------------------------------------------------------------------

    def stack_health(self) -> IoTStackHealth:
        """Comprehensive health check of the entire IoT stack."""
        services = self.service_ps()
        running = sum(1 for s in services if s["state"] == "running")
        total = len(self._services)

        required_running = all(
            s["state"] == "running"
            for s in services
            if s["required"]
        )

        if running == total:
            overall = "healthy"
        elif running > 0 and required_running:
            overall = "degraded"
        elif running > 0:
            overall = "degraded"
        else:
            overall = "offline"

        anomalies = []
        for s in services:
            if s["required"] and s["state"] != "running":
                anomalies.append(f"Required service '{s['name']}' is {s['state']}")

        return IoTStackHealth(
            generated_at=datetime.now(timezone.utc).isoformat(),
            stack_dir=str(self._stack_dir),
            compose_exists=self.compose_path.exists(),
            docker_available=self.docker_available(),
            services=services,
            running_count=running,
            total_count=total,
            overall_status=overall,
            anomalies=anomalies,
            network_devices=len(self._discovered_devices),
        )

    # ------------------------------------------------------------------
    # Network scanning
    # ------------------------------------------------------------------

    def scan_network(self, subnet: str = "192.168.1.0/24") -> list[DiscoveredDevice]:
        """Scan the LAN for devices using nmap.

        Args:
            subnet: CIDR subnet to scan (e.g. "192.168.1.0/24").

        Returns:
            List of discovered devices with classification.
        """
        self._audit.record(
            agent="homelink_iot",
            action="network_scan_started",
            details={"subnet": subnet},
        )

        if not shutil.which("nmap"):
            self._audit.record(
                agent="homelink_iot",
                action="network_scan_failed",
                severity=Severity.WARNING,
                details={"error": "nmap not found on PATH"},
            )
            return []

        try:
            result = subprocess.run(
                ["nmap", "-sn", "-oX", "-", subnet],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                return []

            devices = self._parse_nmap_xml(result.stdout)

            # Classify devices
            now = datetime.now(timezone.utc).isoformat()
            for dev in devices:
                if not dev.first_seen:
                    dev.first_seen = now
                dev.last_seen = now

                # Normalize MAC for consistent matching (known_macs stores uppercase)
                if dev.mac_address:
                    dev.mac_address = dev.mac_address.upper()

                if dev.mac_address and dev.mac_address in self._known_macs:
                    dev.device_class = DeviceClassification.KNOWN
                    dev.risk_score = 1
                    dev.notes = self._known_macs[dev.mac_address]
                else:
                    # Check if it was previously seen
                    prev = next(
                        (d for d in self._discovered_devices
                         if d.mac_address and dev.mac_address
                         and d.mac_address.upper() == dev.mac_address),
                        None,
                    )
                    if prev:
                        dev.device_class = prev.device_class
                        dev.first_seen = prev.first_seen
                        dev.risk_score = prev.risk_score
                    else:
                        dev.device_class = DeviceClassification.UNKNOWN
                        dev.risk_score = 4  # Unknown devices are high risk

            self._discovered_devices = devices
            self._audit.record(
                agent="homelink_iot",
                action="network_scan_complete",
                details={
                    "subnet": subnet,
                    "devices_found": len(devices),
                    "unknown": sum(
                        1 for d in devices
                        if d.device_class == DeviceClassification.UNKNOWN
                    ),
                },
            )
            return devices

        except subprocess.TimeoutExpired:
            self._audit.record(
                agent="homelink_iot",
                action="network_scan_timeout",
                severity=Severity.WARNING,
                details={"subnet": subnet},
            )
            return []
        except FileNotFoundError:
            return []

    def register_known_device(self, mac: str, name: str) -> None:
        """Register a MAC address as a known device."""
        self._known_macs[mac.upper()] = name
        # Update any existing discovered device
        for dev in self._discovered_devices:
            if dev.mac_address.upper() == mac.upper():
                dev.device_class = DeviceClassification.KNOWN
                dev.risk_score = 1
                dev.notes = name

    def quarantine_device(self, mac: str) -> dict[str, Any]:
        """Mark a device as quarantined (requires manual VLAN/firewall action).

        This produces a recommendation — Guardian One cannot reconfigure
        the router directly.
        """
        for dev in self._discovered_devices:
            if dev.mac_address.upper() == mac.upper():
                dev.device_class = DeviceClassification.QUARANTINED
                dev.risk_score = 5
                self._audit.record(
                    agent="homelink_iot",
                    action="device_quarantined",
                    severity=Severity.WARNING,
                    details={"mac": mac, "ip": dev.ip_address, "vendor": dev.vendor},
                    requires_review=True,
                )
                return {
                    "success": True,
                    "action_required": [
                        f"Move MAC {mac} to IoT VLAN (VLAN 20) on your router",
                        f"Block internet access for {dev.ip_address}",
                        "Allow MQTT traffic only (port 1883) from IoT VLAN",
                    ],
                }
        return {"success": False, "error": f"Device {mac} not found in scan results"}

    def unknown_devices(self) -> list[DiscoveredDevice]:
        """Return all devices classified as unknown."""
        return [
            d for d in self._discovered_devices
            if d.device_class == DeviceClassification.UNKNOWN
        ]

    # ------------------------------------------------------------------
    # MQTT helpers
    # ------------------------------------------------------------------

    def mqtt_publish(self, topic: str, payload: str) -> dict[str, Any]:
        """Publish a message to the local Mosquitto MQTT broker.

        Uses mosquitto_pub CLI (available when Mosquitto is running).
        """
        if not shutil.which("mosquitto_pub"):
            return {"success": False, "error": "mosquitto_pub not found on PATH"}

        try:
            result = subprocess.run(
                ["mosquitto_pub", "-h", "localhost", "-t", topic, "-m", payload],
                capture_output=True, text=True, timeout=10,
            )
            msg = MQTTMessage(topic=topic, payload=payload)
            with self._mqtt_lock:
                self._mqtt_log.append(msg)

            self._audit.record(
                agent="homelink_iot",
                action="mqtt_publish",
                details={"topic": topic, "payload_len": len(payload)},
            )
            return {
                "success": result.returncode == 0,
                "error": result.stderr if result.returncode != 0 else "",
            }
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # VLAN / Firewall policy
    # ------------------------------------------------------------------

    def vlan_policy(self) -> dict[str, Any]:
        """Return the current VLAN segmentation policy.

        This is a recommendation report — Guardian One cannot apply
        firewall rules directly.
        """
        return {
            "vlans": [
                {
                    "vlan_id": v.vlan_id,
                    "name": v.name,
                    "description": v.description,
                    "allowed_outbound": v.allowed_outbound,
                    "blocked_outbound": v.blocked_outbound,
                }
                for v in DEFAULT_VLANS
            ],
            "firewall_rules": FIREWALL_RULES,
            "recommendation": (
                "IoT devices (VLAN 20) should only reach the MQTT broker. "
                "Block all internet-bound traffic from IoT VLAN. "
                "User devices (VLAN 30) access via VPN only when remote."
            ),
        }

    # ------------------------------------------------------------------
    # Access points summary
    # ------------------------------------------------------------------

    def access_points(self) -> dict[str, str]:
        """Return URLs for all stack services."""
        return {
            "home_assistant": "http://<host-ip>:8123",
            "node_red": "http://<host-ip>:1880",
            "n8n": "http://<host-ip>:5678",
            "mqtt": "tcp://<host-ip>:1883",
            "ollama": "http://<host-ip>:11434",
        }

    # ------------------------------------------------------------------
    # Security hardening checklist
    # ------------------------------------------------------------------

    def security_checklist(self) -> list[dict[str, Any]]:
        """Return a security hardening checklist for the IoT stack."""
        return [
            {
                "item": "Disable anonymous MQTT",
                "priority": "critical",
                "status": "manual",
                "action": "Edit mosquitto.conf: set allow_anonymous false, add password_file",
            },
            {
                "item": "Enable TLS for MQTT",
                "priority": "high",
                "status": "manual",
                "action": "Generate certificates, configure mosquitto listener on 8883 with TLS",
            },
            {
                "item": "Enable HTTPS for Home Assistant",
                "priority": "high",
                "status": "manual",
                "action": "Configure SSL in configuration.yaml with Let's Encrypt or self-signed cert",
            },
            {
                "item": "Restrict ports via UFW",
                "priority": "high",
                "status": "manual",
                "action": "sudo ufw allow 22,8123,1880,5678/tcp && sudo ufw enable",
            },
            {
                "item": "Use Tailscale for remote access",
                "priority": "high",
                "status": "manual",
                "action": "Configure TS_AUTHKEY in docker-compose.yml, avoid port forwarding",
            },
            {
                "item": "Pin Docker image versions",
                "priority": "medium",
                "status": "manual",
                "action": "Replace :stable/:latest with specific version tags after testing",
            },
            {
                "item": "Persistent Zigbee USB device path",
                "priority": "medium",
                "status": "manual",
                "action": "Use /dev/serial/by-id/... instead of /dev/ttyUSB0",
            },
            {
                "item": "Block IoT internet access",
                "priority": "critical",
                "status": "manual",
                "action": "Configure VLAN 20 firewall rules to deny outbound internet",
            },
        ]

    # ------------------------------------------------------------------
    # Dashboard text
    # ------------------------------------------------------------------

    def dashboard_text(self) -> str:
        """Human-readable dashboard for the IoT stack."""
        health = self.stack_health()
        lines = [
            "",
            "  H.O.M.E. L.I.N.K. — SOVEREIGN IoT CONTROL",
            "  " + "=" * 50,
            f"  Generated: {health.generated_at}",
            f"  Stack dir: {health.stack_dir}",
            f"  Docker:    {'available' if health.docker_available else 'NOT FOUND'}",
            f"  Compose:   {'found' if health.compose_exists else 'not scaffolded'}",
            f"  Status:    {health.overall_status.upper()}",
            f"  Services:  {health.running_count}/{health.total_count} running",
            "",
            "  SERVICES:",
        ]

        for svc in health.services:
            state_icon = "[OK]" if svc["state"] == "running" else "[--]"
            req_tag = " (required)" if svc["required"] else ""
            lines.append(f"    {state_icon} {svc['name']:15s} {svc['docker_status']}{req_tag}")

        if health.anomalies:
            lines.append("")
            lines.append("  ANOMALIES:")
            for a in health.anomalies:
                lines.append(f"    [!!] {a}")

        # Network devices
        if self._discovered_devices:
            unknown = self.unknown_devices()
            lines.append("")
            lines.append(f"  NETWORK: {len(self._discovered_devices)} devices discovered")
            if unknown:
                lines.append(f"    [!!] {len(unknown)} UNKNOWN device(s) on LAN")
                for d in unknown[:5]:
                    lines.append(
                        f"      {d.ip_address:15s} {d.mac_address:17s} "
                        f"{d.vendor or 'unknown vendor'}"
                    )

        # Access points
        lines.append("")
        lines.append("  ACCESS POINTS:")
        for name, url in self.access_points().items():
            lines.append(f"    {name:20s} {url}")

        lines.append("")
        lines.append("  " + "=" * 50)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Maintenance schedule
    # ------------------------------------------------------------------

    def maintenance_schedule(self) -> dict[str, Any]:
        """Return the automated and manual maintenance schedules."""
        return {
            "automated": {
                "log_aggregation": "continuous",
                "daily_summary": "daily at 07:00",
                "update_notifications": "daily check",
                "config_backups": "daily at 02:00",
            },
            "manual_approval_required": [
                "firmware_updates",
                "firewall_changes",
                "device_quarantine",
            ],
            "schedule": {
                "daily": "health_summary",
                "weekly": "integrity_report",
                "monthly": "update_review",
            },
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_nmap_xml(self, xml_output: str) -> list[DiscoveredDevice]:
        """Parse nmap -oX output into a list of DiscoveredDevice objects.

        Uses xml.etree.ElementTree to safely parse the XML and only extracts
        host/address/vendor/hostname data from ping scan (-sn) output.
        Parsing errors result in an empty list rather than raising.
        """
        import xml.etree.ElementTree as ET

        devices: list[DiscoveredDevice] = []
        try:
            root = ET.fromstring(xml_output)
        except ET.ParseError:
            return devices

        for host in root.findall(".//host"):
            status_el = host.find("status")
            if status_el is None or status_el.get("state") != "up":
                continue

            ip = ""
            mac = ""
            vendor = ""
            hostname = ""

            for addr in host.findall("address"):
                if addr.get("addrtype") == "ipv4":
                    ip = addr.get("addr", "")
                elif addr.get("addrtype") == "mac":
                    mac = addr.get("addr", "")
                    vendor = addr.get("vendor", "")

            hostnames = host.find("hostnames")
            if hostnames is not None:
                hn = hostnames.find("hostname")
                if hn is not None:
                    hostname = hn.get("name", "")

            if ip:
                devices.append(DiscoveredDevice(
                    ip_address=ip,
                    mac_address=mac,
                    vendor=vendor,
                    hostname=hostname,
                ))

        return devices

    @staticmethod
    def _dict_to_yaml(data: dict, indent: int = 0) -> str:
        """Minimal dict-to-YAML serializer for docker-compose files.

        Handles the specific structure needed for docker-compose.yml
        without requiring the PyYAML dependency.
        """
        lines: list[str] = []
        prefix = "  " * indent

        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                lines.append(IoTController._dict_to_yaml(value, indent + 1))
            elif isinstance(value, list):
                lines.append(f"{prefix}{key}:")
                for item in value:
                    if isinstance(item, dict):
                        # Inline dict in list (not used in our compose)
                        lines.append(f"{prefix}  - {json.dumps(item)}")
                    else:
                        lines.append(f"{prefix}  - \"{item}\"")
            elif isinstance(value, bool):
                lines.append(f"{prefix}{key}: {'true' if value else 'false'}")
            elif isinstance(value, (int, float)):
                lines.append(f"{prefix}{key}: {value}")
            else:
                lines.append(f"{prefix}{key}: \"{value}\"")

        return "\n".join(lines)
