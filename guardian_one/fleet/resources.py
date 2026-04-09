"""Resource Optimizer — RAM/CPU balancing, subscription mapping, and backup strategy.

Responsibilities:
- Track total fleet resources and per-node utilization
- Map subscriptions/tools to optimal nodes
- Define backup strategy across the fleet
- Recommend workload redistribution when nodes are overloaded
- Manage the subscription portfolio for cost efficiency

Subscription portfolio (active):
    Docker AI        → A (ROG) primary, B (MacBook) secondary
    ChatGPT          → A (ROG) desktop app, available on all via web
    Codex (OpenAI)   → A (ROG) primary
    Claude Code      → A (ROG) + B (MacBook) via CLI
    Zapier           → C (Mac Mini) webhook listener, A for config
    Notion           → All nodes (write-only sync from C)
    n8n              → C (Mac Mini) always-on Docker container
    Visual Studio Code → A (ROG) + B (MacBook)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from guardian_one.fleet.nodes import FleetRegistry


class SubscriptionTier(Enum):
    FREE = "free"
    PRO = "pro"
    TEAM = "team"
    ENTERPRISE = "enterprise"


class ResourceCategory(Enum):
    AI_COMPUTE = "ai_compute"
    DEV_TOOLS = "dev_tools"
    AUTOMATION = "automation"
    PRODUCTIVITY = "productivity"
    SECURITY = "security"
    STORAGE = "storage"


@dataclass
class Subscription:
    """An active SaaS subscription in the portfolio."""
    name: str
    category: ResourceCategory
    tier: SubscriptionTier = SubscriptionTier.PRO
    monthly_cost_usd: float = 0.0
    assigned_nodes: list[str] = field(default_factory=list)  # node_ids
    primary_node: str = ""     # Main node that runs this
    docker_service: bool = False  # Runs as Docker container
    always_on: bool = False    # Needs 24/7 uptime (→ C)
    api_key_vault_id: str = "" # Vault credential key
    notes: str = ""


@dataclass
class BackupTarget:
    """A backup destination and schedule."""
    name: str
    target_path: str           # Local path or remote URI
    node_id: str               # Which node runs the backup
    schedule_cron: str = ""    # Cron expression
    retention_days: int = 30
    encrypted: bool = True
    includes: list[str] = field(default_factory=list)  # Paths/patterns to back up
    excludes: list[str] = field(default_factory=list)


@dataclass
class ResourceAllocation:
    """Recommended resource allocation for a workload."""
    workload: str
    recommended_node: str
    reason: str
    ram_estimate_gb: float = 0.0
    cpu_cores_needed: int = 0
    gpu_required: bool = False


class ResourceOptimizer:
    """Optimizes resource usage across Jeremy's fleet.

    Usage:
        opt = ResourceOptimizer(registry)
        opt.load_defaults()
        print(opt.subscription_dashboard())
        recs = opt.optimization_recommendations()
        backup_plan = opt.backup_plan()
    """

    def __init__(self, registry: FleetRegistry) -> None:
        self.registry = registry
        self._subscriptions: dict[str, Subscription] = {}
        self._backups: list[BackupTarget] = []

    def add_subscription(self, sub: Subscription) -> None:
        self._subscriptions[sub.name] = sub

    def all_subscriptions(self) -> list[Subscription]:
        return list(self._subscriptions.values())

    def subscriptions_by_node(self, node_id: str) -> list[Subscription]:
        return [s for s in self._subscriptions.values()
                if node_id in s.assigned_nodes or s.primary_node == node_id]

    def subscriptions_by_category(self, cat: ResourceCategory) -> list[Subscription]:
        return [s for s in self._subscriptions.values() if s.category == cat]

    def monthly_cost(self) -> float:
        return sum(s.monthly_cost_usd for s in self._subscriptions.values())

    def always_on_services(self) -> list[Subscription]:
        return [s for s in self._subscriptions.values() if s.always_on]

    # ------------------------------------------------------------------
    # Resource analysis
    # ------------------------------------------------------------------

    def fleet_resource_summary(self) -> dict[str, Any]:
        """Total fleet resources and per-node breakdown."""
        nodes = self.registry.all_nodes()
        total_ram = sum(n.hardware.ram_gb for n in nodes)
        total_cores = sum(n.hardware.cpu.cores for n in nodes)
        total_storage = sum(
            sum(s.total_gb for s in n.hardware.storage) for n in nodes
        )

        per_node = []
        for n in nodes:
            node_storage = sum(s.total_gb for s in n.hardware.storage)
            per_node.append({
                "id": n.node_id,
                "name": n.name,
                "role": n.role.value,
                "ram_gb": n.hardware.ram_gb,
                "cores": n.hardware.cpu.cores,
                "storage_gb": node_storage,
                "gpu": n.hardware.gpu.model if n.hardware.gpu else "none",
                "services": len(n.assigned_services),
                "load_pct": n.current_load_pct,
                "ram_used_pct": n.ram_used_pct,
            })

        return {
            "total_ram_gb": total_ram,
            "total_cores": total_cores,
            "total_storage_gb": total_storage,
            "nodes": per_node,
            "subscriptions": len(self._subscriptions),
            "monthly_cost_usd": self.monthly_cost(),
        }

    def optimization_recommendations(self) -> list[ResourceAllocation]:
        """Recommend optimal workload placement based on fleet capabilities."""
        recs: list[ResourceAllocation] = []

        # Heavy AI inference → A (64GB RAM + RTX 4060)
        recs.append(ResourceAllocation(
            workload="Ollama / Local LLM Inference",
            recommended_node="rog",
            reason="64GB RAM + RTX 4060 (8GB VRAM, 3072 CUDA cores). "
                   "Can run Llama 3 70B quantized or multiple smaller models.",
            ram_estimate_gb=32.0,
            gpu_required=True,
        ))

        # Docker AI workloads → A
        recs.append(ResourceAllocation(
            workload="Docker AI Containers (training, fine-tuning)",
            recommended_node="rog",
            reason="64GB RAM provides headroom for multiple containers. "
                   "GPU passthrough for CUDA workloads.",
            ram_estimate_gb=16.0,
            gpu_required=True,
        ))

        # Guardian One orchestrator → A
        recs.append(ResourceAllocation(
            workload="Guardian One (main orchestrator)",
            recommended_node="rog",
            reason="Primary controller needs full fleet visibility. "
                   "Runs agents, coordinates B and C.",
            ram_estimate_gb=2.0,
        ))

        # Always-on homelink → C (Mac Mini)
        recs.append(ResourceAllocation(
            workload="H.O.M.E. L.I.N.K. (gateway, monitor, vault)",
            recommended_node="mac-mini",
            reason="Always-on requirement. Mac Mini is stationary with Ethernet. "
                   "Low power draw, 16GB sufficient for gateway services.",
            ram_estimate_gb=4.0,
        ))

        # n8n automation → C
        recs.append(ResourceAllocation(
            workload="n8n Workflow Automation",
            recommended_node="mac-mini",
            reason="24/7 Docker container. Mac Mini always-on with Ethernet reliability.",
            ram_estimate_gb=2.0,
        ))

        # Zapier webhooks → C
        recs.append(ResourceAllocation(
            workload="Zapier Webhook Listener",
            recommended_node="mac-mini",
            reason="Needs constant uptime to receive webhooks. Mac Mini is always-on.",
            ram_estimate_gb=0.5,
        ))

        # Notion sync → C
        recs.append(ResourceAllocation(
            workload="Notion Dashboard Sync (periodic)",
            recommended_node="mac-mini",
            reason="Scheduled sync runs every 15min. Mac Mini handles background tasks.",
            ram_estimate_gb=0.5,
        ))

        # Backup agent → C
        recs.append(ResourceAllocation(
            workload="Automated Backups (fleet-wide)",
            recommended_node="mac-mini",
            reason="Always-on for scheduled backups. Can pull from A and B via SSH.",
            ram_estimate_gb=1.0,
        ))

        # Dev environment → B (MacBook Pro)
        recs.append(ResourceAllocation(
            workload="Xcode / iOS Development",
            recommended_node="macbook-pro",
            reason="Native Apple Silicon for Xcode. M3 Pro handles builds well.",
            ram_estimate_gb=8.0,
            cpu_cores_needed=6,
        ))

        # Claude Code (secondary) → B
        recs.append(ResourceAllocation(
            workload="Claude Code CLI (secondary)",
            recommended_node="macbook-pro",
            reason="Side-by-side with A on ultrawide. Code on B, test on A.",
            ram_estimate_gb=2.0,
        ))

        # ChatGPT → A (desktop app)
        recs.append(ResourceAllocation(
            workload="ChatGPT Desktop App",
            recommended_node="rog",
            reason="Desktop app on Windows. Web fallback available on all nodes.",
            ram_estimate_gb=1.0,
        ))

        # Codex → A
        recs.append(ResourceAllocation(
            workload="OpenAI Codex",
            recommended_node="rog",
            reason="Paired with Claude Code on A for AI-assisted development.",
            ram_estimate_gb=1.0,
        ))

        return recs

    # ------------------------------------------------------------------
    # Backup strategy
    # ------------------------------------------------------------------

    def backup_plan(self) -> list[BackupTarget]:
        """Define the fleet-wide backup strategy."""
        if self._backups:
            return self._backups

        backups = [
            # C backs up A's Guardian One data nightly
            BackupTarget(
                name="guardian-one-data",
                target_path="/Volumes/Backup/guardian-one/",
                node_id="mac-mini",
                schedule_cron="0 3 * * *",  # 3 AM daily
                retention_days=90,
                includes=["~/JT/data/", "~/JT/config/", "~/JT/logs/"],
                excludes=["*.pyc", "__pycache__", ".git/"],
            ),
            # C backs up its own Docker volumes
            BackupTarget(
                name="docker-volumes",
                target_path="/Volumes/Backup/docker/",
                node_id="mac-mini",
                schedule_cron="0 4 * * *",  # 4 AM daily
                retention_days=30,
                includes=["docker volumes"],
            ),
            # Git repo sync (all nodes push to GitHub)
            BackupTarget(
                name="git-repo-sync",
                target_path="github:curiouscat777/jt",
                node_id="rog",
                schedule_cron="*/30 * * * *",  # Every 30 min
                retention_days=0,  # Git handles history
                includes=["~/JT/"],
            ),
            # B backs up Xcode projects to external
            BackupTarget(
                name="xcode-projects",
                target_path="/Volumes/Backup/xcode/",
                node_id="macbook-pro",
                schedule_cron="0 2 * * 0",  # Weekly Sunday 2 AM
                retention_days=60,
                includes=["~/Developer/"],
                excludes=["DerivedData/", "build/"],
            ),
        ]

        self._backups = backups
        return backups

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def subscription_dashboard(self) -> str:
        """Formatted subscription portfolio dashboard."""
        subs = sorted(self.all_subscriptions(), key=lambda s: s.category.value)
        lines = [
            "=" * 70,
            "  SUBSCRIPTION PORTFOLIO — RESOURCE OPTIMIZER",
            "=" * 70,
            f"  Active subscriptions: {len(subs)}",
            f"  Monthly cost: ${self.monthly_cost():.2f}",
            "",
            f"  {'Service':<22} {'Category':<16} {'Primary Node':<16} {'Always-On':>9}",
            "  " + "-" * 65,
        ]

        for s in subs:
            always = "YES" if s.always_on else ""
            lines.append(
                f"  {s.name:<22} {s.category.value:<16} {s.primary_node:<16} {always:>9}"
            )

        lines.append("  " + "-" * 65)
        lines.append("")

        # Always-on services summary
        ao = self.always_on_services()
        if ao:
            lines.append(f"  Always-on services ({len(ao)}) → Mac Mini (daemon):")
            for s in ao:
                lines.append(f"    - {s.name}")

        lines.append("")
        lines.append("=" * 70)
        return "\n".join(lines)

    def optimization_dashboard(self) -> str:
        """Formatted optimization recommendations."""
        recs = self.optimization_recommendations()
        lines = [
            "=" * 70,
            "  WORKLOAD OPTIMIZATION — FLEET RESOURCE PLANNER",
            "=" * 70,
            "",
        ]

        by_node: dict[str, list[ResourceAllocation]] = {}
        for r in recs:
            by_node.setdefault(r.recommended_node, []).append(r)

        for node_id, allocs in by_node.items():
            node = self.registry.get(node_id)
            name = node.name if node else node_id
            ram = node.hardware.ram_gb if node else 0
            total_est = sum(a.ram_estimate_gb for a in allocs)

            lines.append(f"  {name} ({node_id}) — {ram}GB RAM")
            lines.append(f"  Estimated workload: {total_est:.1f}GB / {ram}GB ({total_est/ram*100:.0f}%)" if ram else "")
            lines.append("  " + "-" * 60)

            for a in allocs:
                gpu_tag = " [GPU]" if a.gpu_required else ""
                lines.append(f"    {a.workload}{gpu_tag} — ~{a.ram_estimate_gb:.1f}GB")
                lines.append(f"      {a.reason[:80]}")

            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Load defaults
    # ------------------------------------------------------------------

    def load_defaults(self) -> None:
        """Load Jeremy's active subscription portfolio."""
        for sub in _jeremys_subscriptions():
            self.add_subscription(sub)


