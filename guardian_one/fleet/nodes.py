"""Fleet Node Registry — Compute node definitions, specs, and roles.

Each node in Jeremy's fleet is a physical machine with defined:
- Hardware specs (CPU, RAM, GPU, storage)
- OS and network identity
- Role in the Guardian One system
- Display assignments
- Health status and uptime tracking

Fleet topology:
    A (ASUS ROG)    → Primary controller, heavy compute, manages B and C
    B (MacBook Pro) → Secondary workstation, side-by-side with A on ultrawide
    C (Mac Mini)    → Always-on daemon, runs homelink services 24/7
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class NodeRole(Enum):
    """What this machine does in the fleet."""
    PRIMARY = "primary"          # A — controller, heavy lifts
    WORKSTATION = "workstation"  # B — secondary dev/work machine
    DAEMON = "daemon"            # C — always-on services


class NodeOS(Enum):
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"


class NodeStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    STANDBY = "standby"         # Sleeping / lid closed
    BUSY = "busy"               # Running heavy workload
    UNREACHABLE = "unreachable" # Network issue
    UNKNOWN = "unknown"


class ConnectionMethod(Enum):
    """How A connects to this node for remote management."""
    SSH = "ssh"
    POWERSHELL_REMOTE = "powershell_remote"
    VNC = "vnc"
    RDP = "rdp"
    LOCAL = "local"             # This IS the primary machine


# ---------------------------------------------------------------------------
# Hardware specs
# ---------------------------------------------------------------------------

@dataclass
class CPUSpec:
    model: str
    cores: int
    threads: int
    base_clock_ghz: float
    boost_clock_ghz: float = 0.0
    architecture: str = "x86_64"


@dataclass
class GPUSpec:
    model: str
    vram_gb: int = 0
    cuda_cores: int = 0
    driver: str = ""


@dataclass
class StorageSpec:
    total_gb: int
    type: str = "SSD"       # SSD, NVMe, HDD
    model: str = ""
    encrypted: bool = True


@dataclass
class HardwareSpec:
    """Full hardware profile for a compute node."""
    cpu: CPUSpec
    ram_gb: int
    gpu: GPUSpec | None = None
    storage: list[StorageSpec] = field(default_factory=list)
    display_outputs: list[str] = field(default_factory=list)  # HDMI, DP, USB-C, TB4
    thunderbolt_ports: int = 0
    usb_c_ports: int = 0
    usb_a_ports: int = 0
    ethernet: bool = False
    wifi: str = "WiFi 6E"
    bluetooth: str = "5.3"


# ---------------------------------------------------------------------------
# Network identity
# ---------------------------------------------------------------------------

@dataclass
class NetworkIdentity:
    """How this node appears on the LAN."""
    hostname: str
    local_ip: str = ""          # Static LAN IP (set in router DHCP reservation)
    mac_address: str = ""
    ssh_port: int = 22
    ssh_user: str = ""
    ssh_key_path: str = ""      # Path to private key on A for passwordless auth
    tailscale_ip: str = ""      # Tailscale mesh IP for remote access
    vnc_port: int = 5900
    rdp_port: int = 3389


# ---------------------------------------------------------------------------
# Compute node
# ---------------------------------------------------------------------------

@dataclass
class ComputeNode:
    """A physical machine in Jeremy's fleet."""

    # Identity
    node_id: str                # "rog", "macbook-pro", "mac-mini"
    name: str                   # Human-readable name
    role: NodeRole
    os: NodeOS

    # Hardware
    hardware: HardwareSpec

    # Network
    network: NetworkIdentity

    # Connection
    connection_method: ConnectionMethod = ConnectionMethod.SSH
    is_stationary: bool = True  # False = laptop that moves

    # Status
    status: NodeStatus = NodeStatus.UNKNOWN
    last_seen: str = ""
    uptime_hours: float = 0.0
    current_load_pct: float = 0.0
    ram_used_pct: float = 0.0

    # Assigned services
    assigned_services: list[str] = field(default_factory=list)
    assigned_displays: list[str] = field(default_factory=list)

    # Docker
    docker_available: bool = False
    docker_containers: list[str] = field(default_factory=list)

    # Metadata
    location: str = "office"    # Physical location in the house
    notes: str = ""
    added_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# Fleet registry
# ---------------------------------------------------------------------------

