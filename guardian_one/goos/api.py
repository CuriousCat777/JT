"""GOOS API — REST endpoints for the Guardian One Operating System platform.

Provides the web API for:
- Client registration and authentication
- Onboarding flow
- Agent management
- Varys node registration
- System status
"""

from __future__ import annotations

from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.goos.client import ClientRegistry, ClientTier, GOOSClient
from guardian_one.goos.registration import RegistrationService, RegistrationResult
from guardian_one.goos.onboarding import OnboardingEngine


class GOOSAPI:
    """Central API controller for the GOOS platform.

    In production, this backs a Flask/FastAPI web application.
    This class provides the business logic layer.
    """

    def __init__(self, audit: AuditLog | None = None) -> None:
        self.audit = audit or AuditLog()
        self.registry = ClientRegistry(audit=self.audit)
        self.registration = RegistrationService(
            registry=self.registry, audit=self.audit,
        )
        self.onboarding = OnboardingEngine(
            registry=self.registry, audit=self.audit,
        )

    # ------------------------------------------------------------------
    # Registration endpoints
    # ------------------------------------------------------------------

    def register(
        self,
        email: str,
        display_name: str,
        password: str,
        captcha_token: str = "",
        ip_address: str = "",
        tier: str = "free",
    ) -> dict[str, Any]:
        """POST /api/register"""
        tier_map = {
            "free": ClientTier.FREE,
            "premium": ClientTier.PREMIUM,
            "sovereign": ClientTier.SOVEREIGN,
        }
        result = self.registration.register(
            email=email,
            display_name=display_name,
            password=password,
            captcha_token=captcha_token,
            ip_address=ip_address,
            tier=tier_map.get(tier, ClientTier.FREE),
        )
        return result.to_dict()

    def verify_email(self, client_id: str, token: str) -> dict[str, Any]:
        """GET /api/verify?client_id=...&token=..."""
        success = self.registration.verify_email(client_id, token)
        return {"success": success}

    def login(self, email: str, password: str) -> dict[str, Any]:
        """POST /api/login"""
        result = self.registration.authenticate(email, password)
        response: dict[str, Any] = {"success": result.success}
        if result.success:
            response["client_id"] = result.client_id
            response["session_token"] = result.session_token
        else:
            response["error"] = result.error
        return response

    # ------------------------------------------------------------------
    # Onboarding endpoints
    # ------------------------------------------------------------------

    def get_onboarding_step(self, client_id: str) -> dict[str, Any]:
        """GET /api/onboarding/:client_id"""
        client = self.registry.get_client(client_id)
        if not client:
            return {"error": "Client not found"}

        messages = self.onboarding.get_step_messages(client)
        return {
            "client_id": client_id,
            "step": client.onboarding_step.value,
            "messages": [m.to_dict() for m in messages],
        }

    def advance_onboarding(
        self, client_id: str, data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /api/onboarding/:client_id/advance"""
        messages = self.onboarding.advance(client_id, client_data=data)
        client = self.registry.get_client(client_id)
        return {
            "client_id": client_id,
            "step": client.onboarding_step.value if client else "unknown",
            "messages": [m.to_dict() for m in messages],
        }

    # ------------------------------------------------------------------
    # Client management
    # ------------------------------------------------------------------

    def get_client(self, client_id: str) -> dict[str, Any]:
        """GET /api/client/:client_id"""
        client = self.registry.get_client(client_id)
        if not client:
            return {"error": "Client not found"}
        return client.to_dict()

    def register_varys_node(
        self,
        client_id: str,
        hostname: str,
        os_type: str = "linux",
        ip_local: str = "",
    ) -> dict[str, Any]:
        """POST /api/client/:client_id/varys"""
        node = self.registry.register_varys_node(
            client_id, hostname, os_type, ip_local,
        )
        if not node:
            return {"error": "Client not found"}
        return node.to_dict()

    def set_offline(self, client_id: str) -> dict[str, Any]:
        """POST /api/client/:client_id/offline"""
        success = self.registry.set_offline_mode(client_id)
        return {"success": success}

    def reconnect(self, client_id: str) -> dict[str, Any]:
        """POST /api/client/:client_id/reconnect"""
        success = self.registry.reconnect(client_id)
        return {"success": success}

    # ------------------------------------------------------------------
    # System status
    # ------------------------------------------------------------------

    def platform_status(self) -> dict[str, Any]:
        """GET /api/status"""
        return {
            "platform": "Guardian One Operating System",
            "version": "1.0",
            "total_clients": self.registry.count,
            "status": "operational",
        }
