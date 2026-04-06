"""GOOS Client — multi-tenant user model for Guardian One Operating System.

Every registered user becomes a GOOSClient with their own:
- Vault (encrypted credentials)
- Audit trail
- Agent configuration
- Varys node registrations
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from guardian_one.core.audit import AuditLog, Severity


class ClientTier(Enum):
    """Subscription tiers for GOOS clients."""
    FREE = "free"           # Guardian + Varys (local only), basic IoT
    PREMIUM = "premium"     # Full agent suite, cloud sync, CFO
    SOVEREIGN = "sovereign" # Dedicated instance, custom agents, SLA


class ClientStatus(Enum):
    """Lifecycle status of a GOOS client."""
    PENDING = "pending"         # Email sent, awaiting verification
    ONBOARDING = "onboarding"   # Verified, going through setup
    ACTIVE = "active"           # Fully onboarded
    SUSPENDED = "suspended"     # Account suspended
    OFFLINE = "offline"         # Detached from cloud, Varys-only mode


class OnboardingStep(Enum):
    """Steps in the client onboarding flow."""
    WELCOME = "welcome"                     # Initial welcome screen
    MEET_GUARDIAN = "meet_guardian"          # Introduction to Guardian
    FILE_EXCHANGE = "file_exchange"          # Upload documents
    CHAT_INTRO = "chat_intro"               # First chat with Guardian
    MEET_CFO = "meet_cfo"                   # CFO introduction + bank linking
    BUDGET_SETUP = "budget_setup"           # Budget preferences
    MEET_VARYS = "meet_varys"               # Varys introduction
    INSTALL_LOCAL = "install_local"          # Install GOOS on local machine
    NETWORK_DISCOVERY = "network_discovery" # Varys discovers local network
    COMPLETE = "complete"                   # Fully onboarded


@dataclass
class VarysNode:
    """A registered Varys installation on a client's machine."""
    node_id: str
    hostname: str
    os_type: str            # linux, darwin, windows
    installed_at: str
    last_seen: str
    status: str = "active"  # active, offline, decommissioned
    ip_local: str = ""
    devices_managed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "os_type": self.os_type,
            "installed_at": self.installed_at,
            "last_seen": self.last_seen,
            "status": self.status,
            "ip_local": self.ip_local,
            "devices_managed": self.devices_managed,
        }


@dataclass
class GOOSClient:
    """A registered client of the Guardian One Operating System.

    Each client gets their own isolated environment with:
    - Guardian (cloud coordinator)
    - Varys (local sentinel, optional)
    - CFO + other agents (per tier)
    """
    client_id: str
    email: str
    display_name: str
    tier: ClientTier = ClientTier.FREE
    status: ClientStatus = ClientStatus.PENDING
    onboarding_step: OnboardingStep = OnboardingStep.WELCOME
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    verified_at: str = ""
    onboarded_at: str = ""
    varys_nodes: list[VarysNode] = field(default_factory=list)
    agents_enabled: list[str] = field(default_factory=list)
    preferences: dict[str, Any] = field(default_factory=dict)

    # Security
    password_hash: str = ""
    verification_token: str = ""
    encryption_key_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "email": self.email,
            "display_name": self.display_name,
            "tier": self.tier.value,
            "status": self.status.value,
            "onboarding_step": self.onboarding_step.value,
            "created_at": self.created_at,
            "verified_at": self.verified_at,
            "onboarded_at": self.onboarded_at,
            "varys_nodes": [n.to_dict() for n in self.varys_nodes],
            "agents_enabled": self.agents_enabled,
            "preferences": self.preferences,
        }

    @property
    def is_verified(self) -> bool:
        return bool(self.verified_at)

    @property
    def is_onboarded(self) -> bool:
        return self.onboarding_step == OnboardingStep.COMPLETE

    @property
    def has_varys(self) -> bool:
        return any(n.status == "active" for n in self.varys_nodes)

    def default_agents_for_tier(self) -> list[str]:
        """Return default agent list based on subscription tier."""
        base = ["guardian"]
        if self.tier == ClientTier.FREE:
            return base + ["varys"]
        elif self.tier == ClientTier.PREMIUM:
            return base + [
                "varys", "cfo", "chronos", "archivist",
                "gmail_agent", "doordash",
            ]
        elif self.tier == ClientTier.SOVEREIGN:
            return base + [
                "varys", "cfo", "chronos", "archivist",
                "gmail_agent", "web_architect", "doordash",
                "dev_coach",
            ]
        return base


