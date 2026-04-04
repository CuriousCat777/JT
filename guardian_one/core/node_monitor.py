"""Guardian One Node Monitor — Health checking and status reporting for fleet nodes.

Runs on the primary controller to periodically check the health of all fleet nodes,
their Docker containers, and assigned services. Reports status changes and triggers
failover when nodes become unreachable.
"""

import json
import logging
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .fleet_manager import FleetManager, NodeStatus

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    hostname: str
    reachable: bool
    docker_status: Optional[dict] = None
    services_up: list[str] = None
    services_down: list[str] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    timestamp: str = ""

    def __post_init__(self):
        if self.services_up is None:
            self.services_up = []
        if self.services_down is None:
            self.services_down = []
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class NodeMonitor:
    """Monitors fleet node health and triggers alerts on status changes."""

    def __init__(self, fleet_manager: FleetManager, log_dir: Path):
        self.fleet = fleet_manager
        self.log_dir = log_dir
        self._previous_status: dict[str, NodeStatus] = {}

    def check_node(self, hostname: str) -> HealthCheckResult:
        """Run a health check against a single node."""
        node = self.fleet.get_node(hostname)
        if not node:
            return HealthCheckResult(
                hostname=hostname,
                reachable=False,
                error=f"Unknown node: {hostname}",
            )

        start = time.monotonic()
        reachable = self._ping_node(hostname)
        latency = (time.monotonic() - start) * 1000

        result = HealthCheckResult(
            hostname=hostname,
            reachable=reachable,
            latency_ms=round(latency, 2),
        )

        if reachable:
            self.fleet.record_heartbeat(hostname)
            if node.docker:
                result.docker_status = self._check_docker(hostname)
            result.services_up, result.services_down = self._check_services(hostname)
        else:
            result.services_down = node.services[:]
            result.error = "Node unreachable"

        self._detect_status_change(hostname, result)
        self._log_check(result)
        return result

    def check_all_nodes(self) -> list[HealthCheckResult]:
        """Run health checks against all registered fleet nodes."""
        results = []
        for hostname in self.fleet.nodes:
            result = self.check_node(hostname)
            results.append(result)
        return results

    def get_fleet_summary(self) -> dict:
        """Generate a formatted fleet status summary."""
        status = self.fleet.get_fleet_status()
        total_containers = 0
        total_services = 0

        for hostname, node_info in status["nodes"].items():
            node = self.fleet.get_node(hostname)
            if node:
                total_containers += len(node.docker_containers)
                total_services += len(node.services)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nodes_online": status["nodes_online"],
            "nodes_total": status["nodes_total"],
            "docker_containers": total_containers,
            "assigned_services": total_services,
            "nodes": status["nodes"],
        }

    def _ping_node(self, hostname: str) -> bool:
        """Check if a node is reachable via network ping."""
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", hostname],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _check_docker(self, hostname: str) -> dict:
        """Query Docker container status on a node."""
        node = self.fleet.get_node(hostname)
        if not node or not node.docker:
            return {"available": False}

        return {
            "available": True,
            "containers": node.docker_containers,
            "container_count": len(node.docker_containers),
        }

    def _check_services(self, hostname: str) -> tuple[list[str], list[str]]:
        """Check which assigned services are running on a node."""
        node = self.fleet.get_node(hostname)
        if not node:
            return [], []

        # In a real deployment, this would query each service endpoint.
        # For now, treat all services on an online node as up.
        if node.status == NodeStatus.ONLINE:
            return node.services[:], []
        return [], node.services[:]

    def _detect_status_change(self, hostname: str, result: HealthCheckResult) -> None:
        """Detect and log node status transitions."""
        current = NodeStatus.ONLINE if result.reachable else NodeStatus.OFFLINE
        previous = self._previous_status.get(hostname, NodeStatus.UNKNOWN)

        if current != previous:
            self._previous_status[hostname] = current
            self.fleet.log_fleet_event(
                "node_status_change",
                {
                    "hostname": hostname,
                    "previous": previous.value,
                    "current": current.value,
                },
                self.log_dir,
            )
            logger.info(
                "Node %s status changed: %s -> %s",
                hostname,
                previous.value,
                current.value,
            )

    def _log_check(self, result: HealthCheckResult) -> None:
        """Write a health check result to the node log."""
        node_log_dir = self.log_dir / "fleet" / "nodes"
        node_log_dir.mkdir(parents=True, exist_ok=True)
        log_path = node_log_dir / f"{result.hostname}.jsonl"

        entry = {
            "timestamp": result.timestamp,
            "reachable": result.reachable,
            "latency_ms": result.latency_ms,
            "services_up": result.services_up,
            "services_down": result.services_down,
            "error": result.error,
        }
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