class FleetRegistry:
    """Registry of all compute nodes in Jeremy's fleet.

    Provides lookup, health tracking, and role-based queries.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, ComputeNode] = {}

    def register(self, node: ComputeNode) -> None:
        self._nodes[node.node_id] = node

    def get(self, node_id: str) -> ComputeNode | None:
        return self._nodes.get(node_id)

    def remove(self, node_id: str) -> bool:
        return self._nodes.pop(node_id, None) is not None

    def all_nodes(self) -> list[ComputeNode]:
        return list(self._nodes.values())

    def by_role(self, role: NodeRole) -> list[ComputeNode]:
        return [n for n in self._nodes.values() if n.role == role]

    def by_status(self, status: NodeStatus) -> list[ComputeNode]:
        return [n for n in self._nodes.values() if n.status == status]

    def primary(self) -> ComputeNode | None:
        """Get the primary controller (A)."""
        nodes = self.by_role(NodeRole.PRIMARY)
        return nodes[0] if nodes else None

    def daemon(self) -> ComputeNode | None:
        """Get the always-on daemon node (C)."""
        nodes = self.by_role(NodeRole.DAEMON)
        return nodes[0] if nodes else None

    def workstations(self) -> list[ComputeNode]:
        """All workstation-class nodes (B, and potentially more)."""
        return self.by_role(NodeRole.WORKSTATION)

    def managed_nodes(self) -> list[ComputeNode]:
        """Nodes managed remotely by A (everything except A itself)."""
        return [n for n in self._nodes.values() if n.role != NodeRole.PRIMARY]

    def update_status(self, node_id: str, status: NodeStatus,
                      load_pct: float = 0.0, ram_pct: float = 0.0) -> bool:
        node = self._nodes.get(node_id)
        if node:
            node.status = status
            node.current_load_pct = load_pct
            node.ram_used_pct = ram_pct
            node.last_seen = datetime.now(timezone.utc).isoformat()
            return True
        return False

    def total_ram_gb(self) -> int:
        return sum(n.hardware.ram_gb for n in self._nodes.values())

    def total_storage_gb(self) -> int:
        return sum(
            sum(s.total_gb for s in n.hardware.storage)
            for n in self._nodes.values()
        )

    def fleet_summary(self) -> dict[str, Any]:
        nodes = self.all_nodes()
        online = [n for n in nodes if n.status == NodeStatus.ONLINE]
        return {
            "total_nodes": len(nodes),
            "online": len(online),
            "offline": len(nodes) - len(online),
            "total_ram_gb": self.total_ram_gb(),
            "total_storage_gb": self.total_storage_gb(),
            "nodes": [
                {
                    "id": n.node_id,
                    "name": n.name,
                    "role": n.role.value,
                    "os": n.os.value,
                    "status": n.status.value,
                    "ram_gb": n.hardware.ram_gb,
                    "cpu": n.hardware.cpu.model,
                    "services": n.assigned_services,
                    "displays": n.assigned_displays,
                }
                for n in nodes
            ],
        }

    def load_defaults(self) -> None:
        """Register Jeremy's three-node fleet."""
        for node in _jeremys_fleet():
            self.register(node)


# ---------------------------------------------------------------------------
# Jeremy's fleet inventory
# ---------------------------------------------------------------------------