class ClientRegistry:
    """In-memory client registry for GOOS.

    Production would use SQLite/PostgreSQL via CitadelOne.
    This provides the API contract.
    """

    def __init__(self, audit: AuditLog | None = None) -> None:
        self._clients: dict[str, GOOSClient] = {}
        self._email_index: dict[str, str] = {}  # email → client_id
        self._audit = audit

    def _log(self, action: str, details: dict[str, Any] | None = None) -> None:
        if self._audit:
            self._audit.record(
                agent="goos_registry",
                action=action,
                severity=Severity.INFO,
                details=details or {},
            )

    def create_client(
        self,
        email: str,
        display_name: str,
        password_hash: str = "",
        tier: ClientTier = ClientTier.FREE,
    ) -> GOOSClient:
        """Create a new GOOS client account."""
        email_lower = email.lower().strip()

        if email_lower in self._email_index:
            raise ValueError(f"Account already exists for {email_lower}")

        client_id = str(uuid.uuid4())
        verification_token = secrets.token_urlsafe(32)

        client = GOOSClient(
            client_id=client_id,
            email=email_lower,
            display_name=display_name,
            password_hash=password_hash,
            verification_token=verification_token,
            tier=tier,
            status=ClientStatus.PENDING,
            onboarding_step=OnboardingStep.WELCOME,
            agents_enabled=GOOSClient(
                client_id="", email="", display_name="", tier=tier,
            ).default_agents_for_tier(),
        )

        self._clients[client_id] = client
        self._email_index[email_lower] = client_id
        self._log("client_created", {"client_id": client_id, "email": email_lower})
        return client

    def verify_email(self, client_id: str, token: str) -> bool:
        """Verify a client's email with their verification token."""
        client = self._clients.get(client_id)
        if not client:
            return False
        if client.verification_token != token:
            return False

        client.verified_at = datetime.now(timezone.utc).isoformat()
        client.status = ClientStatus.ONBOARDING
        client.onboarding_step = OnboardingStep.MEET_GUARDIAN
        client.verification_token = ""  # Consumed
        self._log("email_verified", {"client_id": client_id})
        return True

    def get_client(self, client_id: str) -> GOOSClient | None:
        return self._clients.get(client_id)

    def get_by_email(self, email: str) -> GOOSClient | None:
        client_id = self._email_index.get(email.lower().strip())
        if client_id:
            return self._clients.get(client_id)
        return None

    def advance_onboarding(self, client_id: str) -> OnboardingStep | None:
        """Move client to the next onboarding step."""
        client = self._clients.get(client_id)
        if not client:
            return None

        steps = list(OnboardingStep)
        current_idx = steps.index(client.onboarding_step)

        if current_idx < len(steps) - 1:
            next_step = steps[current_idx + 1]
            client.onboarding_step = next_step

            if next_step == OnboardingStep.COMPLETE:
                client.status = ClientStatus.ACTIVE
                client.onboarded_at = datetime.now(timezone.utc).isoformat()

            self._log("onboarding_advanced", {
                "client_id": client_id,
                "step": next_step.value,
            })
            return next_step
        return client.onboarding_step

    def register_varys_node(
        self,
        client_id: str,
        hostname: str,
        os_type: str = "linux",
        ip_local: str = "",
    ) -> VarysNode | None:
        """Register a Varys installation on a client's machine."""
        client = self._clients.get(client_id)
        if not client:
            return None

        now = datetime.now(timezone.utc).isoformat()
        node = VarysNode(
            node_id=str(uuid.uuid4()),
            hostname=hostname,
            os_type=os_type,
            installed_at=now,
            last_seen=now,
            ip_local=ip_local,
        )
        client.varys_nodes.append(node)
        self._log("varys_node_registered", {
            "client_id": client_id,
            "node_id": node.node_id,
            "hostname": hostname,
        })
        return node

    def set_offline_mode(self, client_id: str) -> bool:
        """Detach client from cloud — Varys-only mode."""
        client = self._clients.get(client_id)
        if not client:
            return False
        client.status = ClientStatus.OFFLINE
        self._log("offline_mode_enabled", {"client_id": client_id})
        return True

    def reconnect(self, client_id: str) -> bool:
        """Reconnect an offline client to the cloud."""
        client = self._clients.get(client_id)
        if not client or client.status != ClientStatus.OFFLINE:
            return False
        client.status = ClientStatus.ACTIVE
        self._log("client_reconnected", {"client_id": client_id})
        return True

    def list_clients(self) -> list[GOOSClient]:
        return list(self._clients.values())

    @property
    def count(self) -> int:
        return len(self._clients)
