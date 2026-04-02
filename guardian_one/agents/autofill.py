"""Autofill Agent — Password manager bridge that actually works.

Responsibilities:
- Store payment cards, addresses, and identities securely in Vault
- Serve a local-only API for browser-side autofill
- Generate one-time tokens for each fill request
- Audit every fill operation
- Provide CLI for profile management (add, list, remove)

The browser bookmarklet talks to our local server, which pulls
encrypted data from Vault on demand. No data cached in memory
after serving.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from dataclasses import field
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig
from guardian_one.autofill.profiles import (
    CARD_PREFIX,
    ADDRESS_PREFIX,
    IDENTITY_PREFIX,
    PROFILE_TYPES,
    CardProfile,
    AddressProfile,
    IdentityProfile,
)


# One-time tokens: token -> (profile_type, profile_id, created_timestamp)
_pending_tokens: dict[str, tuple[str, str, float]] = {}
_token_lock = threading.Lock()

TOKEN_TTL_SECONDS = 120  # Tokens expire after 2 minutes


def _generate_token(profile_type: str, profile_id: str) -> str:
    """Generate a one-time token for a fill request."""
    token = secrets.token_urlsafe(32)
    with _token_lock:
        _pending_tokens[token] = (profile_type, profile_id, time.time())
    return token


def _consume_token(token: str) -> tuple[str, str] | None:
    """Consume a one-time token. Returns (profile_type, profile_id) or None."""
    with _token_lock:
        entry = _pending_tokens.pop(token, None)
        if entry is None:
            return None
        ptype, pid, created = entry
        if time.time() - created > TOKEN_TTL_SECONDS:
            return None  # Expired
        return (ptype, pid)


def _cleanup_expired_tokens() -> int:
    """Remove expired tokens. Returns count removed."""
    now = time.time()
    removed = 0
    with _token_lock:
        expired = [
            t for t, (_, _, ts) in _pending_tokens.items()
            if now - ts > TOKEN_TTL_SECONDS
        ]
        for t in expired:
            del _pending_tokens[t]
            removed += 1
    return removed


class AutofillAgent(BaseAgent):
    """Manages autofill profiles in Vault and serves them to browsers."""

    def __init__(
        self,
        config: AgentConfig,
        audit: AuditLog,
        vault: Any = None,
    ) -> None:
        super().__init__(config, audit)
        self._vault = vault
        self._server: HTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        self._port = config.custom.get("autofill_port", 17380)
        self._bind = config.custom.get("autofill_bind", "127.0.0.1")
        self._lan_pin: str | None = None  # Set via set_lan_pin() for LAN mode

    def set_vault(self, vault: Any) -> None:
        """Inject vault reference (called by GuardianOne after registration)."""
        self._vault = vault

    # ── LAN mode & PIN ───────────────────────────────────────────

    def set_lan_pin(self, pin: str) -> None:
        """Set PIN for LAN-mode access. Stored as SHA-256 hash in vault."""
        pin_hash = hashlib.sha256(pin.encode()).hexdigest()
        self._vault.store(
            "autofill_lan_pin", pin_hash,
            service="autofill", scope="admin",
        )
        self._lan_pin = pin_hash
        self.log("lan_pin_set", severity=Severity.WARNING)

    def _load_lan_pin(self) -> str | None:
        """Load the hashed PIN from vault."""
        if self._lan_pin:
            return self._lan_pin
        raw = self._vault.retrieve("autofill_lan_pin")
        if raw:
            self._lan_pin = raw
        return self._lan_pin

    def verify_pin(self, pin: str) -> bool:
        """Verify a PIN against the stored hash."""
        stored = self._load_lan_pin()
        if stored is None:
            return False
        return hashlib.sha256(pin.encode()).hexdigest() == stored

    @property
    def is_lan_mode(self) -> bool:
        return self._bind != "127.0.0.1"

    def enable_lan_mode(self, bind: str = "0.0.0.0") -> None:
        """Switch to LAN mode (requires PIN to be set first)."""
        if self._load_lan_pin() is None:
            raise ValueError("Set a PIN first with set_lan_pin() before enabling LAN mode")
        self._bind = bind
        self.log(
            "lan_mode_enabled",
            severity=Severity.WARNING,
            details={"bind": bind},
        )

    # ── Profile CRUD ─────────────────────────────────────────────

    def add_card(
        self,
        label: str,
        cardholder_name: str,
        card_number: str,
        exp_month: str,
        exp_year: str,
        cvv: str,
        billing_address: str = "",
        billing_zip: str = "",
    ) -> CardProfile:
        """Add a payment card to the vault."""
        profile = CardProfile(
            label=label,
            cardholder_name=cardholder_name,
            card_number=card_number,
            exp_month=exp_month,
            exp_year=exp_year,
            cvv=cvv,
            billing_address=billing_address,
            billing_zip=billing_zip,
        )
        key = f"{CARD_PREFIX}{profile.profile_id}"
        self._vault.store(key, profile.to_json(), service="autofill", scope="read")
        self.log(
            "card_added",
            details={"label": label, "masked": profile.masked_number},
        )
        return profile

    def add_address(
        self,
        label: str,
        full_name: str,
        street: str,
        city: str,
        state: str,
        zip_code: str,
        country: str = "US",
        phone: str = "",
    ) -> AddressProfile:
        """Add an address profile to the vault."""
        profile = AddressProfile(
            label=label,
            full_name=full_name,
            street=street,
            city=city,
            state=state,
            zip_code=zip_code,
            country=country,
            phone=phone,
        )
        key = f"{ADDRESS_PREFIX}{profile.profile_id}"
        self._vault.store(key, profile.to_json(), service="autofill", scope="read")
        self.log("address_added", details={"label": label})
        return profile

    def add_identity(
        self,
        label: str,
        first_name: str,
        last_name: str,
        email: str,
        phone: str = "",
        date_of_birth: str = "",
    ) -> IdentityProfile:
        """Add an identity profile to the vault."""
        profile = IdentityProfile(
            label=label,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            date_of_birth=date_of_birth,
        )
        key = f"{IDENTITY_PREFIX}{profile.profile_id}"
        self._vault.store(key, profile.to_json(), service="autofill", scope="read")
        self.log("identity_added", details={"label": label})
        return profile

    def list_profiles(self, profile_type: str | None = None) -> list[dict[str, Any]]:
        """List profiles (metadata only, no secrets).

        Args:
            profile_type: "card", "address", "identity", or None for all.
        """
        results = []
        keys = self._vault.list_keys()

        type_map = {
            "card": (CARD_PREFIX, CardProfile),
            "address": (ADDRESS_PREFIX, AddressProfile),
            "identity": (IDENTITY_PREFIX, IdentityProfile),
        }

        if profile_type:
            prefixes = {profile_type: type_map[profile_type]}
        else:
            prefixes = type_map

        for ptype, (prefix, cls) in prefixes.items():
            for k in keys:
                if not k.startswith(prefix):
                    continue
                raw = self._vault.retrieve(k)
                if raw is None:
                    continue
                data = json.loads(raw)
                summary = {
                    "type": ptype,
                    "profile_id": data.get("profile_id", ""),
                    "label": data.get("label", ""),
                    "created_at": data.get("created_at", ""),
                }
                if ptype == "card":
                    num = data.get("card_number", "")
                    summary["masked_number"] = f"****{num[-4:]}" if len(num) >= 4 else "****"
                results.append(summary)

        return results

    def get_profile(self, profile_type: str, profile_id: str) -> dict[str, Any] | None:
        """Retrieve full profile data from vault."""
        prefix = PROFILE_TYPES.get(profile_type, (None, None))[0]
        if prefix is None:
            return None
        key = f"{prefix}{profile_id}"
        raw = self._vault.retrieve(key)
        if raw is None:
            return None
        return json.loads(raw)

    def remove_profile(self, profile_type: str, profile_id: str) -> bool:
        """Delete a profile from vault."""
        prefix = PROFILE_TYPES.get(profile_type, (None, None))[0]
        if prefix is None:
            return False
        key = f"{prefix}{profile_id}"
        deleted = self._vault.delete(key)
        if deleted:
            self.log(
                "profile_removed",
                details={"type": profile_type, "profile_id": profile_id},
            )
        return deleted

    # ── Token management ─────────────────────────────────────────

    def request_fill_token(self, profile_type: str, profile_id: str) -> str | None:
        """Generate a one-time token to authorize a browser fill."""
        # Verify profile exists
        if self.get_profile(profile_type, profile_id) is None:
            return None
        token = _generate_token(profile_type, profile_id)
        self.log(
            "fill_token_issued",
            details={"type": profile_type, "profile_id": profile_id},
        )
        return token

    # ── Local API Server ─────────────────────────────────────────

    def start_server(self, bind_override: str | None = None) -> str:
        """Start the local autofill API server. Returns the URL."""
        bind = bind_override or self._bind
        if self._server is not None:
            return f"http://{bind}:{self._port}"

        # LAN mode safety check
        if bind != "127.0.0.1" and self._load_lan_pin() is None:
            raise ValueError(
                "Cannot start in LAN mode without a PIN. "
                "Set one with: python main.py --autofill-pin"
            )

        agent_ref = self
        # Session tokens for LAN-authenticated clients
        # session_token -> expiry_timestamp
        lan_sessions: dict[str, float] = {}
        lan_session_lock = threading.Lock()
        LAN_SESSION_TTL = 3600  # 1 hour

        def _is_localhost(addr: str) -> bool:
            return addr in ("127.0.0.1", "::1", "localhost")

        class AutofillHandler(BaseHTTPRequestHandler):
            """Handles autofill API requests. PIN-gated when in LAN mode."""

            def log_message(self, fmt: str, *args: Any) -> None:
                pass  # Suppress default HTTP logging

            def _cors_headers(self) -> None:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

            def _check_lan_auth(self) -> bool:
                """Returns True if request is authorized.

                Localhost requests always pass. LAN requests need
                a valid session token in the Authorization header.
                """
                client_ip = self.client_address[0]
                if _is_localhost(client_ip):
                    return True
                if bind == "127.0.0.1":
                    return True  # Shouldn't happen, but safe

                # Check Authorization: Bearer <session_token>
                auth = self.headers.get("Authorization", "")
                if not auth.startswith("Bearer "):
                    return False
                session_token = auth[7:]
                with lan_session_lock:
                    expiry = lan_sessions.get(session_token)
                    if expiry is None or time.time() > expiry:
                        lan_sessions.pop(session_token, None)
                        return False
                return True

            def do_OPTIONS(self) -> None:
                self.send_response(200)
                self._cors_headers()
                self.end_headers()

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path

                # Health is always public; auth endpoint is always open
                if path == "/api/autofill/health":
                    self._handle_health()
                    return

                if not self._check_lan_auth():
                    self._send_json(401, {"error": "unauthorized", "hint": "POST /api/autofill/auth with {\"pin\": \"...\"}"})
                    return

                if path == "/api/autofill/profiles":
                    self._handle_list_profiles(parsed)
                elif path == "/api/autofill/bookmarklet":
                    self._handle_bookmarklet()
                else:
                    self._send_json(404, {"error": "not_found"})

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path

                # Auth endpoint is always open (it's how you get a session)
                if path == "/api/autofill/auth":
                    self._handle_auth()
                    return

                if not self._check_lan_auth():
                    self._send_json(401, {"error": "unauthorized", "hint": "POST /api/autofill/auth with {\"pin\": \"...\"}"})
                    return

                if path == "/api/autofill/token":
                    self._handle_request_token()
                elif path == "/api/autofill/fill":
                    self._handle_fill()
                else:
                    self._send_json(404, {"error": "not_found"})

            def _read_body(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", 0))
                if length == 0:
                    return {}
                raw = self.rfile.read(length)
                return json.loads(raw)

            def _send_json(self, code: int, data: dict[str, Any]) -> None:
                body = json.dumps(data).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self._cors_headers()
                self.end_headers()
                self.wfile.write(body)

            def _send_js(self, code: int, js: str) -> None:
                body = js.encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/javascript")
                self._cors_headers()
                self.end_headers()
                self.wfile.write(body)

            def _handle_auth(self) -> None:
                """PIN authentication — returns a 1-hour session token."""
                body = self._read_body()
                pin = body.get("pin", "")
                if not pin:
                    self._send_json(400, {"error": "pin required"})
                    return
                if not agent_ref.verify_pin(pin):
                    agent_ref.log(
                        "lan_auth_failed",
                        severity=Severity.WARNING,
                        details={"client": self.client_address[0]},
                    )
                    self._send_json(403, {"error": "invalid pin"})
                    return

                session_token = secrets.token_urlsafe(32)
                with lan_session_lock:
                    lan_sessions[session_token] = time.time() + LAN_SESSION_TTL
                agent_ref.log(
                    "lan_auth_success",
                    details={"client": self.client_address[0]},
                )
                self._send_json(200, {
                    "session_token": session_token,
                    "ttl": LAN_SESSION_TTL,
                })

            def _handle_health(self) -> None:
                self._send_json(200, {
                    "status": "ok",
                    "agent": "autofill",
                    "profiles": len(agent_ref.list_profiles()),
                    "lan_mode": agent_ref.is_lan_mode,
                })

            def _handle_list_profiles(self, parsed: Any) -> None:
                params = parse_qs(parsed.query)
                ptype = params.get("type", [None])[0]
                profiles = agent_ref.list_profiles(ptype)
                self._send_json(200, {"profiles": profiles})

            def _handle_request_token(self) -> None:
                body = self._read_body()
                ptype = body.get("type", "")
                pid = body.get("profile_id", "")
                if not ptype or not pid:
                    self._send_json(400, {"error": "type and profile_id required"})
                    return
                token = agent_ref.request_fill_token(ptype, pid)
                if token is None:
                    self._send_json(404, {"error": "profile not found"})
                    return
                self._send_json(200, {"token": token, "ttl": TOKEN_TTL_SECONDS})

            def _handle_fill(self) -> None:
                body = self._read_body()
                token = body.get("token", "")
                if not token:
                    self._send_json(400, {"error": "token required"})
                    return
                result = _consume_token(token)
                if result is None:
                    agent_ref.log(
                        "fill_token_rejected",
                        severity=Severity.WARNING,
                        details={"token_prefix": token[:8]},
                    )
                    self._send_json(403, {"error": "invalid or expired token"})
                    return
                ptype, pid = result
                data = agent_ref.get_profile(ptype, pid)
                if data is None:
                    self._send_json(404, {"error": "profile not found"})
                    return

                # Build fill map — the field hints the bookmarklet uses
                fill_map = _build_fill_map(ptype, data)

                agent_ref.log(
                    "fill_served",
                    details={"type": ptype, "profile_id": pid},
                )
                self._send_json(200, {"fill": fill_map, "type": ptype})

            def _handle_bookmarklet(self) -> None:
                """Serve the bookmarklet JavaScript."""
                from guardian_one.autofill.bridge import get_bookmarklet_js
                host = self.headers.get("Host", f"{bind}:{agent_ref._port}")
                js = get_bookmarklet_js(host=host)
                self._send_js(200, js)

        self._server = HTTPServer((bind, self._port), AutofillHandler)
        self._server_thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="autofill-server",
        )
        self._server_thread.start()

        url = f"http://{bind}:{self._port}"
        self.log(
            "server_started",
            severity=Severity.WARNING if bind != "127.0.0.1" else Severity.INFO,
            details={"url": url, "port": self._port, "bind": bind, "lan_mode": bind != "127.0.0.1"},
        )
        return url

    def stop_server(self) -> None:
        """Shutdown the local API server."""
        if self._server:
            self._server.shutdown()
            self._server = None
            self._server_thread = None
            self.log("server_stopped")

    # ── BaseAgent lifecycle ──────────────────────────────────────

    def initialize(self) -> None:
        self._set_status(AgentStatus.IDLE)
        self.log("initialized", details={"port": self._port})

    def run(self) -> AgentReport:
        self._set_status(AgentStatus.RUNNING)
        _cleanup_expired_tokens()
        profiles = self.list_profiles()
        card_count = sum(1 for p in profiles if p["type"] == "card")
        addr_count = sum(1 for p in profiles if p["type"] == "address")
        id_count = sum(1 for p in profiles if p["type"] == "identity")

        server_running = self._server is not None
        summary = (
            f"Autofill Bridge: {len(profiles)} profiles "
            f"({card_count} cards, {addr_count} addresses, {id_count} identities). "
            f"Server: {'running' if server_running else 'stopped'}."
        )

        self._set_status(AgentStatus.IDLE)
        return AgentReport(
            agent_name=self.name,
            status="ok",
            summary=summary,
            data={
                "total_profiles": len(profiles),
                "cards": card_count,
                "addresses": addr_count,
                "identities": id_count,
                "server_running": server_running,
                "port": self._port,
            },
        )

    def report(self) -> AgentReport:
        return self.run()

    def shutdown(self) -> None:
        self.stop_server()
        super().shutdown()


def _build_fill_map(profile_type: str, data: dict[str, Any]) -> dict[str, Any]:
    """Convert profile data into a field-hints map for the bookmarklet.

    The bookmarklet uses these hints to match form fields by name,
    id, placeholder, autocomplete attribute, and label text.
    """
    if profile_type == "card":
        return {
            "fields": [
                {
                    "value": data.get("cardholder_name", ""),
                    "hints": ["cardholder", "card-holder", "card_holder", "ccname",
                              "cc-name", "card holder", "name on card", "cardname"],
                    "autocomplete": "cc-name",
                },
                {
                    "value": data.get("card_number", ""),
                    "hints": ["cardnumber", "card-number", "card_number", "ccnumber",
                              "cc-number", "pan", "account number", "cardnum"],
                    "autocomplete": "cc-number",
                },
                {
                    "value": data.get("exp_month", ""),
                    "hints": ["exp-month", "exp_month", "ccmonth", "cc-exp-month",
                              "expmonth", "expirymonth", "expiry-month"],
                    "autocomplete": "cc-exp-month",
                },
                {
                    "value": data.get("exp_year", ""),
                    "hints": ["exp-year", "exp_year", "ccyear", "cc-exp-year",
                              "expyear", "expiryyear", "expiry-year"],
                    "autocomplete": "cc-exp-year",
                },
                {
                    "value": f"{data.get('exp_month', '')}/{data.get('exp_year', '')}",
                    "hints": ["expiry", "expiration", "cc-exp", "exp",
                              "mm/yyyy", "mm/yy", "mmyyyy", "mmyy",
                              "exp date", "expdate", "expirationdate"],
                    "autocomplete": "cc-exp",
                },
                {
                    "value": data.get("cvv", ""),
                    "hints": ["cvv", "cvc", "cvv2", "cvc2", "security-code",
                              "security code", "securitycode", "card-cvc",
                              "cc-csc"],
                    "autocomplete": "cc-csc",
                },
                {
                    "value": data.get("billing_address", ""),
                    "hints": ["billing-address", "billing_address", "billingaddress",
                              "street", "address", "address1", "street-address"],
                    "autocomplete": "billing street-address",
                },
                {
                    "value": data.get("billing_zip", ""),
                    "hints": ["zip", "zipcode", "zip-code", "zip_code", "postal",
                              "postal-code", "postalcode", "billing-zip",
                              "billingzip"],
                    "autocomplete": "billing postal-code",
                },
            ]
        }
    elif profile_type == "address":
        return {
            "fields": [
                {
                    "value": data.get("full_name", ""),
                    "hints": ["name", "fullname", "full-name", "full_name",
                              "recipient"],
                    "autocomplete": "name",
                },
                {
                    "value": data.get("street", ""),
                    "hints": ["street", "address", "address1", "street-address",
                              "addressline1"],
                    "autocomplete": "street-address",
                },
                {
                    "value": data.get("city", ""),
                    "hints": ["city", "locality", "address-level2"],
                    "autocomplete": "address-level2",
                },
                {
                    "value": data.get("state", ""),
                    "hints": ["state", "region", "province", "address-level1"],
                    "autocomplete": "address-level1",
                },
                {
                    "value": data.get("zip_code", ""),
                    "hints": ["zip", "zipcode", "zip-code", "postal",
                              "postal-code", "postalcode"],
                    "autocomplete": "postal-code",
                },
                {
                    "value": data.get("country", ""),
                    "hints": ["country", "country-name"],
                    "autocomplete": "country-name",
                },
                {
                    "value": data.get("phone", ""),
                    "hints": ["phone", "tel", "telephone", "mobile", "phonenumber"],
                    "autocomplete": "tel",
                },
            ]
        }
    elif profile_type == "identity":
        return {
            "fields": [
                {
                    "value": data.get("first_name", ""),
                    "hints": ["firstname", "first-name", "first_name", "fname",
                              "given-name", "givenname"],
                    "autocomplete": "given-name",
                },
                {
                    "value": data.get("last_name", ""),
                    "hints": ["lastname", "last-name", "last_name", "lname",
                              "family-name", "familyname", "surname"],
                    "autocomplete": "family-name",
                },
                {
                    "value": data.get("email", ""),
                    "hints": ["email", "e-mail", "emailaddress", "email-address"],
                    "autocomplete": "email",
                },
                {
                    "value": data.get("phone", ""),
                    "hints": ["phone", "tel", "telephone", "mobile"],
                    "autocomplete": "tel",
                },
                {
                    "value": data.get("date_of_birth", ""),
                    "hints": ["dob", "birthdate", "birthday", "date-of-birth",
                              "dateofbirth", "bday"],
                    "autocomplete": "bday",
                },
            ]
        }
    return {"fields": []}
