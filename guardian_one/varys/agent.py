"""VARYS Guardian One agent — integrates VARYS into the agent scheduler.

Extends BaseAgent so VARYS runs alongside Chronos, CFO, Archivist, etc.
Each scheduler cycle triggers a VARYS detection cycle.
"""

from __future__ import annotations

from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig
from guardian_one.varys.engine import VarysEngine
from guardian_one.varys.ingestion.collector import AuthLogCollector, SyslogCollector


class VarysAgent(BaseAgent):
    """VARYS cybersecurity sentinel — runs as a Guardian One agent."""

    def __init__(self, config: AgentConfig, audit: AuditLog) -> None:
        super().__init__(config, audit)
        self._engine: VarysEngine | None = None
        self._last_alerts: list[dict[str, Any]] = []
        self._cycle_count: int = 0

    @property
    def engine(self) -> VarysEngine | None:
        return self._engine

    def initialize(self) -> None:
        """Set up VARYS engine with default collectors."""
        varys_config = self.config.custom or {}

        self._engine = VarysEngine(
            dry_run=varys_config.get("dry_run", True),
            z_threshold=varys_config.get("z_threshold", 3.0),
        )

        # Register log collectors based on config
        if varys_config.get("auth_log", True):
            log_path = varys_config.get("auth_log_path", "/var/log/auth.log")
            self._engine.add_collector(AuthLogCollector(log_path=log_path))

        if varys_config.get("syslog", True):
            log_path = varys_config.get("syslog_path", "/var/log/syslog")
            self._engine.add_collector(SyslogCollector(log_path=log_path))

        # Inject AI engine if available
        if self._ai is not None:
            self._engine.set_ai_engine(self._ai)

        self.log("varys_initialized", details={
            "collectors": len(self._engine._collectors),
            "rules": len(self._engine.sigma.rules),
            "dry_run": self._engine.response._dry_run,
        })
        self._set_status(AgentStatus.IDLE)

    def run(self) -> AgentReport:
        """Execute one VARYS detection cycle."""
        self._set_status(AgentStatus.RUNNING)

        if self._engine is None:
            self.initialize()

        try:
            alerts = self._engine.cycle()
            self._cycle_count += 1
            self._last_alerts = [a.to_dict() for a in alerts]

            # Log significant alerts
            for alert in alerts:
                severity_map = {
                    "critical": Severity.CRITICAL,
                    "high": Severity.WARNING,
                    "medium": Severity.INFO,
                    "low": Severity.INFO,
                }
                self.log(
                    f"alert:{alert.rule_id}",
                    severity=severity_map.get(alert.severity.value, Severity.INFO),
                    details=alert.to_dict(),
                    requires_review=alert.severity.value in ("critical", "high"),
                )

            # Build report
            status = self._engine.status()
            actions_taken = []
            recommendations = []
            alert_summaries = []

            for alert in alerts:
                alert_summaries.append(
                    f"[{alert.severity.value.upper()}] {alert.title}"
                )

            if status["response"]["pending_actions"] > 0:
                recommendations.append(
                    f"{status['response']['pending_actions']} response actions pending approval"
                )

            high_risk = self._engine.scorer.get_high_risk_entities()
            if high_risk:
                recommendations.append(
                    f"{len(high_risk)} high-risk entities detected"
                )

            self._set_status(AgentStatus.IDLE)
            return AgentReport(
                agent_name=self.name,
                status="ok" if not alerts else "alert",
                summary=(
                    f"VARYS cycle #{self._cycle_count}: "
                    f"{status['total_events']} events processed, "
                    f"{len(alerts)} alerts generated"
                ),
                actions_taken=actions_taken,
                recommendations=recommendations,
                alerts=alert_summaries,
                data=status,
            )

        except Exception as exc:
            self._set_status(AgentStatus.ERROR)
            self.log("varys_error", severity=Severity.ERROR, details={"error": str(exc)})
            return AgentReport(
                agent_name=self.name,
                status="error",
                summary=f"VARYS cycle failed: {exc}",
                alerts=[str(exc)],
            )

    def report(self) -> AgentReport:
        """Return current VARYS status without side effects."""
        if self._engine is None:
            return AgentReport(
                agent_name=self.name,
                status="not_initialized",
                summary="VARYS engine not yet initialized",
            )

        status = self._engine.status()
        return AgentReport(
            agent_name=self.name,
            status="ok",
            summary=(
                f"VARYS: {status['total_events']} events, "
                f"{status['total_alerts']} alerts, "
                f"{status['detection']['rules_loaded']} rules loaded"
            ),
            data=status,
        )

    def shutdown(self) -> None:
        """Stop the VARYS engine."""
        if self._engine:
            self._engine.stop()
        super().shutdown()
