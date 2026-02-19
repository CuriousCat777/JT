"""Agent Template — blueprint for creating new subordinate agents.

Use this template when adding one of the planned ~15 future agents.
Copy this file, rename the class, and implement the three required methods:
    initialize(), run(), report()

Every new agent automatically inherits:
- Audit logging (self.log)
- Status management (self._set_status)
- Configuration via AgentConfig
- Access control via Guardian One's AccessController

Checklist for new agents:
  [ ] Copy this file to guardian_one/agents/<your_agent>.py
  [ ] Rename the class and update __init__
  [ ] Implement initialize() — connect to APIs, load state
  [ ] Implement run() — core logic, return AgentReport
  [ ] Implement report() — read-only status snapshot
  [ ] Register in config/guardian_config.yaml
  [ ] Add integration module in guardian_one/integrations/ if needed
  [ ] Write tests in tests/test_<your_agent>.py
  [ ] Register in main.py's _build_agents()
"""

from __future__ import annotations

from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig


class TemplateAgent(BaseAgent):
    """Copy and customise this class for each new agent.

    Replace 'TemplateAgent' with your agent's name (e.g., HealthAgent).
    """

    def __init__(self, config: AgentConfig, audit: AuditLog) -> None:
        super().__init__(config, audit)
        # Add your agent-specific state here
        self._state: dict[str, Any] = {}

    def initialize(self) -> None:
        """One-time setup.

        Examples:
        - Connect to external APIs
        - Load persisted state from disk
        - Validate required configuration keys
        """
        self._set_status(AgentStatus.IDLE)
        self.log("initialized")

    def run(self) -> AgentReport:
        """Execute the agent's primary duties.

        This is called periodically by Guardian One.
        Return an AgentReport summarising what happened.
        """
        self._set_status(AgentStatus.RUNNING)
        alerts: list[str] = []
        recommendations: list[str] = []
        actions: list[str] = []

        # --- Your logic here ---
        actions.append("Template agent ran successfully.")

        self._set_status(AgentStatus.IDLE)
        return AgentReport(
            agent_name=self.name,
            status=AgentStatus.IDLE.value,
            summary="Template agent completed its cycle.",
            actions_taken=actions,
            recommendations=recommendations,
            alerts=alerts,
            data=self._state,
        )

    def report(self) -> AgentReport:
        """Return a read-only snapshot of current state."""
        return AgentReport(
            agent_name=self.name,
            status=self.status.value,
            summary="Template agent status.",
            data=self._state,
        )
