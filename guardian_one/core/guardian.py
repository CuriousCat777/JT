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
from guardian_one.homelink.gateway import Gateway, ServiceConfig, RateLimitConfig
from guardian_one.homelink.vault import Vault
from guardian_one.homelink.registry import IntegrationRegistry
from guardian_one.homelink.monitor import Monitor


class GuardianOne:
    """Central coordinator for the multi-agent system.

    Manages the lifecycle of all registered agents, enforces access control,
    and produces consolidated reports.
    """

    def __init__(
        self,
        config: GuardianConfig | None = None,
        vault_passphrase: str | None = None,
    ) -> None:
        self.config = config or load_config()
        self.audit = AuditLog(log_dir=Path(self.config.log_dir))
        self.mediator = Mediator(audit=self.audit)
        self.access = AccessController()
        self._agents: dict[str, BaseAgent] = {}

        # H.O.M.E. L.I.N.K. subsystems
        self.gateway = Gateway(audit=self.audit)
        passphrase = vault_passphrase or os.environ.get(
            "GUARDIAN_MASTER_PASSPHRASE", "guardian-one-default-dev-passphrase"
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

        # Register default access policies
        self._setup_access_policies()

        # Register gateway services for known integrations
        self._setup_gateway_services()

        # Auto-load Notion token from .env into Vault if present and not yet stored
        self._seed_vault_from_env()

        self.audit.record(
            agent="guardian_one",
            action="system_boot",
            severity=Severity.INFO,
            details={"owner": self.config.owner, "homelink": "active"},
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
                    allowed_agents=[record.owner_agent] if record.owner_agent else [],
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

        self._agents[name] = agent
        self.audit.record(
            agent="guardian_one",
            action=f"agent_registered:{name}",
            severity=Severity.INFO,
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

        # Pending reviews
        pending = self.audit.pending_reviews()
        if pending:
            lines.append(f"** {len(pending)} items need your review **")
            for entry in pending[:5]:
                lines.append(f"  - [{entry.agent}] {entry.action}")

        lines.append("\n" + self.audit.summary(last_n=10))
        return "\n".join(lines)

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
