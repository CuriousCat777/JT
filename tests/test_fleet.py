"""Tests for the Fleet Management system (multi-device orchestration).

Covers:
- Node registry (3 nodes: ROG, MacBook Pro, Mac Mini)
- Fleet orchestrator (task dispatch, node selection)
- Display topology (4 displays: ultrawide, Alienware, 2 TVs)
- Resource optimizer (subscriptions, backup plan, recommendations)
- Fleet commander (CLI interface)
"""

import pytest
from pathlib import Path

from guardian_one.core.audit import AuditLog
from guardian_one.fleet.nodes import (
    ComputeNode,
    ConnectionMethod,
    CPUSpec,
    FleetRegistry,
    GPUSpec,
    HardwareSpec,
    NetworkIdentity,
    NodeOS,
    NodeRole,
    NodeStatus,
    StorageSpec,
)
from guardian_one.fleet.displays import (
    DisplaySpec,
    DisplayTopology,
    DisplayType,
    DisplayConnection,
    DisplayPosition,
)
from guardian_one.fleet.orchestrator import (
    CommandResult,
    FleetOrchestrator,
    FleetTask,
    NodeHealth,
    TaskPriority,
    TaskStatus,
)
from guardian_one.fleet.resources import (
    ResourceCategory,
    ResourceOptimizer,
    Subscription,
    SubscriptionTier,
)
from guardian_one.fleet.commander import FleetCommander


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def audit(tmp_path: Path) -> AuditLog:
    return AuditLog(log_dir=tmp_path)


@pytest.fixture
def registry() -> FleetRegistry:
    reg = FleetRegistry()
    reg.load_defaults()
    return reg


@pytest.fixture
def display_topology() -> DisplayTopology:
    topo = DisplayTopology()
    topo.load_defaults()
    return topo


@pytest.fixture
def orchestrator(registry: FleetRegistry, audit: AuditLog) -> FleetOrchestrator:
    return FleetOrchestrator(registry, audit)


@pytest.fixture
def optimizer(registry: FleetRegistry) -> ResourceOptimizer:
    opt = ResourceOptimizer(registry)
    opt.load_defaults()
    return opt


@pytest.fixture
def commander(audit: AuditLog) -> FleetCommander:
    cmd = FleetCommander(audit)
    cmd.initialize()
    return cmd


# ===========================================================================
# Node Registry Tests
# ===========================================================================