def _jeremys_subscriptions() -> list[Subscription]:
    """Jeremy's active SaaS subscriptions mapped to fleet nodes."""
    return [
        Subscription(
            name="Docker AI",
            category=ResourceCategory.AI_COMPUTE,
            tier=SubscriptionTier.PRO,
            assigned_nodes=["rog", "macbook-pro"],
            primary_node="rog",
            docker_service=True,
            notes="Docker Desktop on A and B. Docker daemon on C.",
        ),
        Subscription(
            name="ChatGPT",
            category=ResourceCategory.AI_COMPUTE,
            tier=SubscriptionTier.PRO,
            assigned_nodes=["rog"],
            primary_node="rog",
            notes="Desktop app on ROG. Web on all nodes.",
        ),
        Subscription(
            name="Codex (OpenAI)",
            category=ResourceCategory.AI_COMPUTE,
            tier=SubscriptionTier.PRO,
            assigned_nodes=["rog"],
            primary_node="rog",
            notes="AI coding assistant paired with Claude Code.",
        ),
        Subscription(
            name="Claude Code",
            category=ResourceCategory.AI_COMPUTE,
            tier=SubscriptionTier.PRO,
            assigned_nodes=["rog", "macbook-pro"],
            primary_node="rog",
            notes="CLI on both workstations. Primary dev on A.",
        ),
        Subscription(
            name="Zapier",
            category=ResourceCategory.AUTOMATION,
            tier=SubscriptionTier.PRO,
            assigned_nodes=["mac-mini", "rog"],
            primary_node="mac-mini",
            always_on=True,
            notes="Webhook listener on C (always-on). Config from A.",
        ),
        Subscription(
            name="Notion",
            category=ResourceCategory.PRODUCTIVITY,
            tier=SubscriptionTier.PRO,
            assigned_nodes=["rog", "macbook-pro", "mac-mini"],
            primary_node="mac-mini",
            always_on=True,
            notes="Write-only sync from C. Desktop apps on A and B.",
        ),
        Subscription(
            name="n8n",
            category=ResourceCategory.AUTOMATION,
            tier=SubscriptionTier.FREE,
            assigned_nodes=["mac-mini"],
            primary_node="mac-mini",
            docker_service=True,
            always_on=True,
            notes="Self-hosted Docker on C. 24/7 workflow automation.",
        ),
        Subscription(
            name="Visual Studio Code",
            category=ResourceCategory.DEV_TOOLS,
            tier=SubscriptionTier.FREE,
            assigned_nodes=["rog", "macbook-pro"],
            primary_node="rog",
            notes="IDE on both workstations. Extensions synced via Settings Sync.",
        ),
    ]
