"""Fleet Commander — Root CLI interface for managing the compute fleet.

This is the command center that Jeremy uses from A (ROG) to:
- View fleet status at a glance
- Health-check all nodes
- SSH into B or C with a single command
- Start/stop services on remote nodes
- View display layout
- See subscription portfolio and optimization recommendations
- Execute tasks on the optimal node
- View backup status and strategy

CLI commands (wired into main.py):
    python main.py --fleet              # Full fleet dashboard
    python main.py --fleet-health       # Health check all nodes
    python main.py --fleet-ssh NODE CMD # SSH command on a node
    python main.py --fleet-start NODE SERVICE  # Start service on node
    python main.py --fleet-stop NODE SERVICE   # Stop service on node
    python main.py --fleet-services NODE       # List services on node
    python main.py --fleet-displays     # Display topology + ASCII layout
    python main.py --fleet-resources    # Resource optimization dashboard
    python main.py --fleet-subs         # Subscription portfolio
    python main.py --fleet-backup       # Backup strategy
"""

from __future__ import annotations

from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.fleet.displays import DisplayTopology
from guardian_one.fleet.nodes import FleetRegistry
from guardian_one.fleet.orchestrator import FleetOrchestrator
from guardian_one.fleet.resources import ResourceOptimizer


class FleetCommander:
    """Unified command interface for fleet management.

    Instantiated once and used by main.py to handle all --fleet-* commands.
    """

    def __init__(self, audit: AuditLog) -> None:
        self.audit = audit
        self.registry = FleetRegistry()
        self.displays = DisplayTopology()
        self.orchestrator = FleetOrchestrator(self.registry, audit)
        self.resources = ResourceOptimizer(self.registry)

    def initialize(self) -> None:
        """Load all fleet defaults."""
        self.registry.load_defaults()
        self.displays.load_defaults()
        self.resources.load_defaults()
        self.audit.record(
            agent="fleet_commander",
            action="init",
            severity=Severity.INFO,
            details={
                "nodes": len(self.registry.all_nodes()),
                "displays": len(self.displays.all_displays()),
                "subscriptions": len(self.resources.all_subscriptions()),
            },
        )

    # ------------------------------------------------------------------
    # CLI handlers
    # ------------------------------------------------------------------

    def cmd_fleet(self) -> str:
        """--fleet: Full fleet dashboard."""
        return self.orchestrator.fleet_dashboard()

    def cmd_health(self) -> str:
        """--fleet-health: Health check all nodes."""
        results = self.orchestrator.health_check_all()
        lines = [
            "=" * 70,
            "  FLEET HEALTH CHECK",
            "=" * 70,
            "",
        ]
        for nid, health in results.items():
            node = self.registry.get(nid)
            name = node.name if node else nid
            status = "[OK]" if health.reachable else "[FAIL]"
            lines.append(f"  {status} {name} ({nid})")
            if health.reachable:
                lines.append(f"      CPU: {health.cpu_load_pct:.0f}% | "
                             f"RAM: {health.ram_used_pct:.0f}% | "
                             f"Free: {health.ram_available_gb:.1f}GB")
                if health.docker_running:
                    containers = len(health.services_up)
                    lines.append(f"      Docker: {containers} container(s) running")
                if health.services_down:
                    lines.append(f"      DOWN: {', '.join(health.services_down)}")
            else:
                lines.append("      UNREACHABLE — check network/SSH")
            lines.append("")

        online = sum(1 for h in results.values() if h.reachable)
        lines.append(f"  Fleet: {online}/{len(results)} nodes online")
        lines.append("=" * 70)
        return "\n".join(lines)

    def cmd_ssh(self, node_id: str, command: str) -> str:
        """--fleet-ssh NODE CMD: Execute SSH command on a node."""
        result = self.orchestrator.ssh_exec(node_id, command)
        lines = [
            f"  Node: {node_id}",
            f"  Command: {command}",
            f"  Return code: {result.return_code}",
            f"  Duration: {result.duration_ms:.0f}ms",
        ]
        if result.stdout:
            lines.append(f"\n  --- stdout ---\n{result.stdout}")
        if result.stderr:
            lines.append(f"\n  --- stderr ---\n{result.stderr}")
        return "\n".join(lines)

    def cmd_start_service(self, node_id: str, service: str) -> str:
        """--fleet-start NODE SERVICE: Start a service."""
        result = self.orchestrator.start_service(node_id, service)
        status = "STARTED" if result.success else "FAILED"
        msg = f"  [{status}] {service} on {node_id}"
        if result.stderr:
            msg += f"\n  Error: {result.stderr}"
        return msg

    def cmd_stop_service(self, node_id: str, service: str) -> str:
        """--fleet-stop NODE SERVICE: Stop a service."""
        result = self.orchestrator.stop_service(node_id, service)
        status = "STOPPED" if result.success else "FAILED"
        msg = f"  [{status}] {service} on {node_id}"
        if result.stderr:
            msg += f"\n  Error: {result.stderr}"
        return msg

    def cmd_list_services(self, node_id: str) -> str:
        """--fleet-services NODE: List running services."""
        result = self.orchestrator.list_services(node_id)
        node = self.registry.get(node_id)
        name = node.name if node else node_id
        lines = [
            f"  Services on {name} ({node_id}):",
            "",
        ]
        if result.success:
            lines.append(result.stdout)
        else:
            lines.append(f"  Error: {result.stderr}")
        return "\n".join(lines)

    def cmd_displays(self) -> str:
        """--fleet-displays: Show display topology."""
        layout = self.displays.layout_diagram()
        summary = self.displays.summary()
        lines = [layout, ""]

        for d in summary["displays"]:
            lines.append(f'  {d["name"]}')
            lines.append(f'      {d["resolution"]} @ {d["refresh"]} | {d["position"]}')
            lines.append(f'      Connected to: {d["node"]}')
            lines.append("")

        lines.append(f"  Total pixels: {summary['total_resolution']}")
        return "\n".join(lines)

    def cmd_resources(self) -> str:
        """--fleet-resources: Resource optimization dashboard."""
        return self.resources.optimization_dashboard()

    def cmd_subscriptions(self) -> str:
        """--fleet-subs: Subscription portfolio."""
        return self.resources.subscription_dashboard()

    def cmd_backup(self) -> str:
        """--fleet-backup: Backup strategy."""
        backups = self.resources.backup_plan()
        lines = [
            "=" * 70,
            "  FLEET BACKUP STRATEGY",
            "=" * 70,
            "",
        ]
        for b in backups:
            node = self.registry.get(b.node_id)
            name = node.name if node else b.node_id
            lines.append(f"  {b.name}")
            lines.append(f"      Runner: {name} ({b.node_id})")
            lines.append(f"      Target: {b.target_path}")
            lines.append(f"      Schedule: {b.schedule_cron}")
            lines.append(f"      Retention: {b.retention_days} days | Encrypted: {b.encrypted}")
            if b.includes:
                lines.append(f"      Includes: {', '.join(b.includes[:3])}")
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)

    def cmd_kernels(self) -> str:
        """--fleet-kernels: Show active kernels and daemons across all 3 nodes."""
        overview = self.orchestrator.fleet_kernel_overview()
        lines = [
            "=" * 70,
            "  GUARDIAN ONE — ACTIVE KERNELS & DAEMONS",
            "=" * 70,
            "",
        ]

        role_labels = {
            "primary": "PRIMARY (Controller)",
            "workstation": "WORKSTATION",
            "daemon": "DAEMON (Always-On)",
        }

        for nid, data in overview["nodes"].items():
            node = self.registry.get(nid)
            name = node.name if node else nid
            role = role_labels.get(data["role"], data["role"])
            kernel = data["kernel"]
            daemons = data["daemons"]

            reachable = daemons.get("reachable", False)
            status_icon = "[OK]" if reachable else "[--]"

            lines.append(f"  {status_icon} {name} ({nid}) — {role}")
            lines.append(f"  " + "-" * 60)

            # Kernel info
            kern_str = kernel.get("kernel", "unreachable")
            os_ver = kernel.get("os_version", "")
            uptime = kernel.get("uptime", "")
            lines.append(f"      Kernel:  {kern_str}")
            if os_ver:
                lines.append(f"      OS:      {os_ver}")
            if uptime:
                lines.append(f"      Uptime:  {uptime}")

            # Docker containers
            containers = daemons.get("docker_containers", [])
            if containers:
                lines.append(f"      Docker:  {len(containers)} container(s)")
                for c in containers:
                    lines.append(f"        - {c['name']:<20} {c['status']:<25} {c['image']}")
            else:
                lines.append("      Docker:  no containers running")

            # Assigned services (from config)
            services = data.get("assigned_services", [])
            if services:
                lines.append(f"      Assigned services ({len(services)}):")
                # Show in two columns
                for i in range(0, len(services), 2):
                    pair = services[i:i+2]
                    line = "        " + "  ".join(f"- {s:<28}" for s in pair)
                    lines.append(line)

            # Raw daemon output (abbreviated)
            raw = daemons.get("daemons_output", "")
            if raw and reachable:
                # Show just the Guardian/key processes section
                for section in raw.split("==="):
                    section = section.strip()
                    if not section:
                        continue
                    header = section.split("\n")[0].strip()
                    if header in ("GUARDIAN PROCESSES", "KEY PROCESSES"):
                        proc_lines = [l.strip() for l in section.split("\n")[1:] if l.strip()]
                        if proc_lines:
                            lines.append(f"      Active processes:")
                            for pl in proc_lines[:10]:
                                # Truncate long lines
                                lines.append(f"        {pl[:70]}")

            lines.append("")

        # Fleet totals
        total_nodes = len(overview["nodes"])
        reachable_count = sum(
            1 for d in overview["nodes"].values()
            if d["daemons"].get("reachable", False)
        )
        total_containers = sum(
            len(d["daemons"].get("docker_containers", []))
            for d in overview["nodes"].values()
        )
        total_services = sum(
            len(d.get("assigned_services", []))
            for d in overview["nodes"].values()
        )

        lines.append(f"  FLEET TOTALS: {reachable_count}/{total_nodes} nodes online | "
                     f"{total_containers} Docker containers | "
                     f"{total_services} assigned services")
        lines.append("=" * 70)
        return "\n".join(lines)

    def cmd_full_status(self) -> str:
        """Complete fleet status — combines fleet + displays + resources."""
        parts = [
            self.cmd_fleet(),
            "",
            self.displays.layout_diagram(),
            "",
            self.resources.subscription_dashboard(),
        ]
        return "\n".join(parts)
