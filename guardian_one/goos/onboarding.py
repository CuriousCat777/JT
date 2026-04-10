"""GOOS Onboarding — guided flow to introduce clients to Guardian, CFO, and Varys.

The onboarding engine manages the conversation-driven setup experience
where each agent introduces itself and collects necessary information.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.goos.client import (
    ClientRegistry,
    GOOSClient,
    OnboardingStep,
    VarysNode,
)


@dataclass
class OnboardingMessage:
    """A single message in the onboarding conversation."""
    speaker: str        # "guardian", "cfo", "varys", "system", "client"
    content: str
    step: str
    actions: list[str] = field(default_factory=list)  # Available UI actions
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "speaker": self.speaker,
            "content": self.content,
            "step": self.step,
            "actions": self.actions,
            "data": self.data,
            "timestamp": self.timestamp,
        }


class OnboardingEngine:
    """Drives the GOOS client onboarding conversation.

    Each step returns one or more OnboardingMessages that the frontend
    renders. The client responds with actions, and the engine advances
    to the next step.

    Flow:
        WELCOME → MEET_GUARDIAN → FILE_EXCHANGE → CHAT_INTRO →
        MEET_CFO → BUDGET_SETUP → MEET_VARYS → INSTALL_LOCAL →
        NETWORK_DISCOVERY → COMPLETE
    """

    def __init__(
        self,
        registry: ClientRegistry,
        audit: AuditLog | None = None,
    ) -> None:
        self._registry = registry
        self._audit = audit

    def _log(self, action: str, details: dict[str, Any] | None = None) -> None:
        if self._audit:
            self._audit.record(
                agent="goos_onboarding",
                action=action,
                severity=Severity.INFO,
                details=details or {},
            )

    def get_step_messages(self, client: GOOSClient) -> list[OnboardingMessage]:
        """Get the messages for the client's current onboarding step."""
        step = client.onboarding_step
        handler = self._step_handlers.get(step)
        if handler:
            return handler(self, client)
        return [OnboardingMessage(
            speaker="system",
            content="Onboarding complete.",
            step=step.value,
        )]

    def advance(
        self,
        client_id: str,
        client_data: dict[str, Any] | None = None,
    ) -> list[OnboardingMessage]:
        """Process client input and advance to the next onboarding step.

        Args:
            client_id: The client's ID.
            client_data: Any data submitted by the client at this step
                         (e.g., bank info, budget prefs, hostname).

        Returns:
            Messages for the next step.
        """
        client = self._registry.get_client(client_id)
        if not client:
            return [OnboardingMessage(
                speaker="system",
                content="Client not found.",
                step="error",
            )]

        current_step = client.onboarding_step

        # Process any submitted data for the current step
        if client_data:
            self._process_step_data(client, current_step, client_data)

        # Advance to next step
        next_step = self._registry.advance_onboarding(client_id)
        if not next_step:
            return [OnboardingMessage(
                speaker="system",
                content="Unable to advance onboarding.",
                step="error",
            )]

        self._log("step_advanced", {
            "client_id": client_id,
            "from": current_step.value,
            "to": next_step.value,
        })

        # Reload client with updated step
        client = self._registry.get_client(client_id)
        if not client:
            return []
        return self.get_step_messages(client)

    def _process_step_data(
        self,
        client: GOOSClient,
        step: OnboardingStep,
        data: dict[str, Any],
    ) -> None:
        """Handle data submitted during a specific onboarding step."""
        if step == OnboardingStep.BUDGET_SETUP:
            client.preferences["budget"] = data
        elif step == OnboardingStep.MEET_CFO:
            client.preferences["financial_profile"] = data
        elif step == OnboardingStep.INSTALL_LOCAL:
            hostname = data.get("hostname", "unknown")
            os_type = data.get("os_type", "linux")
            ip_local = data.get("ip_local", "")
            self._registry.register_varys_node(
                client.client_id, hostname, os_type, ip_local,
            )
        elif step == OnboardingStep.FILE_EXCHANGE:
            client.preferences["files_uploaded"] = data.get("file_count", 0)

    # ------------------------------------------------------------------
    # Step message generators
    # ------------------------------------------------------------------

    def _welcome(self, client: GOOSClient) -> list[OnboardingMessage]:
        return [OnboardingMessage(
            speaker="system",
            content=(
                f"Welcome to Guardian One Operating System, {client.display_name}.\n\n"
                "GOOS is your personal AI command center. You're about to meet "
                "the agents who will manage your digital and physical world.\n\n"
                "Let's begin."
            ),
            step="welcome",
            actions=["continue"],
        )]

    def _meet_guardian(self, client: GOOSClient) -> list[OnboardingMessage]:
        return [
            OnboardingMessage(
                speaker="guardian",
                content=(
                    f"Hello, {client.display_name}. I am Guardian.\n\n"
                    "I will be your central command AI agent. I coordinate "
                    "everything online — your finances, your schedule, your email, "
                    "your websites. Think of me as your executive assistant who "
                    "never sleeps.\n\n"
                    "I work in the cloud, processing data from all your connected "
                    "services. But I don't work alone."
                ),
                step="meet_guardian",
                actions=["continue"],
            ),
            OnboardingMessage(
                speaker="guardian",
                content=(
                    "You'll work with two primary agents:\n\n"
                    "1. **Me (Guardian)** — I handle the cloud. Online coordination, "
                    "API integrations, agent orchestration.\n\n"
                    "2. **Varys** — He handles your local world. Your computers, "
                    "your network, your IoT devices. Always on, always watching. "
                    "He's my collaborator.\n\n"
                    "But first, let me introduce you to someone who will help "
                    "manage your finances."
                ),
                step="meet_guardian",
                actions=["continue"],
            ),
        ]

    def _file_exchange(self, client: GOOSClient) -> list[OnboardingMessage]:
        return [OnboardingMessage(
            speaker="guardian",
            content=(
                "Before we proceed, you can upload any documents you'd like me "
                "to have access to — financial records, schedules, notes.\n\n"
                "Everything is encrypted with your personal key. I can only see "
                "what you share with me."
            ),
            step="file_exchange",
            actions=["upload_files", "skip"],
            data={"accepted_types": [".pdf", ".csv", ".xlsx", ".txt", ".json"]},
        )]

    def _chat_intro(self, client: GOOSClient) -> list[OnboardingMessage]:
        return [OnboardingMessage(
            speaker="guardian",
            content=(
                "This is your chat interface. You can talk to me anytime — "
                "ask questions, give instructions, or just check in.\n\n"
                "Try saying something. I'm listening."
            ),
            step="chat_intro",
            actions=["send_message", "continue"],
        )]

    def _meet_cfo(self, client: GOOSClient) -> list[OnboardingMessage]:
        return [
            OnboardingMessage(
                speaker="guardian",
                content=(
                    "Now, meet the CFO. He manages your money."
                ),
                step="meet_cfo",
            ),
            OnboardingMessage(
                speaker="cfo",
                content=(
                    f"Hello, {client.display_name}. I'm the CFO.\n\n"
                    "I'll be managing your financial intelligence — bank accounts, "
                    "budgets, bills, investments, and spending analysis.\n\n"
                    "What you tell me will be shared with Guardian — we work as a team. "
                    "Everything is encrypted and only accessible to you.\n\n"
                    "Would you like to connect your bank accounts?"
                ),
                step="meet_cfo",
                actions=["connect_bank", "skip"],
                data={"integration": "plaid_link"},
            ),
        ]

    def _budget_setup(self, client: GOOSClient) -> list[OnboardingMessage]:
        return [OnboardingMessage(
            speaker="cfo",
            content=(
                "Let's set up your budget preferences.\n\n"
                "I'll track your spending across categories and alert you "
                "when something looks off. What are your monthly goals?\n\n"
                "You can always adjust these later."
            ),
            step="budget_setup",
            actions=["set_budget", "skip"],
            data={
                "categories": [
                    "housing", "food", "transport", "utilities",
                    "entertainment", "savings", "investments",
                ],
            },
        )]

    def _meet_varys(self, client: GOOSClient) -> list[OnboardingMessage]:
        return [
            OnboardingMessage(
                speaker="guardian",
                content=(
                    "Good. Now let's set up your local agent.\n\n"
                    "Meet Varys."
                ),
                step="meet_varys",
            ),
            OnboardingMessage(
                speaker="varys",
                content=(
                    f"{client.display_name}. I am Varys.\n\n"
                    "I will live on your computers — always available, 24/7. "
                    "I manage your physical world: IoT devices, home network, "
                    "local security.\n\n"
                    "I am Guardian's collaborator. He works online, I work locally. "
                    "Together, we keep your entire world running.\n\n"
                    "I provide the H.O.M.E. L.I.N.K. interface — that's how I "
                    "talk to your smart devices, monitor your network, and "
                    "ensure your security from the inside.\n\n"
                    "Even if the internet goes down, I'm still here."
                ),
                step="meet_varys",
                actions=["continue"],
            ),
        ]

    def _install_local(self, client: GOOSClient) -> list[OnboardingMessage]:
        return [OnboardingMessage(
            speaker="varys",
            content=(
                "To get started, I need to be installed on your machine.\n\n"
                "We start with Linux. Run this in your terminal:\n\n"
                "```bash\n"
                "curl -sSL https://goos.jtmdai.com/install | bash\n"
                "```\n\n"
                "This installs me as a background service. I'll run quietly, "
                "discover your network, and report back to Guardian.\n\n"
                "You can also install me on additional machines later."
            ),
            step="install_local",
            actions=["install_complete", "skip_for_now"],
            data={
                "supported_os": ["linux"],
                "install_method": "systemd_service",
            },
        )]

    def _network_discovery(self, client: GOOSClient) -> list[OnboardingMessage]:
        nodes = client.varys_nodes
        if nodes:
            node_info = nodes[-1]
            return [OnboardingMessage(
                speaker="varys",
                content=(
                    f"Systems online on {node_info.hostname}.\n\n"
                    "I've scanned your local network and I'm ready to manage "
                    "your devices.\n\n"
                    "I'll monitor for:\n"
                    "- Unauthorized devices on your network\n"
                    "- IoT device health and firmware updates\n"
                    "- Security threats and anomalies\n"
                    "- Network performance\n\n"
                    "Guardian and I will keep you covered."
                ),
                step="network_discovery",
                actions=["continue"],
                data={"node": node_info.to_dict()},
            )]
        return [OnboardingMessage(
            speaker="varys",
            content=(
                "No local installation detected yet. That's okay — "
                "you can install me later from your dashboard.\n\n"
                "Guardian will handle everything from the cloud for now."
            ),
            step="network_discovery",
            actions=["continue"],
        )]

    def _complete(self, client: GOOSClient) -> list[OnboardingMessage]:
        agents = client.agents_enabled
        has_varys = client.has_varys
        return [
            OnboardingMessage(
                speaker="guardian",
                content=(
                    f"You're fully onboarded, {client.display_name}.\n\n"
                    "Here's what's active:\n"
                    f"- **Guardian** (cloud) — central command, online\n"
                    f"- **CFO** — managing your finances\n"
                    f"- **Varys** — {'local sentinel, always on' if has_varys else 'ready to install when you are'}\n"
                    f"\nActive agents: {', '.join(agents)}\n\n"
                    "You can activate additional agents from your dashboard:\n"
                    "- Chronos (scheduling & calendar)\n"
                    "- Archivist (data sovereignty & backups)\n"
                    "- And more...\n\n"
                    "What would you like to do first?"
                ),
                step="complete",
                actions=["open_dashboard", "chat", "explore_agents"],
            ),
        ]

    # Step → handler mapping
    _step_handlers = {
        OnboardingStep.WELCOME: _welcome,
        OnboardingStep.MEET_GUARDIAN: _meet_guardian,
        OnboardingStep.FILE_EXCHANGE: _file_exchange,
        OnboardingStep.CHAT_INTRO: _chat_intro,
        OnboardingStep.MEET_CFO: _meet_cfo,
        OnboardingStep.BUDGET_SETUP: _budget_setup,
        OnboardingStep.MEET_VARYS: _meet_varys,
        OnboardingStep.INSTALL_LOCAL: _install_local,
        OnboardingStep.NETWORK_DISCOVERY: _network_discovery,
        OnboardingStep.COMPLETE: _complete,
    }
