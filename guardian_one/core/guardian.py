"""Guardian One — the sovereign coordinator.

Responsibilities:
- Boot and supervise all subordinate agents
- Enforce security policies
- Mediate cross-agent conflicts
- Produce daily summaries for Jeremy
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from guardian_one.core.ai_engine import AIConfig, AIEngine, AIProvider
from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig, GuardianConfig, load_config
from guardian_one.core.mediator import Mediator
from guardian_one.core.security import (
    AccessController,
    AccessLevel,
    AccessPolicy,
    SecretStore,
)
from guardian_one.core.vop import VOPEngine
from guardian_one.homelink.gateway import Gateway, ServiceConfig, RateLimitConfig
from guardian_one.homelink.vault import Vault
from guardian_one.homelink.registry import IntegrationRegistry
from guardian_one.integrations.n8n_sync import GatewayN8nProvider
from guardian_one.homelink.monitor import Monitor
from guardian_one.utils.power_tools_library import PowerToolsLibrary


class GuardianOne:
    """Central coordinator for the multi-agent system.

    Manages the lifecycle of all registered agents, enforces access control,
    and produces consolidated reports.
    """

    def __init__(
        self,
        config: GuardianConfig | None = None,
        vault_passphrase: str | None = None,
        ai_config: AIConfig | None = None,
    ) -> None:
        self.config = config or load_config()
        self.audit = AuditLog(log_dir=Path(self.config.log_dir))
        self.mediator = Mediator(audit=self.audit)
        self.access = AccessController()
        self._agents: dict[str, BaseAgent] = {}

        # AI Engine — the sovereign brain
        self.ai_engine = AIEngine(ai_config or self._load_ai_config())

        # VOP v2.1 — ORaCLE arbiter (verification operating protocol)
        self.vop = VOPEngine(audit=self.audit, fail_closed=True)

        # H.O.M.E. L.I.N.K. subsystems
        self.gateway = Gateway(audit=self.audit)
        passphrase = vault_passphrase or os.environ.get(
            "GUARDIAN_MASTER_PASSPHRASE", ""
        )
        if not passphrase:
            raise RuntimeError(
                "Vault passphrase required: set GUARDIAN_MASTER_PASSPHRASE env var "
                "or pass vault_passphrase to GuardianOne()"
            )
        vault_path = Path(self.config.data_dir) / "vault.enc"
        self.vault = Vault(vault_path, passphrase=passphrase)
        self.registry = IntegrationRegistry()
        self.registry.load_defaults()
        self.monitor = Monitor(
            gateway=self.gateway,
            vault=self.vault,
            registry=self.registry,
        )

        # Power Tools Library — managed by Archivist, available to agents
        self.power_tools = PowerToolsLibrary(
            audit=self.audit, data_dir=self.config.data_dir,
        )

        # Register default access policies
        self._setup_access_policies()

        # Register gateway services for known integrations
        self._setup_gateway_services()

        # Auto-load Notion token from .env into Vault if present and not yet stored
        self._seed_vault_from_env()

        # Notion sync — first-class service (write-only workspace push)
        root_page_id = os.environ.get("NOTION_ROOT_PAGE_ID", "")
        self.notion_sync: NotionSync | None = None
        if root_page_id:
            self.notion_sync = NotionSync(
                gateway=self.gateway,
                vault=self.vault,
                audit=self.audit,
                root_page_id=root_page_id,
            )

        # n8n provider — routes through Gateway for TLS/rate-limit/audit
        self.n8n_provider = GatewayN8nProvider(
            gateway=self.gateway, agent="web_architect",
        )

        # Log AI engine status at boot
        ai_status = self.ai_engine.status()
        self.audit.record(
            agent="guardian_one",
            action="system_boot",
            severity=Severity.INFO,
            details={
                "owner": self.config.owner,
                "homelink": "active",
                "ai_engine": ai_status["active_provider"] or "offline",
                "ai_ollama": ai_status["ollama"]["available"],
                "ai_anthropic": ai_status["anthropic"]["available"],
                "notion_configured": self.notion_sync is not None,
                "n8n_registered": self.n8n_provider.has_credentials,
            },
        )

    # ------------------------------------------------------------------
    # AI configuration
    # ------------------------------------------------------------------

    def _load_ai_config(self) -> AIConfig:
        """Load AI engine config from guardian_config.yaml or defaults."""
        # Try to load from the raw YAML config
        config_path = Path("config/guardian_config.yaml")
        ai_raw: dict[str, Any] = {}
        if config_path.exists():
            import yaml
            with open(config_path) as f:
                raw = yaml.safe_load(f) or {}
            ai_raw = raw.get("ai_engine", {})

        provider_map = {"ollama": AIProvider.OLLAMA, "anthropic": AIProvider.ANTHROPIC}

        return AIConfig(
            primary_provider=provider_map.get(
                ai_raw.get("primary_provider", "ollama"), AIProvider.OLLAMA
            ),
            fallback_provider=provider_map.get(
                ai_raw.get("fallback_provider", "anthropic"), AIProvider.ANTHROPIC
            ),
            ollama_base_url=ai_raw.get("ollama_base_url", "http://localhost:11434"),
            ollama_model=ai_raw.get("ollama_model", "llama3"),
            anthropic_model=ai_raw.get(
                "anthropic_model", "claude-sonnet-4-20250514"
            ),
            max_tokens=ai_raw.get("max_tokens", 2048),
            temperature=ai_raw.get("temperature", 0.3),
            timeout_seconds=ai_raw.get("timeout_seconds", 60),
            enable_memory=ai_raw.get("enable_memory", True),
            max_memory_messages=ai_raw.get("max_memory_messages", 50),
        )

    # ------------------------------------------------------------------
    # Access control setup
    # ------------------------------------------------------------------

    def _setup_access_policies(self) -> None:
        self.access.register(AccessPolicy(
            identity="jeremy",
            level=AccessLevel.OWNER,
        ))
        self.access.register(AccessPolicy(
            identity="guardian_one",
            level=AccessLevel.GUARDIAN,
        ))
        self.access.register(AccessPolicy(
            identity="mentor",
            level=AccessLevel.MENTOR,
            allowed_resources=["audit_log", "reports", "config_readonly"],
        ))

    def _seed_vault_from_env(self) -> None:
        """Auto-load API tokens from environment into Vault if not already stored.

        This bridges the gap between .env configuration and the encrypted Vault,
        so users don't have to manually store tokens via the Vault API.
        """
        env_to_vault = [
            ("NOTION_TOKEN", "notion", "write"),
            ("OLLAMA_API_KEY", "ollama", "read"),
        ]
        for env_key, service, scope in env_to_vault:
            value = os.environ.get(env_key, "")
            if value and not self.vault.retrieve(env_key):
                self.vault.store(env_key, value, service=service, scope=scope)
                self.audit.record(
                    agent="guardian_one",
                    action=f"vault_seed:{env_key}",
                    severity=Severity.INFO,
                    details={"source": ".env", "service": service},
                )

    def _setup_gateway_services(self) -> None:
        """Register external services in the gateway from the integration registry."""
        for record in self.registry.active():
            if record.base_url and record.base_url != "local_cli":
                self.gateway.register_service(ServiceConfig(
                    name=record.name,
                    base_url=record.base_url,
                    rate_limit=RateLimitConfig(max_requests=60, window_seconds=60),
                    allowed_agents=(
                        [record.owner_agent] + getattr(record, "additional_agents", [])
                        if record.owner_agent else []
                    ),
                ))

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    def register_agent(self, agent: BaseAgent) -> None:
        """Register and initialize a subordinate agent."""
        name = agent.name
        if name in self._agents:
            raise ValueError(f"Agent '{name}' is already registered.")

        # Create an access policy scoped to this agent's config
        policy = AccessPolicy(
            identity=name,
            level=AccessLevel.AGENT,
            allowed_resources=agent.config.allowed_resources,
        )
        self.access.register(policy)

        # Inject AI engine into the agent
        agent.set_ai_engine(self.ai_engine)

        # Inject VOP engine into the agent (ORaCLE verification)
        agent.set_vop_engine(self.vop)

        # Inject Power Tools Library if the agent has access
        if "power_tools" in agent.config.allowed_resources:
            if hasattr(agent, "set_power_tools"):
                agent.set_power_tools(self.power_tools)
            else:
                # Generic injection via attribute
                agent._power_tools = self.power_tools

        self._agents[name] = agent
        self.audit.record(
            agent="guardian_one",
            action=f"agent_registered:{name}",
            severity=Severity.INFO,
            details={"ai_enabled": agent.ai_enabled},
        )

        agent.initialize()
        self.audit.record(
            agent="guardian_one",
            action=f"agent_initialized:{name}",
            severity=Severity.INFO,
        )

    def run_agent(self, name: str) -> AgentReport:
        """Execute a single agent's run cycle."""
        agent = self._agents.get(name)
        if agent is None:
            raise KeyError(f"No agent named '{name}'.")
        if not agent.config.enabled:
            return AgentReport(
                agent_name=name,
                status=AgentStatus.DISABLED.value,
                summary=f"{name} is disabled in configuration.",
            )

        self.audit.record(
            agent="guardian_one",
            action=f"run_start:{name}",
        )
        try:
            report = agent.run()
            self.audit.record(
                agent="guardian_one",
                action=f"run_complete:{name}",
                details={"status": report.status},
            )
            return report
        except Exception as exc:
            self.audit.record(
                agent="guardian_one",
                action=f"run_error:{name}",
                severity=Severity.ERROR,
                details={"error": str(exc)},
                requires_review=True,
            )
            return AgentReport(
                agent_name=name,
                status=AgentStatus.ERROR.value,
                summary=f"Error: {exc}",
            )

    def run_all(self) -> list[AgentReport]:
        """Run every registered and enabled agent, then check for conflicts."""
        reports: list[AgentReport] = []
        for name in self._agents:
            reports.append(self.run_agent(name))

        conflicts = self.mediator.check_conflicts()
        if conflicts:
            self.audit.record(
                agent="guardian_one",
                action=f"conflicts_detected:{len(conflicts)}",
                severity=Severity.WARNING,
                requires_review=True,
            )
        self.mediator.clear_pending()
        return reports

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def daily_summary(self) -> str:
        """Produce a daily summary for Jeremy."""
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            f"=== Guardian One Daily Summary — {now} ===",
            f"Owner: {self.config.owner}",
            f"Registered agents: {', '.join(self._agents.keys()) or 'none'}",
            "",
        ]

        for name, agent in self._agents.items():
            try:
                report = agent.report()
                lines.append(f"--- {name} ---")
                lines.append(f"  Status: {report.status}")
                lines.append(f"  Summary: {report.summary}")
                if report.alerts:
                    for alert in report.alerts:
                        lines.append(f"  [ALERT] {alert}")
                if report.recommendations:
                    for rec in report.recommendations:
                        lines.append(f"  [REC] {rec}")
                lines.append("")
            except Exception as exc:
                lines.append(f"--- {name} ---")
                lines.append(f"  Error generating report: {exc}")
                lines.append("")

        # H.O.M.E. L.I.N.K. status
        lines.append("--- H.O.M.E. L.I.N.K. ---")
        services = self.gateway.list_services()
        if services:
            for svc in services:
                status = self.gateway.service_status(svc)
                health = self.monitor.assess_service(svc)
                lines.append(
                    f"  {svc}: circuit={status['circuit_state']} "
                    f"risk={health.risk_score}/5"
                )
        else:
            lines.append("  No external services registered.")
        vault_health = self.vault.health_report()
        lines.append(f"  Vault: {vault_health['total_credentials']} credentials")
        rotation_due = vault_health["due_for_rotation"]
        if rotation_due:
            lines.append(f"  ** {rotation_due} credentials due for rotation **")
        lines.append("")

        # AI Engine status
        lines.append("--- AI Engine ---")
        ai_info = self.ai_engine.status()
        active = ai_info["active_provider"] or "OFFLINE"
        lines.append(f"  Active provider: {active}")
        lines.append(f"  Ollama: {'available' if ai_info['ollama']['available'] else 'not available'} ({ai_info['ollama']['model']})")
        lines.append(f"  Anthropic: {'available' if ai_info['anthropic']['available'] else 'not available'}")
        lines.append(f"  Total AI requests: {ai_info['total_requests']}")
        lines.append(f"  Agents with memory: {', '.join(ai_info['agents_with_memory']) or 'none'}")
        lines.append("")

        # VOP v2.1 — ORaCLE status
        lines.append("--- VOP v2.1 (ORaCLE) ---")
        vop_info = self.vop.status()
        lines.append(f"  Protocol: {vop_info['protocol']}")
        lines.append(f"  Fail-closed: {vop_info['fail_closed']}")
        lines.append(f"  Verifiers: {', '.join(vop_info['verifiers']) or 'none'}")
        stats = vop_info["stats"]
        lines.append(f"  Claims processed: {stats['total_processed']}")
        lines.append(f"  Verification rate: {stats['verification_rate']}%")
        lines.append(f"  Blocked: {stats['total_blocked']}")
        if vop_info["consecutive_failures"] >= 2:
            lines.append(f"  ** {vop_info['consecutive_failures']} consecutive failures — approaching escalation **")
        lines.append("")

        # Pending reviews
        pending = self.audit.pending_reviews()
        if pending:
            lines.append(f"** {len(pending)} items need your review **")
            for entry in pending[:5]:
                lines.append(f"  - [{entry.agent}] {entry.action}")

        lines.append("\n" + self.audit.summary(last_n=10))
        return "\n".join(lines)

    def ai_status(self) -> dict[str, Any]:
        """Get AI engine status."""
        return self.ai_engine.status()

    def think(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Ask the AI engine a question as the Guardian coordinator.

        This is the top-level AI interface for the system itself.
        """
        response = self.ai_engine.reason(
            agent_name="guardian_one",
            prompt=prompt,
            system=(
                "You are Guardian One, the sovereign AI coordinator for "
                "Jeremy Paulo Salvino Tabernero's personal life management system. "
                "You oversee all subordinate agents (CFO, Chronos, Archivist, etc.). "
                "Provide high-level strategic reasoning, conflict resolution, "
                "and daily summaries. Be direct, concise, and proactive."
            ),
            context=context,
        )
        return response.content

    # ------------------------------------------------------------------
    # VOP v2.1 — Verification Operating Protocol
    # ------------------------------------------------------------------

    def verify_claims(self, claims: list) -> Any:
        """Run claims through the VOP verification pipeline.

        Args:
            claims: List of Claim objects to verify.

        Returns:
            VOPResult with verified/blocked claims.
        """
        return self.vop.process(claims)

    def vop_status(self) -> dict[str, Any]:
        """Get VOP engine status."""
        return self.vop.status()

    # ------------------------------------------------------------------
    # Notion + n8n integration
    # ------------------------------------------------------------------

    def sync_to_notion(
        self,
        roadmap_phases: list[dict[str, Any]] | None = None,
        deliverables: list[dict[str, Any]] | None = None,
        decisions: list[dict[str, Any]] | None = None,
    ) -> SyncResult | None:
        """Run a full Notion workspace sync using live agent/service data.

        Returns None if Notion is not configured.
        """
        if not self.notion_sync:
            return None

        agents_data = []
        for name in self.list_agents():
            agent = self.get_agent(name)
            if agent:
                try:
                    report = agent.report()
                    agents_data.append({
                        "name": name,
                        "status": report.status,
                        "health_score": 90 if report.status == "idle" else 70,
                        "schedule_interval": agent.config.schedule_interval_minutes,
                        "last_run": getattr(report, "last_run", "never"),
                        "allowed_resources": agent.config.allowed_resources,
                    })
                except Exception:
                    agents_data.append({
                        "name": name,
                        "status": "unknown",
                        "health_score": 50,
                        "schedule_interval": 0,
                        "last_run": "never",
                        "allowed_resources": [],
                    })

        services_data = []
        for svc_name in self.gateway.list_services():
            status = self.gateway.service_status(svc_name)
            health = self.monitor.assess_service(svc_name)
            services_data.append({
                "name": svc_name,
                "circuit_state": status.get("circuit_state", "unknown"),
                "success_rate": status.get("success_rate", 0),
                "avg_latency_ms": status.get("avg_latency_ms", 0),
                "risk_score": health.risk_score,
            })

        return self.notion_sync.full_sync(
            agents=agents_data,
            roadmap_phases=roadmap_phases or [],
            services=services_data,
            deliverables=deliverables or [],
            decisions=decisions,
        )

    def sync_n8n_to_notion(self) -> SyncResult | None:
        """Push n8n workflow status to Notion dashboard.

        Returns None if Notion is not configured.
        """
        if not self.notion_sync:
            return None

        from guardian_one.integrations.notion_n8n_sync import NotionN8nSync

        n8n_sync = NotionN8nSync(self.notion_sync, self.audit)

        # Collect workflows from the provider
        workflows = []
        n8n_connected = False
        if self.n8n_provider.has_credentials:
            n8n_connected = self.n8n_provider.authenticate()
            if n8n_connected:
                workflows = self.n8n_provider.list_workflows()

        # Also include any local workflows from WebArchitect if registered
        web_architect = self.get_agent("web_architect")
        if web_architect and hasattr(web_architect, "list_workflows"):
            local_wfs = web_architect.list_workflows()
            local_ids = {w.id for w in workflows}
            for wf_id, wf in local_wfs.items():
                if wf_id not in local_ids:
                    workflows.append(wf)

        return n8n_sync.push_workflow_dashboard(
            workflows=workflows,
            n8n_connected=n8n_connected,
        )

    def get_agent(self, name: str) -> BaseAgent | None:
        return self._agents.get(name)

    def list_agents(self) -> list[str]:
        return list(self._agents.keys())

    def shutdown(self) -> None:
        """Gracefully shut down all agents."""
        for name, agent in self._agents.items():
            try:
                agent.shutdown()
            except Exception as exc:
                self.audit.record(
                    agent="guardian_one",
                    action=f"shutdown_error:{name}",
                    severity=Severity.ERROR,
                    details={"error": str(exc)},
                )
        self.audit.record(
            agent="guardian_one",
            action="system_shutdown",
            severity=Severity.INFO,
        )
