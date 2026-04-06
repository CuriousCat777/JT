"""Fleet Orchestrator — Remote management of compute nodes from Primary (A).

Responsibilities:
- SSH into B (MacBook Pro) and C (Mac Mini) for remote commands
- Dispatch tasks to the optimal node based on resource availability
- Health-check all nodes on a schedule
- Start/stop services on remote nodes
- Coordinate workloads: heavy lifts → A, homelink daemons → C, dev → B
- Provide a unified status view of the entire fleet

Security:
- SSH key-based auth only (no passwords)
- All commands logged via AuditLog
- Sensitive output is never cached
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.fleet.nodes import (
    ComputeNode,
    ConnectionMethod,
    FleetRegistry,
    NodeRole,
    NodeStatus,
)


class TaskPriority(Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class RemoteCommand:
    """A command to execute on a remote node."""
    command: str
    node_id: str
    timeout_seconds: int = 30
    capture_output: bool = True


@dataclass
class CommandResult:
    """Result of a remote command execution."""
    node_id: str
    command: str
    return_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    executed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def success(self) -> bool:
        return self.return_code == 0


@dataclass
class FleetTask:
    """A task to be dispatched to the optimal node."""
    task_id: str
    description: str
    command: str
    priority: TaskPriority = TaskPriority.NORMAL
    preferred_node: str = ""      # Empty = auto-select
    requires_gpu: bool = False
    min_ram_gb: int = 0
    status: TaskStatus = TaskStatus.PENDING
    assigned_node: str = ""
    result: CommandResult | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class NodeHealth:
    """Health check result for a node."""
    node_id: str
    reachable: bool
    cpu_load_pct: float = 0.0
    ram_used_pct: float = 0.0
    ram_available_gb: float = 0.0
    disk_used_pct: float = 0.0
    uptime_hours: float = 0.0
    docker_running: bool = False
    services_up: list[str] = field(default_factory=list)
    services_down: list[str] = field(default_factory=list)
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class FleetOrchestrator:
    """Controls Jeremy's compute fleet from the primary node (A = ROG).

    Usage:
        orch = FleetOrchestrator(registry, audit)
        orch.health_check_all()          # Ping all nodes
        orch.dispatch(task)              # Route task to best node
        orch.ssh_exec("mac-mini", "docker ps")  # Direct SSH command
        orch.start_service("mac-mini", "n8n")   # Start a service
        orch.fleet_dashboard()           # Full status view
    """

    def __init__(
        self,
        registry: FleetRegistry,
        audit: AuditLog,
    ) -> None:
        self.registry = registry
        self.audit = audit
        self._tasks: list[FleetTask] = []
        self._health_cache: dict[str, NodeHealth] = {}

    # ------------------------------------------------------------------
    # SSH execution
    # ------------------------------------------------------------------

    def _build_ssh_command(self, node: ComputeNode, command: str) -> list[str]:
        """Build the SSH command for a remote node."""
        net = node.network
        ssh_cmd = ["ssh", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=yes"]

        if net.ssh_key_path:
            ssh_cmd.extend(["-i", net.ssh_key_path])

        if net.ssh_port != 22:
            ssh_cmd.extend(["-p", str(net.ssh_port)])

        target = f"{net.ssh_user}@{net.tailscale_ip or net.local_ip or net.hostname}"
        ssh_cmd.append(target)
        ssh_cmd.append(command)
        return ssh_cmd

    def ssh_exec(self, node_id: str, command: str,
                 timeout: int = 30) -> CommandResult:
        """Execute a command on a remote node via SSH.

        For the primary node (A), runs locally instead.
        """
        node = self.registry.get(node_id)
        if not node:
            return CommandResult(
                node_id=node_id, command=command, return_code=-1,
                stderr=f"Unknown node: {node_id}",
            )

        start = datetime.now(timezone.utc)

        try:
            if node.connection_method == ConnectionMethod.LOCAL:
                # Primary node — run locally
                proc = subprocess.run(
                    command, shell=True, capture_output=True,
                    text=True, timeout=timeout,
                )
            else:
                # Remote node — SSH
                ssh_cmd = self._build_ssh_command(node, command)
                proc = subprocess.run(
                    ssh_cmd, capture_output=True, text=True, timeout=timeout,
                )

            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            result = CommandResult(
                node_id=node_id,
                command=command,
                return_code=proc.returncode,
                stdout=proc.stdout.strip(),
                stderr=proc.stderr.strip(),
                duration_ms=elapsed,
            )
        except subprocess.TimeoutExpired:
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            result = CommandResult(
                node_id=node_id, command=command, return_code=-1,
                stderr=f"Timeout after {timeout}s", duration_ms=elapsed,
            )
        except FileNotFoundError:
            result = CommandResult(
                node_id=node_id, command=command, return_code=-1,
                stderr="SSH binary not found",
            )

        self.audit.record(
            agent="fleet_orchestrator",
            action="ssh_exec",
            severity=Severity.INFO if result.success else Severity.WARNING,
            details={
                "node": node_id,
                "command": command[:200],
                "return_code": result.return_code,
                "duration_ms": result.duration_ms,
            },
        )
        return result

    # ------------------------------------------------------------------
    # Health checks
    # ------------------------------------------------------------------

    def _health_check_mac(self, node_id: str) -> NodeHealth:
        """Health check for macOS nodes (B and C)."""
        cpu_result = self.ssh_exec(node_id, "top -l 1 -n 0 | grep 'CPU usage'", timeout=15)
        ram_result = self.ssh_exec(node_id, "vm_stat | head -5", timeout=10)
        uptime_result = self.ssh_exec(node_id, "uptime", timeout=10)
        docker_result = self.ssh_exec(node_id, "docker ps --format '{{.Names}}' 2>/dev/null", timeout=10)

        reachable = cpu_result.return_code != -1
        cpu_load = 0.0
        ram_pct = 0.0

        if cpu_result.success and "CPU usage" in cpu_result.stdout:
            try:
                parts = cpu_result.stdout.split("CPU usage:")[-1]
                user_pct = float(parts.split("%")[0].strip())
                sys_pct = float(parts.split(",")[1].split("%")[0].strip())
                cpu_load = user_pct + sys_pct
            except (ValueError, IndexError):
                pass

        docker_running = docker_result.success
        containers = docker_result.stdout.split("\n") if docker_result.success and docker_result.stdout else []

        node = self.registry.get(node_id)
        ram_avail = node.hardware.ram_gb * (1 - ram_pct / 100) if node else 0

        return NodeHealth(
            node_id=node_id,
            reachable=reachable,
            cpu_load_pct=cpu_load,
            ram_used_pct=ram_pct,
            ram_available_gb=ram_avail,
            docker_running=docker_running,
            services_up=containers,
        )

    def _health_check_windows(self, node_id: str) -> NodeHealth:
        """Health check for the primary Windows node (A = ROG)."""
        # Local checks for Windows primary
        try:
            import platform
            import psutil  # type: ignore[import-untyped]
            cpu_load = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            return NodeHealth(
                node_id=node_id,
                reachable=True,
                cpu_load_pct=cpu_load,
                ram_used_pct=ram.percent,
                ram_available_gb=ram.available / (1024 ** 3),
                disk_used_pct=disk.percent,
                docker_running=True,
            )
        except ImportError:
            # psutil not installed — fallback
            return NodeHealth(node_id=node_id, reachable=True)

    def health_check(self, node_id: str) -> NodeHealth:
        """Run a health check on a single node."""
        node = self.registry.get(node_id)
        if not node:
            return NodeHealth(node_id=node_id, reachable=False)

        if node.connection_method == ConnectionMethod.LOCAL:
            health = self._health_check_windows(node_id)
        else:
            health = self._health_check_mac(node_id)

        # Update registry status
        status = NodeStatus.ONLINE if health.reachable else NodeStatus.UNREACHABLE
        if health.reachable and health.cpu_load_pct > 90:
            status = NodeStatus.BUSY
        self.registry.update_status(node_id, status, health.cpu_load_pct, health.ram_used_pct)

        self._health_cache[node_id] = health
        return health

    def health_check_all(self) -> dict[str, NodeHealth]:
        """Health check all nodes in the fleet."""
        results = {}
        for node in self.registry.all_nodes():
            results[node.node_id] = self.health_check(node.node_id)
        self.audit.record(
            agent="fleet_orchestrator",
            action="health_check_all",
            severity=Severity.INFO,
            details={
                "nodes_checked": len(results),
                "online": sum(1 for h in results.values() if h.reachable),
            },
        )
        return results

    # ------------------------------------------------------------------
    # Task dispatch
    # ------------------------------------------------------------------

    def _select_node(self, task: FleetTask) -> str:
        """Select the optimal node for a task based on requirements."""
        if task.preferred_node:
            return task.preferred_node

        # GPU tasks → A (ROG has the RTX 4060)
        if task.requires_gpu:
            return "rog"

        # High RAM tasks → A (64GB)
        if task.min_ram_gb > 18:
            return "rog"

        # Homelink / daemon tasks → C (Mac Mini, always-on)
        homelink_keywords = ["homelink", "n8n", "monitor", "backup", "sync", "webhook"]
        if any(kw in task.description.lower() for kw in homelink_keywords):
            return "mac-mini"

        # Dev tasks → B (MacBook Pro)
        dev_keywords = ["build", "compile", "xcode", "swift", "ios"]
        if any(kw in task.description.lower() for kw in dev_keywords):
            return "macbook-pro"

        # Default: use the least loaded node
        healths = self._health_cache
        if healths:
            candidates = [
                (nid, h) for nid, h in healths.items()
                if h.reachable and h.ram_available_gb >= task.min_ram_gb
            ]
            if candidates:
                return min(candidates, key=lambda x: x[1].cpu_load_pct)[0]

        return "rog"  # Fallback to primary

    def dispatch(self, task: FleetTask) -> FleetTask:
        """Dispatch a task to the optimal node and execute it."""
        target = self._select_node(task)
        task.assigned_node = target
        task.status = TaskStatus.DISPATCHED

        self.audit.record(
            agent="fleet_orchestrator",
            action="task_dispatch",
            severity=Severity.INFO,
            details={
                "task_id": task.task_id,
                "node": target,
                "command": task.command[:200],
                "priority": task.priority.value,
            },
        )

        result = self.ssh_exec(target, task.command, timeout=120)
        task.result = result
        task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED

        self._tasks.append(task)
        return task

    # ------------------------------------------------------------------
    # Service management
    # ------------------------------------------------------------------

    def start_service(self, node_id: str, service: str) -> CommandResult:
        """Start a service on a remote node."""
        # Map service names to start commands
        service_commands: dict[str, dict[str, str]] = {
            "n8n": {
                "macos": "docker start n8n 2>/dev/null || docker run -d --name n8n -p 5678:5678 n8nio/n8n",
                "windows": "docker start n8n 2>nul || docker run -d --name n8n -p 5678:5678 n8nio/n8n",
            },
            "homelink_gateway": {
                "macos": "cd ~/JT && python -m guardian_one.homelink.gateway &",
            },
            "homelink_monitor": {
                "macos": "cd ~/JT && python -m guardian_one.homelink.monitor &",
            },
            "ollama": {
                "windows": "ollama serve",
                "macos": "ollama serve",
            },
            "backup_agent": {
                "macos": "cd ~/JT && python main.py --schedule &",
            },
        }

        node = self.registry.get(node_id)
        if not node:
            return CommandResult(node_id=node_id, command=f"start {service}",
                                return_code=-1, stderr=f"Unknown node: {node_id}")

        os_key = "macos" if node.os.value == "macos" else "windows"
        cmd_map = service_commands.get(service, {})
        cmd = cmd_map.get(os_key, "")

        if not cmd:
            return CommandResult(node_id=node_id, command=f"start {service}",
                                return_code=-1, stderr=f"No start command for {service} on {os_key}")

        self.audit.record(
            agent="fleet_orchestrator",
            action="service_start",
            severity=Severity.INFO,
            details={"node": node_id, "service": service},
        )
        return self.ssh_exec(node_id, cmd, timeout=30)

    def stop_service(self, node_id: str, service: str) -> CommandResult:
        """Stop a service on a remote node."""
        stop_commands: dict[str, str] = {
            "n8n": "docker stop n8n",
            "ollama": "pkill ollama",
        }
        cmd = stop_commands.get(service, f"pkill -f {service}")
        return self.ssh_exec(node_id, cmd, timeout=15)

    def list_services(self, node_id: str) -> CommandResult:
        """List running services/containers on a node."""
        node = self.registry.get(node_id)
        if not node:
            return CommandResult(node_id=node_id, command="list services",
                                return_code=-1, stderr=f"Unknown node: {node_id}")

        if node.os.value == "macos":
            cmd = "docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}' 2>/dev/null; echo '---'; ps aux | grep -E 'guardian|n8n|ollama' | grep -v grep"
        else:
            cmd = "docker ps --format \"table {{.Names}}\\t{{.Status}}\\t{{.Ports}}\" 2>nul"
        return self.ssh_exec(node_id, cmd, timeout=15)

    # ------------------------------------------------------------------
    # Kernel & daemon overview
    # ------------------------------------------------------------------

    def kernel_info(self, node_id: str) -> dict[str, Any]:
        """Get kernel and OS info for a single node."""
        node = self.registry.get(node_id)
        if not node:
            return {"node_id": node_id, "error": f"Unknown node: {node_id}"}

        result: dict[str, Any] = {"node_id": node_id, "name": node.name, "os": node.os.value}

        if node.os.value == "macos":
            kern = self.ssh_exec(node_id, "uname -srm", timeout=10)
            sw_vers = self.ssh_exec(node_id, "sw_vers 2>/dev/null | tr '\\n' ' '", timeout=10)
            uptime = self.ssh_exec(node_id, "uptime", timeout=10)
            result["kernel"] = kern.stdout if kern.success else "unreachable"
            result["os_version"] = sw_vers.stdout.strip() if sw_vers.success else ""
            result["uptime"] = uptime.stdout.strip() if uptime.success else ""
        else:
            if node.os.value == "windows":
                kern = self.ssh_exec(node_id, "ver 2>nul", timeout=10)
                uptime = self.ssh_exec(node_id, "echo N/A", timeout=10)
            else:
                kern = self.ssh_exec(node_id, "uname -srm", timeout=10)
                uptime = self.ssh_exec(node_id, "uptime 2>/dev/null || echo N/A", timeout=10)
            result["kernel"] = kern.stdout.strip() if kern.success else "unreachable"
            result["uptime"] = uptime.stdout.strip() if uptime.success else ""

        return result

    def list_daemons(self, node_id: str) -> dict[str, Any]:
        """List active daemons/background services on a node."""
        node = self.registry.get(node_id)
        if not node:
            return {"node_id": node_id, "error": f"Unknown node: {node_id}"}

        result: dict[str, Any] = {"node_id": node_id, "name": node.name}

        if node.os.value == "macos":
            # LaunchDaemons + Docker + Guardian processes
            daemons_cmd = (
                "echo '=== LAUNCHD DAEMONS ===' && "
                "launchctl list 2>/dev/null | grep -E 'com\\.(apple|docker|n8n|guardian|ollama)' | head -20 && "
                "echo '' && echo '=== DOCKER CONTAINERS ===' && "
                "docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Image}}' 2>/dev/null || echo 'Docker not running' && "
                "echo '' && echo '=== GUARDIAN PROCESSES ===' && "
                "ps aux | grep -E 'guardian|n8n|ollama|node|python.*main' | grep -v grep"
            )
        else:
            # Windows: services + Docker + processes
            daemons_cmd = (
                "echo === DOCKER CONTAINERS === && "
                "docker ps --format \"table {{.Names}}\\t{{.Status}}\\t{{.Image}}\" 2>nul && "
                "echo. && echo === KEY PROCESSES === && "
                "tasklist /FI \"IMAGENAME eq ollama*\" /FI \"STATUS eq Running\" 2>nul & "
                "tasklist /FI \"IMAGENAME eq python*\" /FI \"STATUS eq Running\" 2>nul & "
                "tasklist /FI \"IMAGENAME eq docker*\" /FI \"STATUS eq Running\" 2>nul & "
                "tasklist /FI \"IMAGENAME eq node*\" /FI \"STATUS eq Running\" 2>nul"
            )

        cmd_result = self.ssh_exec(node_id, daemons_cmd, timeout=20)
        result["daemons_output"] = cmd_result.stdout if cmd_result.success else cmd_result.stderr
        result["reachable"] = cmd_result.return_code != -1

        # Docker containers separately for structured data
        docker_result = self.ssh_exec(node_id, "docker ps --format '{{.Names}}|{{.Status}}|{{.Image}}' 2>/dev/null", timeout=10)
        containers = []
        if docker_result.success and docker_result.stdout:
            for line in docker_result.stdout.strip().split("\n"):
                parts = line.split("|")
                if len(parts) == 3:
                    containers.append({
                        "name": parts[0],
                        "status": parts[1],
                        "image": parts[2],
                    })
        result["docker_containers"] = containers

        return result

    def fleet_kernel_overview(self) -> dict[str, Any]:
        """Get kernel + daemon info for ALL nodes in the fleet."""
        overview: dict[str, Any] = {"nodes": {}}
        for node in self.registry.all_nodes():
            nid = node.node_id
            kernel = self.kernel_info(nid)
            daemons = self.list_daemons(nid)
            overview["nodes"][nid] = {
                "kernel": kernel,
                "daemons": daemons,
                "role": node.role.value,
                "assigned_services": node.assigned_services,
            }
        return overview

    # ------------------------------------------------------------------
    # Fleet dashboard
    # ------------------------------------------------------------------

    def fleet_dashboard(self) -> str:
        """Generate a formatted fleet dashboard for the CLI."""
        summary = self.registry.fleet_summary()
        lines = [
            "=" * 70,
            "  GUARDIAN ONE — FLEET COMMAND CENTER",
            "=" * 70,
            f"  Fleet: {summary['total_nodes']} nodes | "
            f"RAM: {summary['total_ram_gb']}GB total | "
            f"Storage: {summary['total_storage_gb']}GB total",
            "",
        ]

        for node_data in summary["nodes"]:
            nid = node_data["id"]
            health = self._health_cache.get(nid)
            status_icon = {
                "online": "[OK]",
                "offline": "[--]",
                "busy": "[!!]",
                "unreachable": "[??]",
                "unknown": "[..]",
            }.get(node_data["status"], "[..]")

            lines.append(f"  {status_icon} {node_data['name']}")
            lines.append(f"      Role: {node_data['role'].upper()} | OS: {node_data['os']} | RAM: {node_data['ram_gb']}GB")
            lines.append(f"      CPU: {node_data['cpu']}")

            if health and health.reachable:
                lines.append(f"      Load: CPU {health.cpu_load_pct:.0f}% | RAM {health.ram_used_pct:.0f}% | "
                             f"Free RAM: {health.ram_available_gb:.1f}GB")
                if health.docker_running:
                    lines.append(f"      Docker: running ({len(health.services_up)} containers)")

            if node_data["services"]:
                lines.append(f"      Services: {', '.join(node_data['services'][:5])}")
                if len(node_data["services"]) > 5:
                    lines.append(f"                +{len(node_data['services']) - 5} more")

            if node_data["displays"]:
                lines.append(f"      Displays: {', '.join(node_data['displays'])}")

            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)