class TestFleetRegistry:
    def test_load_defaults_three_nodes(self, registry: FleetRegistry) -> None:
        nodes = registry.all_nodes()
        assert len(nodes) == 3

    def test_primary_is_rog(self, registry: FleetRegistry) -> None:
        primary = registry.primary()
        assert primary is not None
        assert primary.node_id == "rog"
        assert primary.role == NodeRole.PRIMARY
        assert primary.os == NodeOS.WINDOWS
        assert primary.hardware.ram_gb == 64

    def test_daemon_is_mac_mini(self, registry: FleetRegistry) -> None:
        daemon = registry.daemon()
        assert daemon is not None
        assert daemon.node_id == "mac-mini"
        assert daemon.role == NodeRole.DAEMON

    def test_workstation_is_macbook(self, registry: FleetRegistry) -> None:
        ws = registry.workstations()
        assert len(ws) == 1
        assert ws[0].node_id == "macbook-pro"
        assert ws[0].is_stationary is True

    def test_managed_nodes_excludes_primary(self, registry: FleetRegistry) -> None:
        managed = registry.managed_nodes()
        assert len(managed) == 2
        assert all(n.role != NodeRole.PRIMARY for n in managed)

    def test_total_ram(self, registry: FleetRegistry) -> None:
        # ROG 64 + MacBook 18 + Mac Mini 16 = 98
        assert registry.total_ram_gb() == 98

    def test_total_storage(self, registry: FleetRegistry) -> None:
        # ROG 2000 + MacBook 512 + Mac Mini 512 = 3024
        assert registry.total_storage_gb() == 3024

    def test_fleet_summary_structure(self, registry: FleetRegistry) -> None:
        summary = registry.fleet_summary()
        assert summary["total_nodes"] == 3
        assert summary["total_ram_gb"] == 98
        assert len(summary["nodes"]) == 3

    def test_get_node(self, registry: FleetRegistry) -> None:
        rog = registry.get("rog")
        assert rog is not None
        assert rog.name == "ASUS ROG Flow Z13"

    def test_get_nonexistent(self, registry: FleetRegistry) -> None:
        assert registry.get("nonexistent") is None

    def test_update_status(self, registry: FleetRegistry) -> None:
        assert registry.update_status("rog", NodeStatus.ONLINE, 25.0, 40.0)
        rog = registry.get("rog")
        assert rog is not None
        assert rog.status == NodeStatus.ONLINE
        assert rog.current_load_pct == 25.0
        assert rog.ram_used_pct == 40.0

    def test_rog_has_gpu(self, registry: FleetRegistry) -> None:
        rog = registry.get("rog")
        assert rog is not None
        assert rog.hardware.gpu is not None
        assert rog.hardware.gpu.vram_gb == 8
        assert rog.hardware.gpu.cuda_cores == 3072

    def test_macbook_is_arm(self, registry: FleetRegistry) -> None:
        mb = registry.get("macbook-pro")
        assert mb is not None
        assert mb.hardware.cpu.architecture == "arm64"

    def test_mac_mini_has_ethernet(self, registry: FleetRegistry) -> None:
        mm = registry.get("mac-mini")
        assert mm is not None
        assert mm.hardware.ethernet is True

    def test_rog_connection_is_local(self, registry: FleetRegistry) -> None:
        rog = registry.get("rog")
        assert rog is not None
        assert rog.connection_method == ConnectionMethod.LOCAL

    def test_remote_nodes_use_ssh(self, registry: FleetRegistry) -> None:
        for nid in ["macbook-pro", "mac-mini"]:
            node = registry.get(nid)
            assert node is not None
            assert node.connection_method == ConnectionMethod.SSH

    def test_mac_mini_services_include_homelink(self, registry: FleetRegistry) -> None:
        mm = registry.get("mac-mini")
        assert mm is not None
        assert "homelink_gateway" in mm.assigned_services
        assert "homelink_monitor" in mm.assigned_services
        assert "n8n" in mm.assigned_services

    def test_register_and_remove(self, registry: FleetRegistry) -> None:
        custom = ComputeNode(
            node_id="test-node",
            name="Test Node",
            role=NodeRole.WORKSTATION,
            os=NodeOS.LINUX,
            hardware=HardwareSpec(
                cpu=CPUSpec(model="Test CPU", cores=4, threads=8, base_clock_ghz=3.0),
                ram_gb=32,
            ),
            network=NetworkIdentity(hostname="test"),
        )
        registry.register(custom)
        assert len(registry.all_nodes()) == 4
        assert registry.remove("test-node")
        assert len(registry.all_nodes()) == 3


# ===========================================================================
# Display Topology Tests
# ===========================================================================

class TestDisplayTopology:
    def test_load_defaults_four_displays(self, display_topology: DisplayTopology) -> None:
        assert len(display_topology.all_displays()) == 4

    def test_two_monitors(self, display_topology: DisplayTopology) -> None:
        monitors = display_topology.monitors()
        assert len(monitors) == 2

    def test_two_tvs(self, display_topology: DisplayTopology) -> None:
        tvs = display_topology.tvs()
        assert len(tvs) == 2

    def test_ultrawide_split(self, display_topology: DisplayTopology) -> None:
        uw = display_topology.get("ultrawide-49")
        assert uw is not None
        assert uw.split_between_nodes is True
        assert uw.split_node_left == "rog"
        assert uw.split_node_right == "macbook-pro"

    def test_alienware_connected_to_rog(self, display_topology: DisplayTopology) -> None:
        aw = display_topology.get("alienware-25")
        assert aw is not None
        assert aw.connected_to_node == "rog"
        assert aw.refresh_rate_hz == 240

    def test_samsung_frame_connected_to_mac_mini(self, display_topology: DisplayTopology) -> None:
        sf = display_topology.get("samsung-frame-65")
        assert sf is not None
        assert sf.connected_to_node == "mac-mini"
        assert sf.supports_cec is True

    def test_lg_nanocell_flexible(self, display_topology: DisplayTopology) -> None:
        lg = display_topology.get("lg-nanocell-65")
        assert lg is not None
        assert lg.connected_to_node == ""  # Flexible

    def test_displays_by_node_rog(self, display_topology: DisplayTopology) -> None:
        rog_displays = display_topology.by_node("rog")
        # Ultrawide (split left) + Alienware
        assert len(rog_displays) == 2

    def test_displays_by_node_macbook(self, display_topology: DisplayTopology) -> None:
        mb_displays = display_topology.by_node("macbook-pro")
        # Ultrawide (split right)
        assert len(mb_displays) == 1

    def test_total_pixels(self, display_topology: DisplayTopology) -> None:
        # 5120*1440 + 2560*1440 + 3840*2160 + 3840*2160
        expected = 5120 * 1440 + 2560 * 1440 + 3840 * 2160 + 3840 * 2160
        assert display_topology.total_pixels() == expected

    def test_layout_diagram_not_empty(self, display_topology: DisplayTopology) -> None:
        diagram = display_topology.layout_diagram()
        assert "Samsung 49" in diagram
        assert "Alienware" in diagram
        assert "LG NanoCell" in diagram
        assert "Samsung Frame" in diagram

    def test_summary_structure(self, display_topology: DisplayTopology) -> None:
        summary = display_topology.summary()
        assert summary["total_displays"] == 4
        assert summary["monitors"] == 2
        assert summary["tvs"] == 2


