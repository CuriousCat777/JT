"""GOOS Registration — account creation, verification, and authentication.

Handles the registration flow:
1. Client submits email + name
2. Human verification (CAPTCHA check)
3. Email verification token sent
4. Client verifies email → account activated → onboarding begins
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.goos.client import (
    ClientRegistry,
    ClientTier,
    GOOSClient,
)


@dataclass
class RegistrationResult:
    """Result of a registration attempt."""
    success: bool
    client_id: str = ""
    verification_token: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"success": self.success}
        if self.success:
            d["client_id"] = self.client_id
        else:
            d["error"] = self.error
        return d


@dataclass
class AuthResult:
    """Result of an authentication attempt."""
    success: bool
    client_id: str = ""
    session_token: str = ""
    error: str = ""


# Minimal email validation — not exhaustive, just sanity check
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


class RegistrationService:
    """Handles GOOS account registration and verification."""

    def __init__(
        self,
        registry: ClientRegistry,
        audit: AuditLog | None = None,
    ) -> None:
        self._registry = registry
        self._audit = audit
        self._failed_attempts: dict[str, int] = {}  # IP → count

    def _log(
        self,
        action: str,
        severity: Severity = Severity.INFO,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self._audit:
            self._audit.record(
                agent="goos_registration",
                action=action,
                severity=severity,
                details=details or {},
            )

    def register(
        self,
        email: str,
        display_name: str,
        password: str,
        captcha_token: str = "",
        ip_address: str = "",
        tier: ClientTier = ClientTier.FREE,
    ) -> RegistrationResult:
        """Register a new GOOS client.

        Args:
            email: Client's email address.
            display_name: Client's display name.
            password: Plaintext password (hashed immediately).
            captcha_token: CAPTCHA verification token (hCaptcha).
            ip_address: Client's IP for rate limiting.
            tier: Requested subscription tier.

        Returns:
            RegistrationResult with client_id and verification token on success.
        """
        # Rate limit check
        if ip_address and self._failed_attempts.get(ip_address, 0) >= 10:
            self._log("registration_rate_limited", Severity.WARNING, {
                "ip": ip_address,
            })
            return RegistrationResult(
                success=False,
                error="Too many registration attempts. Try again later.",
            )

        # Validate email format
        if not _EMAIL_RE.match(email):
            return RegistrationResult(
                success=False,
                error="Invalid email format.",
            )

        # Validate display name
        display_name = display_name.strip()
        if len(display_name) < 2 or len(display_name) > 100:
            return RegistrationResult(
                success=False,
                error="Display name must be 2-100 characters.",
            )

        # Validate password strength
        if len(password) < 12:
            return RegistrationResult(
                success=False,
                error="Password must be at least 12 characters.",
            )

        # Verify CAPTCHA (human verification)
        if not self._verify_captcha(captcha_token):
            if ip_address:
                self._failed_attempts[ip_address] = (
                    self._failed_attempts.get(ip_address, 0) + 1
                )
            return RegistrationResult(
                success=False,
                error="Human verification failed. Please try again.",
            )

        # Check for existing account
        existing = self._registry.get_by_email(email)
        if existing:
            self._log("registration_duplicate", details={"email": email})
            return RegistrationResult(
                success=False,
                error="An account with this email already exists.",
            )

        # Hash password
        password_hash = self._hash_password(password)

        # Create client
        try:
            client = self._registry.create_client(
                email=email,
                display_name=display_name,
                password_hash=password_hash,
                tier=tier,
            )
        except ValueError as e:
            return RegistrationResult(success=False, error=str(e))

        self._log("registration_success", details={
            "client_id": client.client_id,
            "email": email,
            "tier": tier.value,
        })

        return RegistrationResult(
            success=True,
            client_id=client.client_id,
            verification_token=client.verification_token,
        )

    def verify_email(self, client_id: str, token: str) -> bool:
        """Verify a client's email address."""
        result = self._registry.verify_email(client_id, token)
        if result:
            self._log("email_verified", details={"client_id": client_id})
        else:
            self._log("email_verification_failed", Severity.WARNING, {
                "client_id": client_id,
            })
        return result

    def authenticate(self, email: str, password: str) -> AuthResult:
        """Authenticate a client and return a session token."""
        client = self._registry.get_by_email(email)
        if not client:
            return AuthResult(success=False, error="Invalid credentials.")

        if not client.is_verified:
            return AuthResult(
                success=False,
                error="Email not verified. Check your inbox.",
            )

        if not self._verify_password(password, client.password_hash):
            self._log("auth_failed", Severity.WARNING, {
                "client_id": client.client_id,
            })
            return AuthResult(success=False, error="Invalid credentials.")

        session_token = secrets.token_urlsafe(48)
        self._log("auth_success", details={"client_id": client.client_id})

        return AuthResult(
            success=True,
            client_id=client.client_id,
            session_token=session_token,
        )

    @staticmethod
    def _hash_password(password: str) -> str:
        """Hash a password using PBKDF2-SHA256."""
        salt = secrets.token_hex(16)
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), iterations=600_000,
        )
        return f"{salt}:{dk.hex()}"

    @staticmethod
    def _verify_password(password: str, stored_hash: str) -> bool:
        """Verify a password against a stored hash."""
        if ":" not in stored_hash:
            return False
        salt, hash_hex = stored_hash.split(":", 1)
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), iterations=600_000,
        )
        return hmac.compare_digest(dk.hex(), hash_hex)

    @staticmethod
    def _verify_captcha(token: str) -> bool:
        """Verify hCaptcha token.

        In production, this calls the hCaptcha API.
        For now, accepts any non-empty token for development.
        """
        # TODO: Integrate hCaptcha API verification
        # POST https://hcaptcha.com/siteverify
        # with secret + token
        return bool(token)