def _jeremys_fleet() -> list[ComputeNode]:
    """Jeremy's actual compute fleet — 3 machines.

    A = ASUS ROG Flow Z13 (Windows 11, 64GB RAM)
        Primary controller. Heavy AI workloads, manages B and C.
        Side-by-side with B on the Samsung ultrawide.

    B = MacBook Pro 2024 (macOS, Apple Silicon)
        Secondary workstation. Dev work, creative tasks.
        Side-by-side with A on the Samsung ultrawide. Stationary.

    C = Mac Mini (macOS, Apple Silicon)
        Always-on daemon. Runs homelink services, n8n, monitoring.
        Connected to Samsung Frame 65" or headless. Stationary.
    """
    nodes: list[ComputeNode] = []

    # === A: ASUS ROG Flow Z13 — PRIMARY ===
    nodes.append(ComputeNode(
        node_id="rog",
        name="ASUS ROG Flow Z13",
        role=NodeRole.PRIMARY,
        os=NodeOS.WINDOWS,
        hardware=HardwareSpec(
            cpu=CPUSpec(
                model="Intel Core i9-13900H",
                cores=14,
                threads=20,
                base_clock_ghz=2.6,
                boost_clock_ghz=5.4,
            ),
            ram_gb=64,
            gpu=GPUSpec(
                model="NVIDIA GeForce RTX 4060 (Laptop)",
                vram_gb=8,
                cuda_cores=3072,
                driver="NVIDIA Game Ready",
            ),
            storage=[
                StorageSpec(total_gb=2000, type="NVMe", model="WD Black SN850X", encrypted=True),
            ],
            display_outputs=["USB-C/DP", "HDMI 2.1"],
            thunderbolt_ports=1,
            usb_c_ports=2,
            usb_a_ports=1,
            ethernet=False,
            wifi="WiFi 6E",
            bluetooth="5.3",
        ),
        network=NetworkIdentity(
            hostname="ROG-Z13",
            ssh_port=22,
            ssh_user="jeremy",
        ),
        connection_method=ConnectionMethod.LOCAL,
        is_stationary=False,
        assigned_services=[
            "guardian_one",         # Main Guardian One orchestrator
            "ollama",              # Local LLM inference
            "docker_desktop",      # Docker Desktop for Windows
            "claude_code",         # Claude Code CLI
            "visual_studio_code",  # VS Code
            "chatgpt_desktop",     # ChatGPT desktop app
            "codex",               # OpenAI Codex
        ],
        assigned_displays=["ultrawide-left", "alienware-25"],
        docker_available=True,
        location="office",
        notes="Primary controller. 64GB RAM for heavy AI + Docker workloads. Manages B and C via SSH.",
    ))

    # === B: MacBook Pro 2024 — WORKSTATION ===
    nodes.append(ComputeNode(
        node_id="macbook-pro",
        name="MacBook Pro 2024",
        role=NodeRole.WORKSTATION,
        os=NodeOS.MACOS,
        hardware=HardwareSpec(
            cpu=CPUSpec(
                model="Apple M3 Pro",
                cores=12,
                threads=12,
                base_clock_ghz=3.0,
                boost_clock_ghz=4.0,
                architecture="arm64",
            ),
            ram_gb=18,
            gpu=GPUSpec(
                model="Apple M3 Pro (integrated)",
                vram_gb=0,  # Unified memory
            ),
            storage=[
                StorageSpec(total_gb=512, type="NVMe", model="Apple SSD", encrypted=True),
            ],
            display_outputs=["HDMI 2.1", "TB4/DP", "TB4/DP", "TB4/DP"],
            thunderbolt_ports=3,
            usb_c_ports=3,
            usb_a_ports=0,
            ethernet=False,
            wifi="WiFi 6E",
            bluetooth="5.3",
        ),
        network=NetworkIdentity(
            hostname="Jeremys-MacBook-Pro",
            ssh_port=22,
            ssh_user="jeremy",
            ssh_key_path="~/.ssh/id_ed25519_macbook",
        ),
        connection_method=ConnectionMethod.SSH,
        is_stationary=True,
        assigned_services=[
            "claude_code",         # Claude Code CLI
            "visual_studio_code",  # VS Code
            "xcode",               # iOS/macOS dev
            "docker_desktop",      # Docker Desktop for Mac
            "notion_app",          # Notion desktop app
        ],
        assigned_displays=["ultrawide-right"],
        docker_available=True,
        location="office",
        notes="Secondary workstation. Stationary on desk, side-by-side with ROG on ultrawide.",
    ))

    # === C: Mac Mini — DAEMON (always-on) ===
    nodes.append(ComputeNode(
        node_id="mac-mini",
        name="Mac Mini",
        role=NodeRole.DAEMON,
        os=NodeOS.MACOS,
        hardware=HardwareSpec(
            cpu=CPUSpec(
                model="Apple M2",
                cores=8,
                threads=8,
                base_clock_ghz=3.5,
                boost_clock_ghz=3.5,
                architecture="arm64",
            ),
            ram_gb=16,
            gpu=GPUSpec(
                model="Apple M2 (integrated)",
                vram_gb=0,
            ),
            storage=[
                StorageSpec(total_gb=512, type="NVMe", model="Apple SSD", encrypted=True),
            ],
            display_outputs=["HDMI 2.0", "TB4/DP", "TB4/DP"],
            thunderbolt_ports=2,
            usb_c_ports=2,
            usb_a_ports=2,
            ethernet=True,
            wifi="WiFi 6",
            bluetooth="5.3",
        ),
        network=NetworkIdentity(
            hostname="Mac-Mini",
            ssh_port=22,
            ssh_user="jeremy",
            ssh_key_path="~/.ssh/id_ed25519_macmini",
        ),
        connection_method=ConnectionMethod.SSH,
        is_stationary=True,
        assigned_services=[
            "homelink_gateway",    # H.O.M.E. L.I.N.K. API gateway (24/7)
            "homelink_monitor",    # Health monitoring (24/7)
            "n8n",                 # n8n workflow automation (24/7)
            "notion_sync",         # Periodic Notion dashboard sync
            "zapier_webhooks",     # Zapier webhook listener
            "docker_daemon",       # Docker containers for services
            "backup_agent",        # Automated backup scheduler
        ],
        assigned_displays=["samsung-frame-65"],
        docker_available=True,
        location="office",
        notes="Always-on daemon. Runs homelink services 24/7. Ethernet recommended for reliability.",
    ))

    return nodes