# ===========================================================================
# Fleet Orchestrator Tests
# ===========================================================================

class TestFleetOrchestrator:
    def test_task_dispatch_gpu_goes_to_rog(self, orchestrator: FleetOrchestrator) -> None:
        task = FleetTask(
            task_id="test-gpu",
            description="Train ML model",
            command="echo test",
            requires_gpu=True,
        )
        target = orchestrator._select_node(task)
        assert target == "rog"

    def test_task_dispatch_high_ram_goes_to_rog(self, orchestrator: FleetOrchestrator) -> None:
        task = FleetTask(
            task_id="test-ram",
            description="Large data processing",
            command="echo test",
            min_ram_gb=32,
        )
        target = orchestrator._select_node(task)
        assert target == "rog"

    def test_task_dispatch_homelink_goes_to_mac_mini(self, orchestrator: FleetOrchestrator) -> None:
        task = FleetTask(
            task_id="test-homelink",
            description="Run homelink monitor service",
            command="echo test",
        )
        target = orchestrator._select_node(task)
        assert target == "mac-mini"

    def test_task_dispatch_n8n_goes_to_mac_mini(self, orchestrator: FleetOrchestrator) -> None:
        task = FleetTask(
            task_id="test-n8n",
            description="Start n8n workflow",
            command="echo test",
        )
        target = orchestrator._select_node(task)
        assert target == "mac-mini"

    def test_task_dispatch_xcode_goes_to_macbook(self, orchestrator: FleetOrchestrator) -> None:
        task = FleetTask(
            task_id="test-xcode",
            description="Build Xcode project",
            command="echo test",
        )
        target = orchestrator._select_node(task)
        assert target == "macbook-pro"

    def test_task_dispatch_preferred_node(self, orchestrator: FleetOrchestrator) -> None:
        task = FleetTask(
            task_id="test-preferred",
            description="Custom task",
            command="echo test",
            preferred_node="mac-mini",
        )
        target = orchestrator._select_node(task)
        assert target == "mac-mini"

    def test_ssh_exec_unknown_node(self, orchestrator: FleetOrchestrator) -> None:
        result = orchestrator.ssh_exec("nonexistent", "echo hi")
        assert result.return_code == -1
        assert "Unknown node" in result.stderr

    def test_ssh_exec_local_primary(self, orchestrator: FleetOrchestrator) -> None:
        # ROG is local — should run locally via shell
        result = orchestrator.ssh_exec("rog", "echo hello")
        assert result.node_id == "rog"
        assert "Unknown node" not in result.stderr
        # In environments where shell is available, this succeeds
        if result.success:
            assert "hello" in result.stdout

    def test_command_result_success_property(self) -> None:
        ok = CommandResult(node_id="test", command="test", return_code=0)
        assert ok.success is True

        fail = CommandResult(node_id="test", command="test", return_code=1)
        assert fail.success is False

    def test_fleet_dashboard_format(self, orchestrator: FleetOrchestrator) -> None:
        dashboard = orchestrator.fleet_dashboard()
        assert "FLEET COMMAND CENTER" in dashboard
        assert "ASUS ROG Flow Z13" in dashboard
        assert "MacBook Pro 2024" in dashboard
        assert "Mac Mini" in dashboard

    def test_build_ssh_command(self, orchestrator: FleetOrchestrator) -> None:
        node = orchestrator.registry.get("macbook-pro")
        assert node is not None
        cmd = orchestrator._build_ssh_command(node, "ls -la")
        assert "ssh" in cmd
        assert "ls -la" in cmd


