"""Ollama Integration — sovereign local LLM management.

Provides model lifecycle management, health monitoring, and performance
benchmarking for the local Ollama instance. This is Guardian One's
primary AI backend — all reasoning stays on-device.

Usage:
    sync = OllamaSync(gateway, vault, audit)
    health = sync.health_check()
    models = sync.list_models()
    sync.pull_model("llama3:70b")
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from guardian_one.core.audit import AuditLog, Severity

logger = logging.getLogger(__name__)


@dataclass
class OllamaModel:
    """Metadata for a locally available Ollama model."""
    name: str
    size_bytes: int = 0
    modified_at: str = ""
    digest: str = ""
    family: str = ""
    parameter_size: str = ""
    quantization: str = ""

    @property
    def size_gb(self) -> float:
        return round(self.size_bytes / (1024 ** 3), 1)


@dataclass
class OllamaHealth:
    """Health check result for the Ollama instance."""
    reachable: bool = False
    version: str = ""
    models_count: int = 0
    models: list[OllamaModel] = field(default_factory=list)
    total_size_gb: float = 0.0
    latency_ms: float = 0.0
    api_key_configured: bool = False
    error: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def healthy(self) -> bool:
        return self.reachable and self.models_count > 0


@dataclass
class BenchmarkResult:
    """Result from a model performance benchmark."""
    model: str
    prompt: str
    tokens_generated: int = 0
    total_duration_ms: float = 0.0
    load_duration_ms: float = 0.0
    eval_duration_ms: float = 0.0
    tokens_per_second: float = 0.0
    success: bool = False
    error: str = ""


class OllamaSync:
    """Manages the local Ollama LLM instance.

    Responsibilities:
        - Health monitoring (is Ollama running? which models are available?)
        - Model lifecycle (list, pull, delete)
        - Performance benchmarking
        - Status reporting for dashboards and Notion sync
    """

    def __init__(
        self,
        audit: AuditLog,
        base_url: str | None = None,
    ) -> None:
        self._audit = audit
        self._base_url = (base_url or os.environ.get(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )).rstrip("/")
        self._api_key = os.environ.get("OLLAMA_API_KEY", "")

    @property
    def base_url(self) -> str:
        return self._base_url

    def _headers(self) -> dict[str, str]:
        """Build request headers with optional API key."""
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    # ------------------------------------------------------------------
    # Health & status
    # ------------------------------------------------------------------

    def health_check(self) -> OllamaHealth:
        """Full health check of the Ollama instance."""
        start = time.monotonic()
        health = OllamaHealth(api_key_configured=bool(self._api_key))

        try:
            # Check if Ollama is reachable
            resp = httpx.get(
                f"{self._base_url}/api/tags",
                headers=self._headers(),
                timeout=10.0,
            )
            elapsed = (time.monotonic() - start) * 1000
            health.latency_ms = round(elapsed, 1)

            if resp.status_code != 200:
                health.error = f"HTTP {resp.status_code}"
                return health

            health.reachable = True
            data = resp.json()

            # Parse model list
            for m in data.get("models", []):
                model = OllamaModel(
                    name=m.get("name", ""),
                    size_bytes=m.get("size", 0),
                    modified_at=m.get("modified_at", ""),
                    digest=m.get("digest", "")[:12],
                    family=m.get("details", {}).get("family", ""),
                    parameter_size=m.get("details", {}).get("parameter_size", ""),
                    quantization=m.get("details", {}).get("quantization_level", ""),
                )
                health.models.append(model)

            health.models_count = len(health.models)
            health.total_size_gb = round(
                sum(m.size_bytes for m in health.models) / (1024 ** 3), 1
            )

            # Try to get version
            try:
                ver_resp = httpx.get(
                    f"{self._base_url}/api/version",
                    headers=self._headers(),
                    timeout=5.0,
                )
                if ver_resp.status_code == 200:
                    health.version = ver_resp.json().get("version", "")
            except Exception:
                pass

        except httpx.ConnectError:
            health.error = "Connection refused — is Ollama running?"
        except httpx.TimeoutException:
            health.error = "Connection timeout"
        except Exception as exc:
            health.error = str(exc)

        self._audit.record(
            agent="ollama_sync",
            action="health_check",
            severity=Severity.INFO,
            details={
                "reachable": health.reachable,
                "models": health.models_count,
                "latency_ms": health.latency_ms,
            },
        )
        return health

    def is_running(self) -> bool:
        """Quick check — is Ollama reachable?"""
        try:
            resp = httpx.get(
                f"{self._base_url}/api/tags",
                headers=self._headers(),
                timeout=5.0,
            )
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------

    def list_models(self) -> list[OllamaModel]:
        """List all locally available models."""
        health = self.health_check()
        return health.models

    def has_model(self, model_name: str) -> bool:
        """Check if a specific model is available locally."""
        models = self.list_models()
        base_name = model_name.split(":")[0]
        return any(
            m.name == model_name or m.name.split(":")[0] == base_name
            for m in models
        )

    def pull_model(self, model_name: str) -> dict[str, Any]:
        """Pull a model from the Ollama registry.

        Returns:
            {"success": bool, "model": str, "error": str}
        """
        self._audit.record(
            agent="ollama_sync",
            action=f"pull_model:{model_name}",
            severity=Severity.INFO,
        )

        try:
            resp = httpx.post(
                f"{self._base_url}/api/pull",
                json={"name": model_name, "stream": False},
                headers=self._headers(),
                timeout=600.0,  # Models can be large — 10 min timeout
            )

            if resp.status_code == 200:
                self._audit.record(
                    agent="ollama_sync",
                    action=f"pull_complete:{model_name}",
                    severity=Severity.INFO,
                )
                return {"success": True, "model": model_name, "error": ""}

            return {
                "success": False,
                "model": model_name,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
            }
        except Exception as exc:
            return {"success": False, "model": model_name, "error": str(exc)}

    def delete_model(self, model_name: str) -> dict[str, Any]:
        """Delete a locally stored model.

        Returns:
            {"success": bool, "model": str, "error": str}
        """
        self._audit.record(
            agent="ollama_sync",
            action=f"delete_model:{model_name}",
            severity=Severity.WARNING,
        )

        try:
            resp = httpx.delete(
                f"{self._base_url}/api/delete",
                json={"name": model_name},
                headers=self._headers(),
                timeout=30.0,
            )
            if resp.status_code == 200:
                return {"success": True, "model": model_name, "error": ""}
            return {
                "success": False,
                "model": model_name,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
            }
        except Exception as exc:
            return {"success": False, "model": model_name, "error": str(exc)}

    # ------------------------------------------------------------------
    # Benchmarking
    # ------------------------------------------------------------------

    def benchmark(self, model_name: str | None = None) -> BenchmarkResult:
        """Run a quick benchmark against a model.

        Sends a short reasoning prompt and measures response time + throughput.
        """
        model = model_name or "llama3"
        prompt = (
            "Analyze this: Jeremy has 3 bank accounts totaling $15,000 and "
            "monthly expenses of $4,200. What is his runway in months? "
            "Answer in one sentence."
        )

        result = BenchmarkResult(model=model, prompt=prompt[:50])

        try:
            start = time.monotonic()
            resp = httpx.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 100, "temperature": 0.3},
                },
                headers=self._headers(),
                timeout=120.0,
            )
            elapsed = (time.monotonic() - start) * 1000

            if resp.status_code != 200:
                result.error = f"HTTP {resp.status_code}"
                return result

            data = resp.json()
            result.success = True
            result.total_duration_ms = round(elapsed, 1)
            result.tokens_generated = data.get("eval_count", 0)
            result.load_duration_ms = round(
                data.get("load_duration", 0) / 1_000_000, 1
            )
            result.eval_duration_ms = round(
                data.get("eval_duration", 0) / 1_000_000, 1
            )

            if result.eval_duration_ms > 0:
                result.tokens_per_second = round(
                    result.tokens_generated / (result.eval_duration_ms / 1000), 1
                )

        except Exception as exc:
            result.error = str(exc)

        self._audit.record(
            agent="ollama_sync",
            action=f"benchmark:{model}",
            severity=Severity.INFO,
            details={
                "tokens": result.tokens_generated,
                "tps": result.tokens_per_second,
                "latency_ms": result.total_duration_ms,
            },
        )
        return result

    # ------------------------------------------------------------------
    # Formatted output
    # ------------------------------------------------------------------

    def status_text(self) -> str:
        """Produce formatted status text for CLI output."""
        health = self.health_check()
        lines = [
            "",
            "  OLLAMA — SOVEREIGN AI ENGINE",
            "  " + "=" * 50,
        ]

        if not health.reachable:
            lines.append(f"  Status: OFFLINE")
            lines.append(f"  Error:  {health.error}")
            lines.append("")
            lines.append("  To start Ollama:")
            lines.append("    ollama serve")
            lines.append("")
            lines.append("  To pull a model:")
            lines.append("    ollama pull llama3")
            return "\n".join(lines)

        lines.append(f"  Status:    ONLINE")
        if health.version:
            lines.append(f"  Version:   {health.version}")
        lines.append(f"  Endpoint:  {self._base_url}")
        lines.append(f"  API Key:   {'configured' if health.api_key_configured else 'not set'}")
        lines.append(f"  Latency:   {health.latency_ms}ms")
        lines.append(f"  Models:    {health.models_count}")
        lines.append(f"  Disk:      {health.total_size_gb} GB")
        lines.append("")

        if health.models:
            lines.append(f"  {'MODEL':<30} {'SIZE':>8}  {'FAMILY':<12} {'QUANT':<8}")
            lines.append("  " + "-" * 62)
            for m in sorted(health.models, key=lambda x: x.size_bytes, reverse=True):
                lines.append(
                    f"  {m.name:<30} {m.size_gb:>6.1f}GB"
                    f"  {m.family:<12} {m.quantization:<8}"
                )
        else:
            lines.append("  No models installed. Run: ollama pull llama3")

        lines.append("")
        return "\n".join(lines)

    def dashboard_data(self) -> dict[str, Any]:
        """Structured data for Notion sync and dashboards."""
        health = self.health_check()
        return {
            "status": "online" if health.reachable else "offline",
            "version": health.version,
            "endpoint": self._base_url,
            "api_key_configured": health.api_key_configured,
            "latency_ms": health.latency_ms,
            "models_count": health.models_count,
            "total_size_gb": health.total_size_gb,
            "models": [
                {
                    "name": m.name,
                    "size_gb": m.size_gb,
                    "family": m.family,
                    "parameter_size": m.parameter_size,
                    "quantization": m.quantization,
                }
                for m in health.models
            ],
            "error": health.error,
            "checked_at": health.timestamp,
        }
