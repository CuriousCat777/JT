"""Guardian One Fleet Manager — Coordinates all nodes in the Guardian One network.

The FleetManager runs on the primary controller (ROG) and is responsible for:
- Tracking node status across the fleet
- Routing service requests to the correct node
- Coordinating failover when nodes go offline
- Maintaining fleet-wide audit logs
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml


class NodeRole(Enum):
    PRIMARY_CONTROLLER = "primary_controller"
    WORKSTATION = "workstation"
    DAEMON = "daemon"


class NodeStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass
class NodeInfo:
    hostname: str
    display_name: str
    role: NodeRole
    os: str
    arch: str
    always_on: bool
    docker: bool
    services: list[str]
    status: NodeStatus = NodeStatus.UNKNOWN
    last_heartbeat: Optional[float] = None
    docker_containers: list[dict] = field(default_factory=list)


class FleetManager:
    """Central fleet coordinator running on the primary controller."""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.nodes: dict[str, NodeInfo] = {}
        self.controller_config: dict = {}
        self._load_config()

    def _load_config(self) -> None:
        fleet_path = self.config_dir / "fleet" / "nodes.yaml"
        controller_path = self.config_dir / "fleet" / "rog-controller.yaml"

        if fleet_path.exists():
            with open(fleet_path) as f:
                fleet_data = yaml.safe_load(f)
            self._parse_nodes(fleet_data)

        if controller_path.exists():
            with open(controller_path) as f:
                self.controller_config = yaml.safe_load(f)

    def _parse_nodes(self, fleet_data: dict) -> None:
        for hostname, node_data in fleet_data.get("nodes", {}).items():
            self.nodes[hostname] = NodeInfo(
                hostname=hostname,
                display_name=node_data["display_name"],
                role=NodeRole(node_data["role"]),
                os=node_data["os"],
                arch=node_data["arch"],
                always_on=node_data.get("always_on", False),
                docker=node_data.get("docker", False),
                services=node_data.get("services", []),
            )

    def get_node(self, hostname: str) -> Optional[NodeInfo]:
        return self.nodes.get(hostname)

    def get_primary_controller(self) -> Optional[NodeInfo]:
        for node in self.nodes.values():
            if node.role == NodeRole.PRIMARY_CONTROLLER:
                return node
        return None

    def get_nodes_by_role(self, role: NodeRole) -> list[NodeInfo]:
        return [n for n in self.nodes.values() if n.role == role]

    def get_online_nodes(self) -> list[NodeInfo]:
        return [n for n in self.nodes.values() if n.status == NodeStatus.ONLINE]

    def record_heartbeat(self, hostname: str) -> None:
        node = self.nodes.get(hostname)
        if node:
            node.last_heartbeat = time.time()
            node.status = NodeStatus.ONLINE

    def check_node_health(self, hostname: str) -> NodeStatus:
        node = self.nodes.get(hostname)
        if not node:
            return NodeStatus.UNKNOWN

        if node.last_heartbeat is None:
            return NodeStatus.UNKNOWN

        timeout = self.controller_config.get("controller", {}).get(
            "heartbeat", {}
        ).get("timeout_seconds", 90)

        elapsed = time.time() - node.last_heartbeat
        if elapsed > timeout:
            node.status = NodeStatus.OFFLINE
        return node.status

    def resolve_service_target(self, service_name: str) -> Optional[str]:
        """Determine which node should handle a given service request."""
        routing = self.controller_config.get("fleet_coordination", {}).get("routing", {})
        rules = routing.get("rules", [])

        for rule in rules:
            pattern = rule["service"]
            if pattern.endswith("*"):
                if service_name.startswith(pattern[:-1]):
                    return rule["target"]
            elif service_name == pattern:
                return rule["target"]

        return routing.get("default_target", "rog")

    def get_fleet_status(self) -> dict:
        """Generate a fleet status summary."""
        online = sum(1 for n in self.nodes.values() if n.status == NodeStatus.ONLINE)
        total = len(self.nodes)
        containers = sum(len(n.docker_containers) for n in self.nodes.values())
        services = sum(len(n.services) for n in self.nodes.values())

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fleet_name": "guardian-one",
            "nodes_online": online,
            "nodes_total": total,
            "docker_containers": containers,
            "assigned_services": services,
            "nodes": {
                hostname: {
                    "display_name": node.display_name,
                    "role": node.role.value,
                    "status": node.status.value,
                    "services": node.services,
                }
                for hostname, node in self.nodes.items()
            },
        }

    def log_fleet_event(self, event_type: str, data: dict, log_dir: Path) -> None:
        """Append a fleet event to the fleet audit log."""
        log_path = log_dir / "fleet" / "fleet.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            **data,
        }
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
