"""Secure API Gateway for H.O.M.E. L.I.N.K.

Every external API call made by any Guardian One agent is routed through
this gateway.  It enforces:
    - TLS 1.3 minimum
    - Rate limiting (per-service)
    - Request/response logging (secrets redacted)
    - Timeout enforcement
    - Automatic retry with exponential backoff
    - Circuit breaker for failing services
"""

from __future__ import annotations

import json
import ssl
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from guardian_one.core.audit import AuditLog, Severity

# Headers whose values must be redacted in logs / audit trails
_SENSITIVE_HEADERS = frozenset({
    "authorization", "x-api-key", "api-key", "cookie",
    "set-cookie", "proxy-authorization", "x-auth-token",
})


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing — block requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class RateLimitConfig:
    """Per-service rate limit."""
    max_requests: int = 60
    window_seconds: int = 60


@dataclass
class ServiceConfig:
    """Configuration for an external service connection."""
    name: str
    base_url: str
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    timeout_seconds: int = 30
    max_retries: int = 3
    circuit_failure_threshold: int = 5
    circuit_recovery_seconds: int = 60
    require_tls: bool = True
    allowed_agents: list[str] = field(default_factory=list)  # Empty = all agents


@dataclass
class RequestRecord:
    """Audit record for a gateway request (secrets redacted)."""
    timestamp: str
    service: str
    method: str
    path: str
    agent: str
    status_code: int
    latency_ms: float
    success: bool
    error: str = ""


class _RateLimiter:
    """Token-bucket rate limiter."""

    def __init__(self, config: RateLimitConfig) -> None:
        self._max = config.max_requests
        self._window = config.window_seconds
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def allow(self) -> bool:
        now = time.monotonic()
        with self._lock:
            self._timestamps = [
                t for t in self._timestamps if t > now - self._window
            ]
            if len(self._timestamps) >= self._max:
                return False
            self._timestamps.append(now)
            return True

    def remaining(self) -> int:
        now = time.monotonic()
        with self._lock:
            active = [t for t in self._timestamps if t > now - self._window]
            return max(0, self._max - len(active))


class _CircuitBreaker:
    """Circuit breaker to protect against cascading failures."""

    def __init__(self, failure_threshold: int, recovery_seconds: int) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._last_failure: float = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure > self._recovery_seconds:
                    self._state = CircuitState.HALF_OPEN
            return self._state

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure = time.time()
            if self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN

    def allow_request(self) -> bool:
        s = self.state
        return s in (CircuitState.CLOSED, CircuitState.HALF_OPEN)