# ===========================================================================
# Resource Optimizer Tests
# ===========================================================================

class TestResourceOptimizer:
    def test_load_defaults_subscriptions(self, optimizer: ResourceOptimizer) -> None:
        subs = optimizer.all_subscriptions()
        assert len(subs) == 8

    def test_subscriptions_by_node_rog(self, optimizer: ResourceOptimizer) -> None:
        rog_subs = optimizer.subscriptions_by_node("rog")
        assert len(rog_subs) >= 5  # Docker, ChatGPT, Codex, Claude, VS Code

    def test_subscriptions_by_node_mac_mini(self, optimizer: ResourceOptimizer) -> None:
        mm_subs = optimizer.subscriptions_by_node("mac-mini")
        assert len(mm_subs) >= 3  # Zapier, Notion, n8n

    def test_always_on_services(self, optimizer: ResourceOptimizer) -> None:
        ao = optimizer.always_on_services()
        assert len(ao) >= 3  # Zapier, Notion, n8n
        names = {s.name for s in ao}
        assert "n8n" in names
        assert "Zapier" in names
        assert "Notion" in names

    def test_fleet_resource_summary(self, optimizer: ResourceOptimizer) -> None:
        summary = optimizer.fleet_resource_summary()
        assert summary["total_ram_gb"] == 98
        assert summary["total_cores"] == 34  # 14 + 12 + 8
        assert summary["subscriptions"] == 8

    def test_optimization_recommendations(self, optimizer: ResourceOptimizer) -> None:
        recs = optimizer.optimization_recommendations()
        assert len(recs) > 0
        # GPU workloads should go to ROG
        gpu_recs = [r for r in recs if r.gpu_required]
        assert all(r.recommended_node == "rog" for r in gpu_recs)
        # Homelink should go to mac-mini
        hl_recs = [r for r in recs if "H.O.M.E" in r.workload]
        assert all(r.recommended_node == "mac-mini" for r in hl_recs)

    def test_backup_plan(self, optimizer: ResourceOptimizer) -> None:
        backups = optimizer.backup_plan()
        assert len(backups) >= 3
        # Mac mini runs most backups
        mm_backups = [b for b in backups if b.node_id == "mac-mini"]
        assert len(mm_backups) >= 2

    def test_subscription_dashboard_format(self, optimizer: ResourceOptimizer) -> None:
        dashboard = optimizer.subscription_dashboard()
        assert "SUBSCRIPTION PORTFOLIO" in dashboard
        assert "n8n" in dashboard
        assert "Claude Code" in dashboard

    def test_optimization_dashboard_format(self, optimizer: ResourceOptimizer) -> None:
        dashboard = optimizer.optimization_dashboard()
        assert "WORKLOAD OPTIMIZATION" in dashboard
        assert "rog" in dashboard


# ===========================================================================
# Fleet Commander Tests (integration)
# ===========================================================================

class TestFleetCommander:
    def test_initialize(self, commander: FleetCommander) -> None:
        assert len(commander.registry.all_nodes()) == 3
        assert len(commander.displays.all_displays()) == 4
        assert len(commander.resources.all_subscriptions()) == 8

    def test_cmd_fleet(self, commander: FleetCommander) -> None:
        output = commander.cmd_fleet()
        assert "FLEET COMMAND CENTER" in output

    def test_cmd_displays(self, commander: FleetCommander) -> None:
        output = commander.cmd_displays()
        assert "Samsung 49" in output
        assert "Alienware" in output

    def test_cmd_resources(self, commander: FleetCommander) -> None:
        output = commander.cmd_resources()
        assert "WORKLOAD OPTIMIZATION" in output

    def test_cmd_subscriptions(self, commander: FleetCommander) -> None:
        output = commander.cmd_subscriptions()
        assert "SUBSCRIPTION PORTFOLIO" in output

    def test_cmd_backup(self, commander: FleetCommander) -> None:
        output = commander.cmd_backup()
        assert "BACKUP STRATEGY" in output

    def test_cmd_ssh_unknown_node(self, commander: FleetCommander) -> None:
        output = commander.cmd_ssh("nonexistent", "echo hi")
        assert "Return code: -1" in output

    def test_cmd_full_status(self, commander: FleetCommander) -> None:
        output = commander.cmd_full_status()
        assert "FLEET COMMAND CENTER" in output
        assert "SUBSCRIPTION PORTFOLIO" in output