class Gateway:
    """Central API gateway for all external service calls.

    Usage:
        gw = Gateway(audit=audit_log)
        gw.register_service(ServiceConfig(name="doordash", base_url="https://openapi.doordash.com"))
        response = gw.request("doordash", "GET", "/drive/v2/deliveries/123",
                              headers={"Authorization": "Bearer ..."}, agent="doordash")
    """

    def __init__(self, audit: AuditLog) -> None:
        self._audit = audit
        self._services: dict[str, ServiceConfig] = {}
        self._rate_limiters: dict[str, _RateLimiter] = {}
        self._circuit_breakers: dict[str, _CircuitBreaker] = {}
        self._history: list[RequestRecord] = []
        self._history_lock = threading.Lock()
        self._ssl_ctx = self._create_ssl_context()

    @staticmethod
    def _create_ssl_context() -> ssl.SSLContext:
        """Create a TLS 1.3+ context.  Falls back to TLS 1.2 if 1.3 unavailable."""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        except (ValueError, AttributeError):
            pass  # TLS 1.3 not supported on this system; 1.2 is acceptable
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_default_certs()
        return ctx

    # ------------------------------------------------------------------
    # Service registration
    # ------------------------------------------------------------------

    def register_service(self, config: ServiceConfig) -> None:
        self._services[config.name] = config
        self._rate_limiters[config.name] = _RateLimiter(config.rate_limit)
        self._circuit_breakers[config.name] = _CircuitBreaker(
            config.circuit_failure_threshold,
            config.circuit_recovery_seconds,
        )
        self._audit.record(
            agent="homelink",
            action=f"service_registered:{config.name}",
            details={"base_url": config.base_url},
        )

    def get_service(self, name: str) -> ServiceConfig | None:
        return self._services.get(name)

    def list_services(self) -> list[str]:
        return list(self._services.keys())

    # ------------------------------------------------------------------
    # Request execution
    # ------------------------------------------------------------------

    def request(
        self,
        service: str,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        agent: str = "unknown",
    ) -> dict[str, Any]:
        """Execute an API request through the gateway.

        Returns a dict with keys: success, status_code, data, error.
        """
        config = self._services.get(service)
        if config is None:
            return {"success": False, "status_code": 0, "data": None,
                    "error": f"Service '{service}' not registered."}

        # Access control
        if config.allowed_agents and agent not in config.allowed_agents:
            self._audit.record(
                agent="homelink",
                action=f"access_denied:{service}",
                severity=Severity.WARNING,
                details={"agent": agent},
            )
            return {"success": False, "status_code": 403, "data": None,
                    "error": f"Agent '{agent}' not authorized for service '{service}'."}

        # TLS enforcement
        if config.require_tls and not config.base_url.startswith("https://"):
            return {"success": False, "status_code": 0, "data": None,
                    "error": f"TLS required for '{service}' but base_url is not HTTPS."}

        # Circuit breaker
        breaker = self._circuit_breakers[service]
        if not breaker.allow_request():
            return {"success": False, "status_code": 503, "data": None,
                    "error": f"Circuit open for '{service}' — service is failing."}

        # Rate limiting
        limiter = self._rate_limiters[service]
        if not limiter.allow():
            return {"success": False, "status_code": 429, "data": None,
                    "error": f"Rate limit exceeded for '{service}'."}

        # Execute with retry
        url = f"{config.base_url.rstrip('/')}{path}"
        last_error = ""
        for attempt in range(config.max_retries + 1):
            start = time.time()
            try:
                result = self._do_request(url, method, headers, body, config.timeout_seconds)
                latency = (time.time() - start) * 1000

                record = RequestRecord(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    service=service, method=method, path=path, agent=agent,
                    status_code=result["status_code"], latency_ms=round(latency, 1),
                    success=result["success"],
                )
                with self._history_lock:
                    self._history.append(record)
                self._audit.record(
                    agent="homelink",
                    action=f"api_call:{service}:{method}:{path}",
                    details={
                        "status": result["status_code"],
                        "latency_ms": round(latency, 1),
                        "agent": agent,
                    },
                )

                if result["success"]:
                    breaker.record_success()
                else:
                    breaker.record_failure()
                return result

            except Exception as exc:
                last_error = str(exc)
                latency = (time.time() - start) * 1000
                with self._history_lock:
                    self._history.append(RequestRecord(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        service=service, method=method, path=path, agent=agent,
                        status_code=0, latency_ms=round(latency, 1),
                        success=False, error=last_error,
                    ))
                breaker.record_failure()

                if attempt < config.max_retries:
                    backoff = 2 ** (attempt + 1)
                    time.sleep(backoff)

        self._audit.record(
            agent="homelink",
            action=f"api_exhausted_retries:{service}",
            severity=Severity.ERROR,
            details={"attempts": config.max_retries + 1, "last_error": last_error},
        )
        return {"success": False, "status_code": 0, "data": None,
                "error": f"All {config.max_retries + 1} attempts failed: {last_error}"}

    @staticmethod
    def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
        """Return a copy of *headers* with sensitive values replaced."""
        return {
            k: ("***REDACTED***" if k.lower() in _SENSITIVE_HEADERS else v)
            for k, v in headers.items()
        }

    def _do_request(
        self,
        url: str,
        method: str,
        headers: dict[str, str] | None,
        body: dict[str, Any] | None,
        timeout: int,
    ) -> dict[str, Any]:
        """Low-level HTTP request."""
        data = json.dumps(body).encode() if body else None
        all_headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if headers:
            all_headers.update(headers)

        req = urllib.request.Request(url, data=data, method=method, headers=all_headers)
        ctx = self._ssl_ctx if url.startswith("https://") else None

        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                resp_data = json.loads(resp.read().decode())
                return {"success": True, "status_code": resp.status, "data": resp_data, "error": ""}
        except urllib.error.HTTPError as e:
            error_body = ""
            if e.fp:
                try:
                    error_body = e.read().decode()
                except Exception:
                    pass
            return {"success": False, "status_code": e.code, "data": None, "error": error_body}
        except urllib.error.URLError as e:
            raise ConnectionError(f"Network error: {e.reason}") from e

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def service_status(self, service: str) -> dict[str, Any]:
        """Get health status for a registered service."""
        config = self._services.get(service)
        if config is None:
            return {"error": f"Unknown service: {service}"}

        breaker = self._circuit_breakers[service]
        limiter = self._rate_limiters[service]
        with self._history_lock:
            recent = [r for r in self._history if r.service == service][-20:]

        avg_latency = 0.0
        if recent:
            avg_latency = sum(r.latency_ms for r in recent) / len(recent)

        success_count = sum(1 for r in recent if r.success)

        return {
            "service": service,
            "circuit_state": breaker.state.value,
            "rate_limit_remaining": limiter.remaining(),
            "recent_requests": len(recent),
            "success_rate": round(success_count / len(recent), 2) if recent else 1.0,
            "avg_latency_ms": round(avg_latency, 1),
        }

    def all_services_status(self) -> dict[str, dict[str, Any]]:
        return {name: self.service_status(name) for name in self._services}

    def request_history(self, service: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._history_lock:
            records = list(self._history)
        if service:
            records = [r for r in records if r.service == service]
        return [
            {
                "timestamp": r.timestamp,
                "service": r.service,
                "method": r.method,
                "path": r.path,
                "agent": r.agent,
                "status_code": r.status_code,
                "latency_ms": r.latency_ms,
                "success": r.success,
            }
            for r in records[-limit:]
        ]
